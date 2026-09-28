from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from fetch_dgt_highres_bridge import (
    STAC_SEARCH,
    authenticate,
    latest_only,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_bridge.json"
OUT = ROOT / "data" / "raw" / "dgt_laz"
MANIFEST = OUT / "download-manifest.json"
COLLECTION = "LAZ"


def laz_asset(feature: dict):
    for asset in feature.get("assets", {}).values():
        href = asset.get("href")
        ctype = (asset.get("type") or "").lower()
        clean = href.lower().split("?")[0] if href else ""
        if href and (
            "laszip" in ctype
            or clean.endswith(".laz")
            or clean.endswith(".las")
        ):
            return href
    return None


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    bbox = cfg["bbox_wgs84"]
    user = os.getenv("DGT_USER", "").strip()
    password = os.getenv("DGT_PASSWORD", "")
    if not user or not password:
        raise SystemExit("DGT_USER and DGT_PASSWORD are required for LAZ download")

    session = authenticate(user, password)
    response = session.post(
        STAC_SEARCH,
        json={"bbox": bbox, "limit": 1000, "collections": [COLLECTION]},
        timeout=90,
    )
    response.raise_for_status()
    features = latest_only(response.json().get("features", []))
    assets = []
    for feature in features:
        href = laz_asset(feature)
        if href:
            assets.append((feature.get("id", "tile"), href))

    if not assets:
        raise RuntimeError(f"No DGT {COLLECTION} assets found for {bbox}")

    OUT.mkdir(parents=True, exist_ok=True)
    evidence = []
    for index, (feature_id, href) in enumerate(assets, start=1):
        clean = href.split("?")[0]
        suffix = ".laz" if clean.lower().endswith(".laz") else ".las"
        output = OUT / f"{feature_id}{suffix}"
        if not output.exists() or output.stat().st_size == 0:
            last_error = None
            for attempt in range(1, 4):
                try:
                    print(f"[{index}/{len(assets)}] {feature_id}, attempt {attempt}")
                    with session.get(href, stream=True, timeout=300) as download:
                        download.raise_for_status()
                        ctype = download.headers.get("content-type", "").lower()
                        if "text/html" in ctype:
                            raise RuntimeError("DGT returned HTML instead of LAZ")
                        with output.open("wb") as handle:
                            for chunk in download.iter_content(1024 * 1024):
                                if chunk:
                                    handle.write(chunk)
                    break
                except Exception as exc:
                    last_error = exc
                    output.unlink(missing_ok=True)
                    time.sleep(attempt * 3)
            else:
                raise RuntimeError(f"Failed {feature_id}: {last_error!r}")

        evidence.append(
            {
                "feature_id": feature_id,
                "file": output.relative_to(ROOT).as_posix(),
                "bytes": output.stat().st_size,
            }
        )

    manifest = {
        "source": "DGT LiDAR raw point cloud",
        "collection": COLLECTION,
        "bbox_wgs84": bbox,
        "tile_count": len(evidence),
        "total_bytes": sum(item["bytes"] for item in evidence),
        "tiles": evidence,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
