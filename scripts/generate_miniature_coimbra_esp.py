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
PRISON = (-8.41793, 40.20703)  # Estabelecimento Prisional de Coimbra
PRISON_EXCLUSION_RADIUS_M = 450.0

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


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def angular_separation_deg(
    camera: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    ba = bearing_deg(camera, a)
    bb = bearing_deg(camera, b)
    return abs((bb - ba + 180.0) % 360.0 - 180.0)


def prison_exclusion_points() -> list[tuple[float, float]]:
    points = [PRISON]
    for i in range(24):
        angle = 2.0 * math.pi * i / 24
        points.append(
            offset(
                PRISON[0],
                PRISON[1],
                PRISON_EXCLUSION_RADIUS_M * math.cos(angle),
                PRISON_EXCLUSION_RADIUS_M * math.sin(angle),
            )
        )
    return points


def assert_prison_outside_frame(beats: list[Beat], min_margin_deg: float = 18.0) -> None:
    exclusion = prison_exclusion_points()

    for left, right in zip(beats, beats[1:]):
        # Earth Studio uses smooth interpolation. Sampling the straight interpolation
        # is not an exact model of its Bezier curve, so we keep a deliberately large
        # angular safety margin.
        for step in range(21):
            u = step / 20.0

            target_lon = left.target_lon + (right.target_lon - left.target_lon) * u
            target_lat = left.target_lat + (right.target_lat - left.target_lat) * u

            left_cam = offset(
                left.target_lon, left.target_lat, left.cam_east_m, left.cam_north_m
            )
            right_cam = offset(
                right.target_lon, right.target_lat, right.cam_east_m, right.cam_north_m
            )
            cam_lon = left_cam[0] + (right_cam[0] - left_cam[0]) * u
            cam_lat = left_cam[1] + (right_cam[1] - left_cam[1]) * u

            fov = left.fov_deg + (right.fov_deg - left.fov_deg) * u
            camera = (cam_lon, cam_lat)
            target = (target_lon, target_lat)

            nearest = min(
                angular_separation_deg(camera, target, p)
                for p in exclusion
            )
            margin = nearest - fov / 2.0
            if margin < min_margin_deg:
                raise ValueError(
                    f"Prison exclusion failed near {left.label} -> {right.label}: "
                    f"margin={margin:.1f} deg, required={min_margin_deg:.1f}"
                )


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
    # Broad pass from the east / south-east looking west across the city.
    # This keeps the blurred prison complex out of the principal field of view.
    return [
        Beat(0.0,  "wide river SE", *MONDEGO, 1500, -900, 1550, 28),
        Beat(7.5,  "wide river E", *MONDEGO, 1400, -400, 1480, 27),
        Beat(15.0, "wide Baixa", *BAIXA, 1200, -1000, 1420, 27),
        Beat(23.0, "wide University", *UNIVERSITY, 1000, -800, 1360, 26),
        Beat(31.0, "wide University NE", *UNIVERSITY, 900, 900, 1400, 27),
        Beat(38.0, "wide finish N", *UNIVERSITY, 200, 1400, 1460, 28),
    ]


def orbit_beats() -> list[Beat]:
    # A crescent orbit around the University from south to north-east.
    # We deliberately skip the due-east arc where the prison would sit near frame centre.
    return [
        Beat(0.0,  "orbit S", *UNIVERSITY, 0, -1400, 1350, 28),
        Beat(8.0,  "orbit SE", *UNIVERSITY, 700, -1200, 1320, 27),
        Beat(16.0, "orbit ESE", *UNIVERSITY, 1100, -700, 1300, 27),
        Beat(24.0, "orbit NE", *UNIVERSITY, 900, 900, 1320, 27),
        Beat(32.0, "orbit NNE", *UNIVERSITY, 500, 1250, 1360, 28),
        Beat(38.0, "orbit N", *UNIVERSITY, 200, 1400, 1420, 29),
    ]


def reveal_beats() -> list[Beat]:
    # Focus story: Mondego -> Baixa -> University. Camera descends slightly while the POI moves uphill.
    return [
        Beat(0.0,  "reveal establishing", *MONDEGO, -1650, -1450, 1650, 33),
        Beat(7.0,  "reveal river", *MONDEGO, -1250, -1150, 1500, 31),
        Beat(14.0, "reveal transition", -8.4307, 40.2050, 65, -900, -1100, 1380, 30),
        Beat(21.0, "reveal Baixa", *BAIXA, 1000, -1000, 1260, 27),
        Beat(28.0, "reveal climb", -8.4284, 40.2070, 95, 800, -900, 1150, 26),
        Beat(35.0, "reveal University", *UNIVERSITY, 650, -1000, 1080, 25),
        Beat(41.0, "reveal finale", *UNIVERSITY, 500, -1100, 1120, 25),
    ]


def safe_slider_beats() -> list[Beat]:
    # A macro-slider shot for the "city is a model" concept.
    # The camera stays on the north-east side and moves only gently, while the
    # target pans across the city. This keeps the entire prison exclusion zone
    # far outside the optical axis instead of trying to hide it with blur.
    return [
        Beat(0.0,  "safe Mondego", -8.4340, 40.2025, 55, 800, 1000, 1350, 38),
        Beat(8.0,  "safe river-city", -8.4330, 40.2045, 65, 800, 800, 1320, 38),
        Beat(16.0, "safe Baixa south", -8.4310, 40.2060, 72, 600, 600, 1280, 38),
        Beat(24.0, "safe Baixa", -8.4295, 40.2070, 78, 400, 600, 1240, 38),
        Beat(32.0, "safe Alta west", -8.4285, 40.2080, 95, 400, 400, 1200, 38),
        Beat(40.0, "safe University edge", -8.4280, 40.2085, 105, 400, 400, 1180, 38),
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
        "coimbra-miniature-safe-slider.esp": ("Coimbra miniature - safe slider", safe_slider_beats()),
    }

    for filename, (name, beats) in variants.items():
        if filename == "coimbra-miniature-safe-slider.esp":
            assert_prison_outside_frame(beats)
        project = build_project(name, beats, args.fps, args.width, args.height)
        write_project(out / filename, project)

    plan = {
        "goal": "Make Coimbra read like a physical architectural model.",
        "shared_style": {
            "resolution": [args.width, args.height],
            "fps": args.fps,
            "camera_altitude_m": "1080-1650",
            "fov_deg": "27-33",
            "movement": "slow, high, oblique, long-lens; prison kept outside principal view",
            "postprocess": "moving tilt-shift focus band + mild saturation/contrast",
        },
        "variants": {
            "wide": {
                "duration_s": wide_beats()[-1].sec,
                "idea": "Broad lateral pass across the whole city.",
            },
            "orbit": {
                "duration_s": orbit_beats()[-1].sec,
                "idea": "South-to-north-east crescent around the University, avoiding the prison sector.",
            },
            "reveal": {
                "duration_s": reveal_beats()[-1].sec,
                "idea": "Move the visual focus Mondego -> Baixa -> University.",
                "focus_story": ["Mondego", "Baixa", "Universidade de Coimbra"],
            },
            "safe_slider": {
                "duration_s": safe_slider_beats()[-1].sec,
                "idea": "Macro-slider view from the north-east with a hard prison exclusion margin.",
                "recommended": True,
                "prison_exclusion_radius_m": PRISON_EXCLUSION_RADIUS_M,
            },
        },
    }
    (out / "coimbra-miniature-plan.json").write_text(
        json.dumps(plan, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
