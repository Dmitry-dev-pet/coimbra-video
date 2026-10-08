"""Prepare one checked-in composite action; never select or execute user code."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from materialize import PackageError, materialize


def fixed_environment(package: Path, lane: str) -> dict[str, str]:
    payload = json.loads((package / "lanes.json").read_text(encoding="utf-8"))
    if payload.get("version") != 1 or lane not in payload.get("lanes", {}):
        raise PackageError("Unknown project action")
    values = payload["lanes"][lane]["env"]
    if not isinstance(values, dict) or not values:
        raise PackageError("Missing fixed project environment")
    for key, value in values.items():
        if not re.fullmatch(r"(?:COIMBRA_[A-Z0-9_]+|V2_SOURCE_RUN_ID)", key):
            raise PackageError("Unsupported project environment key")
        if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9:._-]{1,128}", value):
            raise PackageError("Unsafe project environment value")
    return values


if __name__ == "__main__":
    package = Path(__file__).resolve().parent
    action = Path(os.environ["COIMBRA_ACTION_DIR"]).resolve(strict=True)
    if action.parent != package or not (action / "action.yml").is_file():
        raise SystemExit("Action is outside the checked-in project package")
    values = fixed_environment(package, action.name)
    workspace = Path(os.environ["GITHUB_WORKSPACE"])
    if Path.cwd().resolve() != workspace.resolve():
        raise SystemExit("Unexpected execution workspace")
    materialize(package, workspace)
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as output:
        for key, value in sorted(values.items()):
            output.write(f"{key}={value}\n")
    print(f"Prepared fixed project action: {action.name}")
