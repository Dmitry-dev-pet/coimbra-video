from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

ALT_MIN = -500.0
ALT_MAX = 65_117_481.0
FOV_MAX = 178.0

# Approximate route anchors for the real street corridor:
# Sanches da Gama x Rua do Brasil -> Rua do Brasil -> Av. Conego Urbano Duarte
# -> Boavista / Rua Teofilo Braga -> Rua Miguel Bombarda / Polo II
# -> Quinta da Portela -> Rua Princesa Cindazunda.
#
# Coordinates are used as cinematic anchors, not turn-by-turn navigation.
START = (-8.41620, 40.20105)
BRASIL_1 = (-8.41725, 40.19965)
BRASIL_2 = (-8.41865, 40.19805)
URBANO_DUARTE = (-8.42089, 40.19638)
BOAVISTA = (-8.42010, 40.19255)
HOTELARIA = (-8.418881, 40.190243)
POLO_II_NORTH = (-8.41473, 40.18668)
POLO_II_SOUTH = (-8.41239, 40.18478)
PORTELA_ENTRY = (-8.40980, 40.18490)
PORTELA_ROTUNDA = (-8.40730, 40.18520)
PORTELA_CENTER = (-8.40520, 40.18579)
DESTINATION = (-8.4049153, 40.1853055)

ROUTE_ANCHORS = [
    ("Sanches x Brasil", *START),
    ("Rua do Brasil 1", *BRASIL_1),
    ("Rua do Brasil 2", *BRASIL_2),
    ("Av. Conego Urbano Duarte", *URBANO_DUARTE),
    ("Boavista", *BOAVISTA),
    ("Escola Hotelaria / Rua Teofilo Braga", *HOTELARIA),
    ("Polo II / Rua Miguel Bombarda", *POLO_II_NORTH),
    ("Polo II south", *POLO_II_SOUTH),
    ("Quinta da Portela entry", *PORTELA_ENTRY),
    ("Quinta da Portela rotunda", *PORTELA_ROTUNDA),
    ("Quinta da Portela centre", *PORTELA_CENTER),
    ("Rua Princesa Cindazunda", *DESTINATION),
]


@dataclass(frozen=True)
class Beat:
    sec: float
    label: str
    target_lon: float
    target_lat: float
    target_alt: float
    cam_east_m: float
    cam_north_m: float
    cam_alt: float
    fov_deg: float = 50.0


