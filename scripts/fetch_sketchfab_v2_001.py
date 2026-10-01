from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_v2_001.json"
OUT = ROOT / "bridge_output_v2_001" / "photogrammetry"
ARCHIVE = OUT / "coimbra-sketchfab-download.bin"
SOURCE = OUT / "source"
MANIFEST = OUT / "source-manifest.json"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    source = cfg["photogrammetry"]
    uid = source["model_uid"]

    token = os.getenv("SKETCHFAB_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "SKETCHFAB_TOKEN is required. Sketchfab's Download API requires an "
            "authenticated user even for downloadable Creative Commons models."
        )

    api = source["download_api"].format(uid=uid)
    response = None
    auth_mode = None
    # Sketchfab accepts OAuth access tokens with Bearer auth and Data API tokens
    # with Token auth. Try both without ever printing the credential.
    for mode in ("Bearer", "Token"):
        candidate = requests.get(
            api,
            headers={
                "Authorization": f"{mode} {token}",
                "User-Agent": "coimbra-video/v2-001",
                "Accept": "application/json",
            },
            timeout=60,
        )
        if candidate.status_code == 200:
            response = candidate
            auth_mode = mode.lower()
            break
        if candidate.status_code not in (401, 403):
            raise RuntimeError(
                f"Sketchfab Download API failed with HTTP {candidate.status_code}"
            )
    if response is None:
        raise RuntimeError(
            "Sketchfab rejected SKETCHFAB_TOKEN as both OAuth Bearer and API Token"
        )
    payload = response.json()

    selected_name = None
    selected = None
    for name in ("gltf", "glb"):
        candidate = payload.get(name)
        if candidate and candidate.get("url"):
            selected_name = name
            selected = candidate
            break
    if selected is None:
        raise RuntimeError(
            "Sketchfab returned no glTF/GLB download for the configured model"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    with requests.get(selected["url"], stream=True, timeout=300) as download:
        download.raise_for_status()
        with ARCHIVE.open("wb") as handle:
            for chunk in download.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)

    if ARCHIVE.stat().st_size < 1024 * 1024:
        raise RuntimeError("Downloaded Sketchfab asset is unexpectedly small")

    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    SOURCE.mkdir(parents=True)

    extracted = False
    if zipfile.is_zipfile(ARCHIVE):
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive.extractall(SOURCE)
        extracted = True
    elif selected_name == "glb":
        shutil.copy2(ARCHIVE, SOURCE / "scene.glb")
    else:
        raise RuntimeError("Expected a ZIP archive for Sketchfab glTF download")

    candidates = sorted(SOURCE.rglob("scene.gltf"))
    candidates += sorted(SOURCE.rglob("*.glb"))
    candidates += sorted(SOURCE.rglob("*.gltf"))
    if not candidates:
        raise RuntimeError("Downloaded Sketchfab asset contains no glTF/GLB scene")

    model_path = candidates[0]
    manifest = {
        "version": "coimbra-v2-001-photogrammetry-source-v1",
        "provider": source["provider"],
        "creator": source["creator"],
        "model_name": source["model_name"],
        "model_uid": uid,
        "model_url": source["model_url"],
        "license": source["license"],
        "format": selected_name,
        "auth_mode": auth_mode,
        "archive_bytes": ARCHIVE.stat().st_size,
        "archive_sha256": digest(ARCHIVE),
        "extracted_archive": extracted,
        "scene": model_path.relative_to(ROOT).as_posix(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
