from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

MIN_LON, MAX_LON = -180.0, 180.0
MIN_LAT, MAX_LAT = -90.0, 90.0
MIN_ALT, MAX_ALT = -500.0, 65117481.0
MIN_TILT, MAX_TILT = 0.0, 180.0
MIN_PAN, MAX_PAN = 0.0, 360.0

# Cinematic south-west -> historic-centre approach.
# lon, lat, camera altitude metres.
PATH = [
    (-8.4450, 40.1948, 900.0),
    (-8.4405, 40.1975, 840.0),
    (-8.4360, 40.2003, 790.0),
    (-8.4318, 40.2027, 735.0),
    (-8.4284, 40.2048, 690.0),
    (-8.4254, 40.2064, 650.0),
    (-8.4224, 40.2080, 630.0),
]

# Aim roughly at Alta / Universidade, keeping Baixa and Mondego in the composition.
TARGET_LON = -8.4265
TARGET_LAT = 40.2079
TARGET_ALT = 115.0


def rel(value: float, lo: float, hi: float) -> float:
    return (value - lo) / (hi - lo)


def metres_between(lon1: float, lat1: float, lon2: float, lat2: float) -> tuple[float, float]:
    r = 6371000.0
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    dx = math.radians(lon2 - lon1) * r * math.cos(mean_lat)
    dy = math.radians(lat2 - lat1) * r
    return dx, dy


def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    dx, dy = metres_between(lon1, lat1, lon2, lat2)
    return math.degrees(math.atan2(dx, dy)) % 360.0


def tilt_deg(lon: float, lat: float, altitude: float) -> float:
    dx, dy = metres_between(lon, lat, TARGET_LON, TARGET_LAT)
    horizontal = math.hypot(dx, dy)
    vertical = max(50.0, altitude - TARGET_ALT)
    # Earth Studio convention used by open-source ESP generators:
    # 0° = straight down, 90° = horizon.
    return math.degrees(math.atan2(horizontal, vertical))


def keyframes(values: list[float]) -> list[dict]:
    n = len(values)
    return [
        {"time": i / (n - 1), "value": value}
        for i, value in enumerate(values)
    ]


def attribute(type_: str, values: list[float], **value_fields) -> dict:
    value = {"relative": values[0]}
    value.update(value_fields)
    return {
        "type": type_,
        "value": value,
        "keyframes": keyframes(values),
        "inTimeline": True,
    }


def build_project(name: str, fps: int, seconds: float, width: int, height: int) -> dict:
    frames = int(round(fps * seconds))

    lon_values = [rel(lon, MIN_LON, MAX_LON) for lon, lat, alt in PATH]
    lat_values = [rel(lat, MIN_LAT, MAX_LAT) for lon, lat, alt in PATH]
    alt_values = [rel(alt, MIN_ALT, MAX_ALT) for lon, lat, alt in PATH]

    pan_deg = [bearing_deg(lon, lat, TARGET_LON, TARGET_LAT) for lon, lat, alt in PATH]
    tilt_degrees = [tilt_deg(lon, lat, alt) for lon, lat, alt in PATH]
    pan_values = [rel(v, MIN_PAN, MAX_PAN) for v in pan_deg]
    tilt_values = [rel(v, MIN_TILT, MAX_TILT) for v in tilt_degrees]

    project = {
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
                                "attributes": [
                                    {
                                        "type": "position",
                                        "inTimeline": True,
                                        "attributes": [
                                            attribute(
                                                "longitude",
                                                lon_values,
                                                minValueRange=MIN_LON,
                                                maxValueRange=MAX_LON,
                                            ),
                                            attribute(
                                                "latitude",
                                                lat_values,
                                                minValueRange=MIN_LAT,
                                                maxValueRange=MAX_LAT,
                                            ),
                                            attribute(
                                                "altitude",
                                                alt_values,
                                                minValueRange=MIN_ALT,
                                                maxValueRange=MAX_ALT,
                                                logarithmic=False,
                                            ),
                                        ],
                                    }
                                ],
                            },
                            {
                                "type": "cameraRotationGroup",
                                "inTimeline": True,
                                "attributes": [
                                    attribute(
                                        "rotationX",
                                        pan_values,
                                        minValueRange=MIN_PAN,
                                        maxValueRange=MAX_PAN,
                                    ),
                                    attribute("rotationY", tilt_values),
                                    {"type": "rotationZ", "value": {"relative": 0}},
                                ],
                            },
                            {
                                "type": "cameraLensGroup",
                                "attributes": [
                                    {"type": "fov", "value": {}},
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
        "playbackManager": {"range": {"start": 0, "end": frames}},
    }
    return project


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a Coimbra Google Earth Studio .esp project.")
    ap.add_argument("--output", default="output/coimbra-cinematic.esp")
    ap.add_argument("--name", default="Coimbra cinematic")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    project = build_project(args.name, args.fps, args.seconds, args.width, args.height)
    out.write_text(json.dumps(project, indent=2), encoding="utf-8")

    # Re-open it so CI also catches malformed JSON.
    json.loads(out.read_text(encoding="utf-8"))
    print(f"Wrote {out}")
    print(f"Frames: {project['settings']['duration']} @ {args.fps} fps")
    print(f"Camera keyframes: {len(PATH)}")


if __name__ == "__main__":
    main()