def offset(lon: float, lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    lat2 = lat + north_m / 111_320.0
    lon2 = lon + east_m / (111_320.0 * math.cos(math.radians(lat)))
    return lon2, lat2


def lon_rel(v: float) -> float:
    return (v + 180.0) / 360.0


def lat_rel(v: float) -> float:
    return (v + 90.0) / 180.0


def alt_rel(v: float) -> float:
    return (v - ALT_MIN) / (ALT_MAX - ALT_MIN)


def kf(time: float, value: float, smooth: bool = True) -> dict:
    item = {"time": time, "value": value}
    if smooth:
        item["transitionIn"] = {
            "x": -0.055, "y": 0, "influence": 0.45, "type": "auto"
        }
        item["transitionOut"] = {
            "x": 0.055, "y": 0, "influence": 0.45, "type": "auto"
        }
    return item


def block(type_: str, values: list[tuple[float, float]], *, value: dict | None = None) -> dict:
    initial = values[0][1]
    v = {"relative": initial}
    if value:
        v.update(value)
    return {
        "type": type_,
        "value": v,
        "keyframes": [kf(t, x) for t, x in values],
        "inTimeline": True,
    }


def walking_beats() -> list[Beat]:
    # 52 seconds. Low, patient movement that roughly feels like travelling
    # the route while a drone is free to peel away for reveals.
    return [
        # Opening orbit around Sanches x Rua do Brasil.
        Beat(0.0,  "start orbit A", *START, 105.0, -100,  20, 245, 54),
        Beat(2.0,  "start orbit B", *START, 105.0,  -55,  95, 250, 52),
        Beat(4.2,  "start orbit C", *START, 105.0,   45, 105, 250, 50),
        Beat(6.0,  "exit orbit",   *BRASIL_1, 100.0,  -55,  55, 240, 49),

        # Follow Rua do Brasil like a moving pedestrian / car companion.
        Beat(9.0,  "Brasil follow", *BRASIL_2, 95.0,  -50,  35, 235, 48),

        # First cinematic reveal: peel away west and rise before returning.
        Beat(13.0, "Urbano reveal A", *URBANO_DUARTE, 90.0, -145,  85, 330, 55),
        Beat(16.5, "Urbano reveal B", *BOAVISTA, 85.0, -105,  70, 300, 52),

        # Back to a lower tracking shot.
        Beat(20.0, "Boavista follow", *BOAVISTA, 85.0,  -45,  35, 220, 47),
        Beat(23.5, "Hotelaria follow", *HOTELARIA, 80.0, -40,  45, 215, 46),

        # Polo II: camera leaves route for a side arc while target continues.
        Beat(27.0, "Polo approach", *POLO_II_NORTH, 85.0, -70,  20, 225, 47),
        Beat(30.0, "Polo arc A",    *POLO_II_NORTH, 85.0, -125, -25, 285, 52),
        Beat(33.0, "Polo arc B",    *POLO_II_SOUTH, 80.0,  -15, -110, 290, 52),
        Beat(35.5, "Polo exit",     *POLO_II_SOUTH, 80.0,   65, -45, 235, 48),

        # Enter Portela and return to a route-following feel.
        Beat(39.0, "Portela entry",   *PORTELA_ENTRY, 70.0,  -35,  45, 205, 47),
        Beat(42.0, "Portela rotunda", *PORTELA_ROTUNDA, 68.0, -40, 35, 195, 46),
        Beat(44.0, "Portela centre",  *PORTELA_CENTER, 65.0, -35, 30, 185, 45),

        # Pass the destination and turn around it instead of simply stopping.
        Beat(46.0, "destination pass", *DESTINATION, 65.0, -85,   0, 185, 46),
        Beat(48.0, "destination orbit A", *DESTINATION, 65.0, -45,  80, 190, 48),
        Beat(50.0, "destination orbit B", *DESTINATION, 65.0,  55,  75, 190, 48),
        Beat(52.0, "destination hold",    *DESTINATION, 65.0,  85,  10, 180, 45),
    ]


def driving_beats() -> list[Beat]:
    # Same visual language, compressed to 34 seconds and slightly higher/faster.
    source = walking_beats()
    duration = 34.0
    scale = duration / source[-1].sec
    out = []
    for b in source:
        out.append(
            Beat(
                b.sec * scale,
                b.label,
                b.target_lon,
                b.target_lat,
                b.target_alt,
                b.cam_east_m * 1.08,
                b.cam_north_m * 1.08,
                b.cam_alt + 25.0,
                min(58.0, b.fov_deg + 2.0),
            )
        )
    return out


def project_from_beats(name: str, beats: list[Beat], fps: int, width: int, height: int) -> dict:
    duration_s = beats[-1].sec
    n_frames = int(round(duration_s * fps))

    camera = []
    for b in beats:
        cam_lon, cam_lat = offset(
            b.target_lon, b.target_lat, b.cam_east_m, b.cam_north_m
        )
        camera.append((b.sec / duration_s, cam_lon, cam_lat, b.cam_alt, b.fov_deg))

    target = [
        (b.sec / duration_s, b.target_lon, b.target_lat, b.target_alt)
        for b in beats
    ]

    lon_vals = [(t, lon_rel(lon)) for t, lon, lat, alt, fov in camera]
    lat_vals = [(t, lat_rel(lat)) for t, lon, lat, alt, fov in camera]
    alt_vals = [(t, alt_rel(alt)) for t, lon, lat, alt, fov in camera]
    fov_vals = [(t, fov / FOV_MAX) for t, lon, lat, alt, fov in camera]

    poi_lon_vals = [(t, lon_rel(lon)) for t, lon, lat, alt in target]
    poi_lat_vals = [(t, lat_rel(lat)) for t, lon, lat, alt in target]
    poi_alt_vals = [(t, alt_rel(alt)) for t, lon, lat, alt in target]

    position = {
        "type": "position",
        "inTimeline": True,
        "attributes": [
            block("longitude", lon_vals),
            block("latitude", lat_vals),
            block(
                "altitude",
                alt_vals,
                value={
                    "maxValueRange": ALT_MAX,
                    "minValueRange": ALT_MIN,
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
                    block("longitudePOI", poi_lon_vals),
                    block("latitudePOI", poi_lat_vals),
                    block(
                        "altitudePOI",
                        poi_alt_vals,
                        value={
                            "maxValueRange": ALT_MAX,
                            "minValueRange": ALT_MIN,
                            "logarithmic": False,
                        },
                    ),
                ],
            },
            {"type": "influence", "value": {"relative": 1}, "inTimeline": True},
        ],
    }

    return {
        "modelVersion": 18,
        "settings": {
            "name": name,
            "frameRate": fps,
            "dimensions": {"width": width, "height": height},
            "duration": n_frames,
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
                "duration": n_frames,
                "attributes": [
                    {
                        "type": "cameraGroup",
                        "inTimeline": True,
                        "attributes": [
                            {
                                "type": "cameraPositionGroup",
                                "inTimeline": True,
                                "attributes": [position],
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
                                    block("fov", fov_vals),
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
                                    {"type": "sunVisibility", "value": {}},
                                    {"type": "worldTime", "value": {"relative": 0.5}},
                                ],
                            },
                            {
                                "type": "cloudGroup",
                                "attributes": [
                                    {"type": "cloudVisibility", "value": {}},
                                    {"type": "cloudopacity", "value": {}},
                                    {"type": "cloudheight", "value": {}},
                                    {"type": "clouddate", "value": {"relative": 0.95}},
                                ],
                            },
                            {
                                "type": "starsPlanetsGroup",
                                "attributes": [{"type": "starsEnabled", "value": {}}],
                            },
                            {"type": "buildingsEnabled", "value": {}},
                        ],
                    },
                ],
                "cameraExport": {"logarithmic": False, "modelVersion": 2},
            }
        ],
        "playbackManager": {"range": {"start": 0, "end": n_frames}},
    }


