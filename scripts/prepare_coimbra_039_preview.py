#!/usr/bin/env python3
"""Stage only immutable public Coimbra data needed for the 039 browser QA.

No Blender runs, private credentials, CI artifacts or production deployment.
The provenance checks fail closed when the published accepted GLB changes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "web" / "public"
UPSTREAM = "https://dmitry-dev-pet.github.io/coimbra-video"
EXPECTED_BLEND_SHA = "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881"
EXPECTED_GLB_SHA = "c02e245f6c59e5f3ec7999b00c8bfb7acc4f96cc8a6d893f708c060757bb8dfd"
ANCHORS = {
    "sanches-brasil": (-293.37, 851.60),
    "polo-ii": (-168.37, -748.07),
    "portela": (463.44, -912.82),
}
MAX_GLB = 90 * 1024 * 1024


def fetch(url: str, destination: Path, *, max_bytes: int = MAX_GLB) -> dict:
    if not url.startswith(UPSTREAM + "/"):
        raise ValueError("Disallowed origin: " + url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "coimbra-039-public-data-qa/1"})
    with urllib.request.urlopen(request, timeout=75) as response:
        # No cross-origin redirects, in particular no leaked signed URLs.
        if not response.url.startswith(UPSTREAM + "/"):
            raise ValueError("Unexpected redirect: " + response.url)
        declared = response.headers.get("Content-Length")
        if declared is not None and int(declared) > max_bytes:
            raise ValueError("Oversize download: " + url)
        sha = hashlib.sha256()
        total = 0
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
            path = Path(tmp.name)
            try:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > max_bytes:
                        raise ValueError("Payload too large: " + url)
                    tmp.write(block)
                    sha.update(block)
            except BaseException:
                path.unlink(missing_ok=True)
                raise
    path.replace(destination)
    return {"path": destination.relative_to(ROOT).as_posix(), "bytes": total, "sha256": sha.hexdigest()}


def load_json(url: str, path: Path, max_bytes: int = 5 * 1024 * 1024) -> tuple[dict, dict]:
    receipt = fetch(url, path, max_bytes=max_bytes)
    return json.loads(path.read_text(encoding="utf-8")), receipt


def main() -> None:
    manifest, manifest_receipt = load_json(
        UPSTREAM + "/037/data/export-manifest.json",
        PUBLIC / "037" / "data" / "export-manifest.json",
    )
    if manifest.get("source_blend_sha256") != EXPECTED_BLEND_SHA:
        raise ValueError("Published accepted scene SHA changed")
    glb = manifest.get("static_glb") or {}
    if glb.get("sha256") != EXPECTED_GLB_SHA or glb.get("path") != "coimbra-032-frame181.glb":
        raise ValueError("Published GLB does not match pinned accepted 032/037 scene")
    if not (1024 * 1024 < int(glb.get("bytes", 0)) <= MAX_GLB):
        raise ValueError("Unexpected GLB size")

    # Same-origin upstream files only; the accepted 037 GLB remains unmodified.
    glb_dest = PUBLIC / "037" / "data" / glb["path"]
    glb_receipt = fetch(UPSTREAM + "/037/data/" + glb["path"], glb_dest)
    if glb_receipt["sha256"] != EXPECTED_GLB_SHA or glb_receipt["bytes"] != glb["bytes"]:
        raise ValueError("GLB integrity mismatch")
    if glb_dest.read_bytes()[:4] != b"glTF":
        raise ValueError("Not a binary glTF/GLB")
    png_receipt = fetch(
        UPSTREAM + "/037/data/frame-181-reference.png",
        PUBLIC / "037" / "data" / "frame-181-reference.png",
        max_bytes=15 * 1024 * 1024,
    )
    if (PUBLIC / "037" / "data" / "frame-181-reference.png").read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Reference is not PNG")

    index, index_receipt = load_json(
        UPSTREAM + "/data/coimbra/index.json",
        PUBLIC / "data" / "coimbra" / "index.json",
        max_bytes=2 * 1024 * 1024,
    )
    tile_size = index.get("tile_size")
    if index.get("schema_version") != 1 or not isinstance(tile_size, (int, float)) or tile_size <= 0:
        raise ValueError("Unexpected Coimbra 034 static index")
    selected = {}
    for x, y in ANCHORS.values():
        # Floor handles negative Coimbra local coordinates.
        i, j = int(x // tile_size), int(y // tile_size)
        for tile in index.get("tiles", []):
            if abs(tile["i"] - i) <= 1 and abs(tile["j"] - j) <= 1:
                path = tile["path"]
                if not path.startswith("tiles/t_") or not path.endswith(".json") or ".." in path:
                    raise ValueError("Unsafe tile path " + str(path))
                selected[path] = tile
    if len(selected) < 20:
        raise ValueError("Expected 3×3 neighborhoods around each of three anchors")

    def fetch_tile(item: tuple[str, dict]) -> dict:
        name, _ = item
        tile, receipt = load_json(
            UPSTREAM + "/data/coimbra/" + name,
            PUBLIC / "data" / "coimbra" / name,
            max_bytes=3 * 1024 * 1024,
        )
        if not isinstance(tile.get("roads"), list) or not isinstance(tile.get("terrain"), (dict, type(None))):
            raise ValueError("Missing roads/terrain in " + name)
        return {"tile": name, "roads": len(tile["roads"]), **receipt}

    with ThreadPoolExecutor(max_workers=8) as pool:
        tile_receipts = list(pool.map(fetch_tile, sorted(selected.items())))
    for anchor_name, (x, y) in ANCHORS.items():
        i, j = int(x // tile_size), int(y // tile_size)
        selected_neighborhood = [p for p in tile_receipts if
                                 abs(selected[p["tile"]]["i"] - i) <= 1 and
                                 abs(selected[p["tile"]]["j"] - j) <= 1]
        if len(selected_neighborhood) != 9:
            raise ValueError(f"{anchor_name}: incomplete tile neighborhood")
        if not sum(p["roads"] for p in selected_neighborhood):
            raise ValueError(f"{anchor_name}: neighborhood has no OSM roads")

    result = {
        "lane": "coimbra-039-street-qa",
        "source": UPSTREAM,
        "accepted_source_sha256": EXPECTED_BLEND_SHA,
        "static_glb": glb_receipt,
        "reference": png_receipt,
        "manifest": manifest_receipt,
        "index": index_receipt,
        "tile_count": len(tile_receipts),
        "total_roads_across_tiles": sum(tile["roads"] for tile in tile_receipts),
        "anchors": list(ANCHORS),
        "note": "QA-only staged assets, not a new production scene",
    }
    output = ROOT / "web" / "street-qa-evidence" / "source-receipt.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
