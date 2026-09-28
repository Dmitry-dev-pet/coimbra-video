from __future__ import annotations

import json
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OUT = ROOT / "data" / "osm" / "coimbra-oss-rich.json"


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    west, south, east, north = cfg["bbox_wgs84"]
    bbox = f"{south},{west},{north},{east}"

    # Richer than the production bridge fetch: preserve tagged nodes and urban
    # area/POI semantics so MOSAIQ and OSM2World get a fair input.
    query = f"""
[out:json][timeout:180];
(
  way["building"]({bbox});
  relation["building"]({bbox});
  way["highway"]({bbox});
  way["landuse"]({bbox});
  relation["landuse"]({bbox});
  way["leisure"]({bbox});
  relation["leisure"]({bbox});
  way["natural"]({bbox});
  relation["natural"]({bbox});
  node["natural"="tree"]({bbox});
  node["highway"="crossing"]({bbox});
  node["crossing"]({bbox});
  node["highway"="street_lamp"]({bbox});
  node["amenity"]({bbox});
  node["shop"]({bbox});
  node["tourism"]({bbox});
  node["barrier"]({bbox});
  node["railway"]({bbox});
);
out body;
>;
out body qt;
""".strip()

    headers = {
        "User-Agent": (
            "coimbra-video-oss-benchmark/0.1 "
            "(+https://github.com/Dmitry-dev-pet/coimbra-video)"
        )
    }

    errors = []
    for endpoint in cfg["overpass_endpoints"]:
        for attempt in range(1, 4):
            try:
                print(f"Overpass rich: {endpoint} attempt {attempt}")
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=240,
                )
                response.raise_for_status()
                data = response.json()
                elements = data.get("elements")
                if not isinstance(elements, list):
                    raise RuntimeError("Overpass JSON has no elements list")

                # Overpass recursion can return the same element through several
                # selected parents. Keep one copy, preferring a tagged record.
                by_key = {}
                for element in elements:
                    key = (element.get("type"), element.get("id"))
                    old = by_key.get(key)
                    if old is None or (
                        len(element.get("tags") or {}) > len(old.get("tags") or {})
                    ):
                        by_key[key] = element
                data["elements"] = list(by_key.values())

                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(data))
                counts = {
                    "elements": len(data["elements"]),
                    "nodes": sum(e.get("type") == "node" for e in data["elements"]),
                    "ways": sum(e.get("type") == "way" for e in data["elements"]),
                    "relations": sum(e.get("type") == "relation" for e in data["elements"]),
                    "tagged_nodes": sum(
                        e.get("type") == "node" and bool(e.get("tags"))
                        for e in data["elements"]
                    ),
                    "crossings": sum(
                        e.get("type") == "node"
                        and (
                            (e.get("tags") or {}).get("highway") == "crossing"
                            or bool((e.get("tags") or {}).get("crossing"))
                        )
                        for e in data["elements"]
                    ),
                    "street_lamps": sum(
                        e.get("type") == "node"
                        and (e.get("tags") or {}).get("highway") == "street_lamp"
                        for e in data["elements"]
                    ),
                }
                print(json.dumps(counts, indent=2))
                return
            except Exception as exc:
                errors.append(f"{endpoint} attempt {attempt}: {exc!r}")
                time.sleep(attempt * 3)

    raise SystemExit("All Overpass endpoints failed:\n" + "\n".join(errors))


if __name__ == "__main__":
    main()