def write(path: Path, project: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project, indent=2), encoding="utf-8")
    check = json.loads(path.read_text(encoding="utf-8"))
    assert check["modelVersion"] == 18
    assert check["settings"]["duration"] > 0
    print(f"Wrote {path}: {check['settings']['duration']} frames")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate cinematic Sanches da Gama -> Princesa Cindazunda Earth Studio projects."
    )
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    out = Path(args.output_dir)
    walk = project_from_beats(
        "Coimbra route - walking drone",
        walking_beats(),
        args.fps,
        args.width,
        args.height,
    )
    drive = project_from_beats(
        "Coimbra route - driving drone",
        driving_beats(),
        args.fps,
        args.width,
        args.height,
    )

    write(out / "coimbra-route-walking-drone.esp", walk)
    write(out / "coimbra-route-driving-drone.esp", drive)

    route_plan = {
        "route_anchors": [
            {"name": name, "lon": lon, "lat": lat}
            for name, lon, lat in ROUTE_ANCHORS
        ],
        "walking_seconds": walking_beats()[-1].sec,
        "driving_seconds": driving_beats()[-1].sec,
        "notes": [
            "Camera path and camera target are animated independently.",
            "Opening orbit at Sanches da Gama x Rua do Brasil.",
            "Wide reveal near Avenida Conego Urbano Duarte.",
            "Side arc around Polo II.",
            "Final pass and half-orbit at Rua Princesa Cindazunda.",
            "Destination anchor is street-level approximate; inspect the exact number 16 visually in Earth Studio.",
        ],
    }
    (out / "route-plan.json").write_text(
        json.dumps(route_plan, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
