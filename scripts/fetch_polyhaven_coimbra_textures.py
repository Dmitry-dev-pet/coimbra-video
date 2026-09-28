from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "textures" / "COIMBRA-005-polyhaven.json"
OUT = ROOT / "data" / "textures" / "polyhaven"
MANIFEST = OUT / "download-manifest.json"
API = "https://api.polyhaven.com"
HEADERS = {
    "User-Agent": "coimbra-video/005-textures (+https://github.com/Dmitry-dev-pet/coimbra-video)",
    "Accept": "application/json",
}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


MAP_KEYS = {
    "diffuse": {"diffuse", "color", "albedo", "basecolor"},
    "rough": {"rough", "roughness"},
    "normal": {"norgl", "normalgl", "normalopengl", "normal"},
}


def pick_map(files: dict, role: str, resolution: str) -> tuple[str, dict]:
    wanted = MAP_KEYS[role]
    node = None
    selected_key = None
    for key, value in files.items():
        if norm(key) in wanted and isinstance(value, dict):
            node = value
            selected_key = key
            break
    if node is None:
        raise RuntimeError(f"Poly Haven map {role!r} not found; keys={sorted(files)}")

    res = node.get(resolution)
    if not isinstance(res, dict):
        raise RuntimeError(
            f"Poly Haven map {selected_key!r} has no {resolution}; "
            f"available={sorted(node)}"
        )

    for extension in ("jpg", "png", "exr"):
        info = res.get(extension)
        if isinstance(info, dict) and info.get("url"):
            return extension, info
    raise RuntimeError(
        f"Poly Haven map {selected_key!r}/{resolution} has no supported format"
    )


def download(url: str, path: Path) -> bytes:
    response = requests.get(url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return response.content


def main() -> None:
    plan = json.loads(PLAN_PATH.read_text())
    resolution = plan["resolution"]
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = {
        "provider": plan["provider"],
        "api": plan["api"],
        "license": plan["license"],
        "resolution": resolution,
        "assets": {},
    }

    for slug in plan["assets"]:
        response = requests.get(
            f"{API}/files/{slug}",
            headers=HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        files = response.json()

        asset_evidence = {}
        for role in plan["maps"]:
            extension, info = pick_map(files, role, resolution)
            target = OUT / slug / f"{slug}_{role}_{resolution}.{extension}"
            content = download(info["url"], target)

            expected_md5 = str(info.get("md5") or "").lower()
            actual_md5 = hashlib.md5(content).hexdigest()
            if expected_md5 and actual_md5 != expected_md5:
                raise RuntimeError(
                    f"MD5 mismatch for {slug}/{role}: "
                    f"{actual_md5} != {expected_md5}"
                )

            asset_evidence[role] = {
                "path": target.relative_to(ROOT).as_posix(),
                "source_url": info["url"],
                "md5": actual_md5,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }

        evidence["assets"][slug] = asset_evidence
        print(f"Fetched {slug}")

    MANIFEST.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
