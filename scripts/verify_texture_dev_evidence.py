from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_PROBE = "coimbra-texture-dev-probe-v1\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--probe", required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text())
    failures: list[str] = []

    if Path(args.probe).read_text() != EXPECTED_PROBE:
        failures.append("falsification probe changed")
    if report.get("contract") != "COIMBRA-BRIDGE-005-TEXTURES":
        failures.append("wrong contract report")
    if report.get("status") != "PASS":
        failures.append("semantic verifier did not pass")

    checks = report.get("checks") or {}
    for name in (
        "apatch_governance_binding",
        "protected_static_unchanged",
        "protected_animation_unchanged",
        "expected_world",
        "expected_camera_path",
        "expected_camera_dof",
        "expected_light:Bridge_VisualGoldenKey",
        "expected_render",
    ):
        if (checks.get(name) or {}).get("pass") is not True:
            failures.append(f"{name} did not pass")

    preview_checks = [
        value
        for key, value in checks.items()
        if key.startswith("preview_exists:")
    ]
    if len(preview_checks) != 3 or not all(
        item.get("pass") is True for item in preview_checks
    ):
        failures.append("three texture previews were not verified")

    protected = report.get("protected") or {}
    if protected.get("base_static_hash") != protected.get("edited_static_hash"):
        failures.append("protected static city state changed")
    if protected.get("base_animation_hash") != protected.get("edited_animation_hash"):
        failures.append("protected city animation changed")

    summary = {
        "ok": not failures,
        "contract": report.get("contract"),
        "failures": failures,
    }
    print(json.dumps(summary, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
