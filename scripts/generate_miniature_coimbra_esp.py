from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ALT_MIN = -500.0
ALT_MAX = 65_117_481.0
FOV_MAX = 178.0

# Visual anchors in central Coimbra. These are framing targets, not navigation points.
MONDEGO = (-8.4314, 40.2027, 55.0)
BAIXA = (-8.4300, 40.2089, 75.0)
UNIVERSITY = (-8.4264, 40.2077, 120.0)
CITY_CENTER = (-8.4267, 40.2057, 95.0)

# Reproducible late-afternoon light. The exact time can still be changed in Earth Studio.
DEFAULT_WORLD_TIME = datetime(2026, 9, 25, 16, 45, tzinfo=timezone.utc)

AUTO_IN = {"x": -0.055, "y": 0, "influence": 0.45, "type": "auto"}
AUTO_OUT = {"x": 0.055, "y": 0, "influence": 0.45, "type": "auto"}


@dataclass(frozen=True)
class Beat:
    sec: float
    label: str
    target_lon: float
    target_lat: float
    target_alt: float
    cam_east_m: float
    cam_north_m: float
    cam_alt_m: float
    fov_deg: float


def lon_rel(v: float) -> float:
    return (v + 180.0) / 360.0


def lat_rel(v: float) -> float:
    return (v + 90.0) / 180.0


def alt_rel(v: float) -> float:
    return (v - ALT_MIN) / (ALT_MAX - ALT_MIN)


