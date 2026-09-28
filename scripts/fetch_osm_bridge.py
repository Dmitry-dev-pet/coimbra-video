from __future__ import annotations

import json
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OUT = ROOT / "data" / "osm" / "coimbra-route.json"


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    west, south, east, north = cfg["bbox_wgs84"]
    bbox = f"{south},{west},{north},{east}"

    query = f"""
[out:json][timeout:120];
(
  way["building"]({bbox});
  way["highway"]({bbox});
);
out body;
>;
out skel qt;
""".strip()

    headers = {
        "User-Agent": "apatch-blender-coimbra-demo/0.1 (+https://github.com/Dmitry-dev-pet/coimbra-video)"
    }

    errors = []
    for endpoint in cfg["overpass_endpoints"]:
        for attempt in range(1, 4):
            try:
                print(f"Overpass: {endpoint} attempt {attempt}")
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=180,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data.get("elements"), list):
                    raise RuntimeError("Overpass JSON has no elements list")

                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(data))
                ways = [e for e in data["elements"] if e.get("type") == "way"]
                buildings = [w for w in ways if "building" in w.get("tags", {})]
                roads = [w for w in ways if "highway" in w.get("tags", {})]
                print(
                    f"Wrote {OUT}: {len(data['elements'])} elements, "
                    f"{len(buildings)} building ways, {len(roads)} road ways"
                )
                return
            except Exception as exc:
                errors.append(f"{endpoint} attempt {attempt}: {exc!r}")
                time.sleep(attempt * 3)

    raise SystemExit("All Overpass endpoints failed:\n" + "\n".join(errors))


if __name__ == "__main__":
    main()
