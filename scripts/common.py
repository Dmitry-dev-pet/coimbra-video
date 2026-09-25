from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra.json"
RAW_MDS = ROOT / "data" / "raw" / "mds"
PROCESSED = ROOT / "data" / "processed"
OUTPUT = ROOT / "output"

def load_config() -> dict:
    return json.loads(CONFIG.read_text())

def ensure_dirs() -> None:
    RAW_MDS.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