def offset(lon: float, lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    lat2 = lat + north_m / 111_320.0
    lon2 = lon + east_m / (111_320.0 * math.cos(math.radians(lat)))
    return lon2, lat2


def _kf(t: float, v: float) -> dict:
    return {
        "time": t,
        "value": v,
        "transitionIn": dict(AUTO_IN),
        "transitionOut": dict(AUTO_OUT),
    }


def _block(type_: str, pairs: list[tuple[float, float]], *, value_extra: dict | None = None) -> dict:
    value = {"relative": pairs[0][1]}
    if value_extra:
        value.update(value_extra)
    return {
        "type": type_,
        "value": value,
        "keyframes": [_kf(t, v) for t, v in pairs],
        "inTimeline": True,
    }


def _world_time_block(dt: datetime) -> dict:
    t_ms = int(dt.timestamp() * 1000)
    return {
        "minValueRange": t_ms - 43_200_000,
        "maxValueRange": t_ms + 43_200_000,
        "relative": 0.5,
    }


def wide_beats() -> list[Beat]:
    # Broad sideways move. City stays compressed in perspective and reads like a tabletop model.
    return [
        Beat(0.0,  "wide SW", *MONDEGO, -1650, -1150, 1550, 31),
        Beat(7.5,  "wide river", *MONDEGO, -1250, -1000, 1480, 30),
        Beat(15.0, "wide Baixa", *BAIXA, -900, -1250, 1420, 29),
        Beat(23.0, "wide University", *UNIVERSITY, -350, -1400, 1360, 28),
        Beat(31.0, "wide city east", *CITY_CENTER, 450, -1350, 1400, 29),
        Beat(38.0, "wide finish", *UNIVERSITY, 1050, -750, 1460, 30),
    ]


def orbit_beats() -> list[Beat]:
    # Large-radius arc around the entire historical centre. No close-up street movement.
    return [
        Beat(0.0,  "orbit SW", *CITY_CENTER, -1350, -900, 1350, 31),
        Beat(8.0,  "orbit W",  *CITY_CENTER, -1550, -100, 1320, 30),
        Beat(16.0, "orbit NW", *CITY_CENTER, -1050, 1050, 1300, 29),
        Beat(24.0, "orbit N",  *CITY_CENTER, -100, 1500, 1320, 29),
        Beat(32.0, "orbit NE", *CITY_CENTER, 1050, 1050, 1360, 30),
        Beat(38.0, "orbit E",  *CITY_CENTER, 1450, 250, 1420, 31),
    ]


def reveal_beats() -> list[Beat]:
    # Focus story: Mondego -> Baixa -> University. Camera descends slightly while the POI moves uphill.
    return [
        Beat(0.0,  "reveal establishing", *MONDEGO, -1650, -1450, 1650, 33),
        Beat(7.0,  "reveal river", *MONDEGO, -1250, -1150, 1500, 31),
        Beat(14.0, "reveal transition", -8.4307, 40.2050, 65, -900, -1100, 1380, 30),
        Beat(21.0, "reveal Baixa", *BAIXA, -650, -1050, 1260, 29),
        Beat(28.0, "reveal climb", -8.4284, 40.2070, 95, -350, -1050, 1150, 28),
        Beat(35.0, "reveal University", *UNIVERSITY, 100, -900, 1080, 27),
        Beat(41.0, "reveal finale", *UNIVERSITY, 650, -550, 1120, 28),
    ]


def build_project(name: str, beats: list[Beat], fps: int, width: int, height: int) -> dict:
    duration_s = beats[-1].sec
    frames = int(round(duration_s * fps))

    camera = []
    target = []
    for b in beats:
        cam_lon, cam_lat = offset(
            b.target_lon,
            b.target_lat,
            b.cam_east_m,
            b.cam_north_m,
        )
        t = b.sec / duration_s
        camera.append((t, cam_lon, cam_lat, b.cam_alt_m, b.fov_deg))
        target.append((t, b.target_lon, b.target_lat, b.target_alt))

    pos = {
        "type": "position",
        "inTimeline": True,
        "attributes": [
            _block("longitude", [(t, lon_rel(lon)) for t, lon, lat, alt, fov in camera]),
            _block("latitude", [(t, lat_rel(lat)) for t, lon, lat, alt, fov in camera]),
            _block(
                "altitude",
                [(t, alt_rel(alt)) for t, lon, lat, alt, fov in camera],
                value_extra={
                    "minValueRange": ALT_MIN,
                    "maxValueRange": ALT_MAX,
                    "logarithmic": False,
                },
            ),
        ],
    }

    target_effect = {
        "type": "cameraTargetEffect",
        "inTimeline": True,
        "attributes": [
            {"type": "enabled", "value": {"relative": 1}, "inTimeline": True},
            {
                "type": "poi",
                "inTimeline": True,
                "attributes": [
                    _block("longitudePOI", [(t, lon_rel(lon)) for t, lon, lat, alt in target]),
                    _block("latitudePOI", [(t, lat_rel(lat)) for t, lon, lat, alt in target]),
                    _block(
                        "altitudePOI",
                        [(t, alt_rel(alt)) for t, lon, lat, alt in target],
                        value_extra={
                            "minValueRange": ALT_MIN,
                            "maxValueRange": ALT_MAX,
                            "logarithmic": False,
                        },
                    ),
                ],
            },
            {"type": "influence", "value": {"relative": 1}, "inTimeline": True},
        ],
    }

    fov_block = _block(
        "fov",
        [(t, fov / FOV_MAX) for t, lon, lat, alt, fov in camera],
    )

    return {
        "modelVersion": 18,
        "settings": {
            "name": name,
            "frameRate": fps,
            "dimensions": {"width": width, "height": height},
            "duration": frames,
            "timeFormat": "frames",
        },
        "scenes": [
            {
                "world": {"kmls": []},
                "animationModel": {
                    "roving": False,
                    "logarithmic": False,
                    "groupedPosition": True,
                },
                "duration": frames,
                "attributes": [
                    {
                        "type": "cameraGroup",
                        "inTimeline": True,
                        "attributes": [
                            {
                                "type": "cameraPositionGroup",
                                "inTimeline": True,
                                "attributes": [pos],
                            },
                            target_effect,
                            {
                                "type": "cameraRotationGroup",
                                "inTimeline": True,
                                "attributes": [
                                    {"type": "rotationX", "value": {}},
                                    {"type": "rotationY", "value": {}},
                                    {"type": "rotationZ", "value": {"relative": 0}},
                                ],
                            },
                            {
                                "type": "cameraLensGroup",
                                "inTimeline": True,
                                "attributes": [
                                    fov_block,
                                    {"type": "exposure", "value": {}},
                                    {"type": "aperture", "value": {}},
                                    {"type": "minFocusLength", "value": {}},
                                ],
                            },
                        ],
                    },
                    {
                        "type": "environmentGroup",
                        "attributes": [
                            {
                                "type": "sunGroup",
                                "attributes": [
                                    {"type": "sunVisibility", "value": {"relative": 1}},
                                    {"type": "worldTime", "value": _world_time_block(DEFAULT_WORLD_TIME)},
                                ],
                            },
                            {
                                "type": "cloudGroup",
                                "attributes": [
                                    {"type": "cloudVisibility", "value": {}},
                                    {"type": "cloudopacity", "value": {}},
                                    {"type": "cloudheight", "value": {}},
                                    {"type": "clouddate", "value": {}},
                                ],
                            },
                            {
                                "type": "starsPlanetsGroup",
                                "attributes": [{"type": "starsEnabled", "value": {}}],
                            },
                            {"type": "buildingsEnabled", "value": {"relative": 1}},
                        ],
                    },
                ],
                "cameraExport": {"logarithmic": False, "modelVersion": 2},
            }
        ],
        "playbackManager": {"range": {"start": 0, "end": frames}},
    }


def write_project(path: Path, project: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project, indent=2), encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["modelVersion"] == 18
    assert data["settings"]["duration"] > 0
    print(f"Wrote {path}: {data['settings']['duration']} frames")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Coimbra miniature-look Earth Studio projects.")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    out = Path(args.output_dir)
    variants = {
        "coimbra-miniature-wide.esp": ("Coimbra miniature - wide", wide_beats()),
        "coimbra-miniature-orbit.esp": ("Coimbra miniature - orbit", orbit_beats()),
        "coimbra-miniature-reveal.esp": ("Coimbra miniature - reveal", reveal_beats()),
    }

    for filename, (name, beats) in variants.items():
        project = build_project(name, beats, args.fps, args.width, args.height)
        write_project(out / filename, project)

    plan = {
        "goal": "Make Coimbra read like a physical architectural model.",
        "shared_style": {
            "resolution": [args.width, args.height],
            "fps": args.fps,
            "camera_altitude_m": "1080-1650",
            "fov_deg": "27-33",
            "movement": "slow, high, oblique, long-lens",
            "postprocess": "moving tilt-shift focus band + mild saturation/contrast",
        },
        "variants": {
            "wide": {
                "duration_s": wide_beats()[-1].sec,
                "idea": "Broad lateral pass across the whole city.",
            },
            "orbit": {
                "duration_s": orbit_beats()[-1].sec,
                "idea": "Large-radius arc around the historical centre.",
            },
            "reveal": {
                "duration_s": reveal_beats()[-1].sec,
                "idea": "Move the visual focus Mondego -> Baixa -> University.",
                "focus_story": ["Mondego", "Baixa", "Universidade de Coimbra"],
            },
        },
    }
    (out / "coimbra-miniature-plan.json").write_text(
        json.dumps(plan, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
