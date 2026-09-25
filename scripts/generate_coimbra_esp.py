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

# Route: Rua Sanches da Gama -> Quinta da Portela.
# Each tuple is (longitude, latitude, camera altitude in metres).
#
# We begin just north-west of Sanches da Gama, pass over the street,
# descend gradually across the south-east side of Coimbra and finish
# over/just beyond Quinta da Portela.
PATH = [
    (-8.41820, 40.20240, 520.0),
    (-8.41597, 40.20071, 480.0),  # Rua Sanches da Gama
    (-8.41375, 40.19805, 450.0),
    (-8.41175, 40.19505, 420.0),
    (-8.40955, 40.19210, 390.0),
    (-8.40735, 40.18935, 360.0),
    (-8.40555, 40.18705, 335.0),
    (-8.40415, 40.18495, 315.0),  # Quinta da Portela area
]

# Extra look-ahead point toward Portela do Mondego. It is not a camera
# position; it keeps the final frames looking forward instead of pitching
# straight down at the last keyframe.
FINAL_LOOK_AT = (-8.39934, 40.18492, 55.0)
GROUND_TARGET_ALT = 80.0


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


def tilt_to_target(
    lon: float,
    lat: float,
    altitude: float,
    target_lon: float,
    target_lat: float,
    target_alt: float,
) -> float:
    dx, dy = metres_between(lon, lat, target_lon, target_lat)
    horizontal = math.hypot(dx, dy)
    vertical = max(30.0, altitude - target_alt)
    # Earth Studio convention used by public ESP generators:
    # 0 degrees = straight down, 90 degrees = horizon.
    return math.degrees(math.atan2(horizontal, vertical))


def camera_targets() -> list[tuple[float, float, float]]:
    targets: list[tuple[float, float, float]] = []
    for i in range(len(PATH)):
        # Look roughly two camera keyframes ahead. This makes the movement feel
        # like a real fly-through instead of a camera orbiting one fixed POI.
        j = min(i + 2, len(PATH) - 1)
        if i >= len(PATH) - 2:
            targets.append(FINAL_LOOK_AT)
        else:
            lon, lat, _ = PATH[j]
            targets.append((lon, lat, GROUND_TARGET_ALT))
    return targets


def unwrap_angles(values: list[float]) -> list[float]:
    """Avoid interpolation taking the long way around at 0/360 degrees."""
    if not values:
        return []
    out = [values[0]]
    for value in values[1:]:
        candidate = value
        while candidate - out[-1] > 180.0:
            candidate -= 360.0
        while candidate - out[-1] < -180.0:
            candidate += 360.0
        out.append(candidate)
    return out


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

    targets = camera_targets()
    pans = []
    tilts = []
    for (lon, lat, alt), (target_lon, target_lat, target_alt) in zip(PATH, targets):
        pans.append(bearing_deg(lon, lat, target_lon, target_lat))
        tilts.append(
            tilt_to_target(lon, lat, alt, target_lon, target_lat, target_alt)
        )

    pans = unwrap_angles(pans)

    # Pan may go slightly below 0 or above 360 after unwrapping. Earth Studio
    # accepts normalized values outside 0..1 for smooth interpolation, while
    # retaining the declared 0..360 value range.
    pan_values = [rel(v, MIN_PAN, MAX_PAN) for v in pans]
    tilt_values = [rel(v, MIN_TILT, MAX_TILT) for v in tilts]

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
    ap = argparse.ArgumentParser(
        description="Generate the Sanches da Gama -> Quinta da Portela Earth Studio project."
    )
    ap.add_argument("--output", default="output/coimbra-sanches-portela.esp")
    ap.add_argument("--name", default="Coimbra - Sanches da Gama to Portela")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    project = build_project(args.name, args.fps, args.seconds, args.width, args.height)
    out.write_text(json.dumps(project, indent=2), encoding="utf-8")

    # Re-open so CI catches malformed JSON.
    json.loads(out.read_text(encoding="utf-8"))
    print(f"Wrote {out}")
    print(f"Frames: {project['settings']['duration']} @ {args.fps} fps")
    print(f"Camera keyframes: {len(PATH)}")
    print("Route: Rua Sanches da Gama -> Quinta da Portela")


if __name__ == "__main__":
    main()
