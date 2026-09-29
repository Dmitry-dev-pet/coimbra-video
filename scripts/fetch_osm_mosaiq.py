from __future__ import annotations

import json
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OUT = ROOT / "data" / "osm" / "coimbra-route-mosaiq.osm"


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    west, south, east, north = map(float, cfg["bbox_wgs84"])
    bbox = f"{south},{west},{north},{east}"

    query = f"""
[out:xml][timeout:180];
(
  nwr["building"]({bbox});
  nwr["building:part"]({bbox});
  way["highway"]({bbox});
  nwr["landuse"]({bbox});
  nwr["leisure"]({bbox});
  nwr["amenity"]({bbox});
  nwr["natural"]({bbox});
  nwr["surface"]({bbox});
  node["highway"]({bbox});
  node["crossing"]({bbox});
  node["entrance"]({bbox});
  node["railway"]({bbox});
);
out body;
>;
out skel qt;
""".strip()

    headers = {
        "User-Agent": (
            "coimbra-video/mosaiq-ab "
            "(+https://github.com/Dmitry-dev-pet/coimbra-video)"
        )
    }

    errors: list[str] = []
    for endpoint in cfg["overpass_endpoints"]:
        for attempt in range(1, 4):
            try:
                print(f"MOSAIQ Overpass: {endpoint} attempt {attempt}")
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=240,
                )
                response.raise_for_status()
                text = response.text
                if "<osm" not in text:
                    raise RuntimeError("Overpass response is not OSM XML")
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(text)
                print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
                return
            except Exception as exc:
                errors.append(f"{endpoint} attempt {attempt}: {exc!r}")
                time.sleep(attempt * 3)

    raise SystemExit("All Overpass endpoints failed:\n" + "\n".join(errors))


if __name__ == "__main__":
    main()
