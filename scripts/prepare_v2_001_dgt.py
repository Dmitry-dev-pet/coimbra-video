from __future__ import annotations

import json
from pathlib import Path

import fetch_dgt_highres_bridge as highres
import fetch_dgt_ortho_bridge as ortho
import prepare_dgt_highres_bridge as prepare


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_v2_001.json"
OUT = ROOT / "bridge_output_v2_001" / "dgt"


def configure_modules() -> None:
    ortho.CONFIG = CONFIG
    ortho.OUT = OUT / "ortho" / "coimbra-v2-001-ortho-2025.jpg"

    highres.CONFIG = CONFIG
    highres.RAW_ROOT = OUT / "raw"

    prepare.CONFIG = CONFIG
    prepare.RAW_ROOT = OUT / "raw"
    prepare.OUT = OUT / "prepared"
    prepare.MDT_DIR = prepare.RAW_ROOT / "mdt-50cm"
    prepare.MDS_DIR = prepare.RAW_ROOT / "mds-50cm"
    prepare.MDT_TIF = prepare.OUT / "coimbra-v2-001-mdt-50cm.tif"
    prepare.MDS_TIF = prepare.OUT / "coimbra-v2-001-mds-50cm.tif"
    prepare.TERRAIN_NPZ = prepare.OUT / "coimbra-v2-001-terrain-2m.npz"
    prepare.HAG_NPZ = prepare.OUT / "coimbra-v2-001-height-above-ground-1m.npz"
    prepare.META_JSON = prepare.OUT / "coimbra-v2-001-highres-manifest.json"


def main() -> None:
    if not CONFIG.is_file():
        raise SystemExit(f"Missing V2 config: {CONFIG}")

    OUT.mkdir(parents=True, exist_ok=True)
    configure_modules()

    # Orthophoto is public WMS. High-resolution MDT/MDS uses the existing safe DGT
    # acquisition path and consumes DGT_USER/DGT_PASSWORD only when anonymous CDD
    # access is unavailable.
    ortho.main()
    generated_ortho_meta = ortho.OUT.parent / "bridge_ortho_2025.json"
    ortho_meta = ortho.OUT.parent / "coimbra-v2-001-ortho-2025.json"
    if generated_ortho_meta != ortho_meta:
        generated_ortho_meta.replace(ortho_meta)

    highres.main()
    prepare.main()

    payload = {
        "version": "coimbra-v2-001-dgt-v1",
        "config": CONFIG.relative_to(ROOT).as_posix(),
        "ortho": ortho.OUT.relative_to(ROOT).as_posix(),
        "ortho_metadata": ortho_meta.relative_to(ROOT).as_posix(),
        "highres_manifest": prepare.META_JSON.relative_to(ROOT).as_posix(),
        "terrain": prepare.TERRAIN_NPZ.relative_to(ROOT).as_posix(),
        "height_above_ground": prepare.HAG_NPZ.relative_to(ROOT).as_posix(),
        "mdt": prepare.MDT_TIF.relative_to(ROOT).as_posix(),
        "mds": prepare.MDS_TIF.relative_to(ROOT).as_posix(),
    }
    path = OUT / "v2-001-dgt-manifest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
