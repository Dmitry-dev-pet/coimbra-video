from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_PROBE = "coimbra-apatch-probe-v1\n"


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Frozen judge for the APatch-governed Coimbra Blender proof."
    )
    parser.add_argument("--contract", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--probe", required=True)
    args = parser.parse_args()

    contract_path = Path(args.contract)
    report_path = Path(args.report)
    probe_path = Path(args.probe)

    failures: list[str] = []
    if probe_path.read_text() != EXPECTED_PROBE:
        failures.append("falsification probe changed")

    report = json.loads(report_path.read_text())
    if report.get("status") != "PASS":
        failures.append("semantic verifier did not pass")

    checks = report.get("checks") or {}
    governance = checks.get("apatch_governance_binding") or {}
    if governance.get("pass") is not True:
        failures.append("APatch governance binding did not pass")

    actual = governance.get("actual") or {}
    expected = governance.get("expected") or {}
    plan_hash = sha256_path(contract_path)
    if actual.get("plan_sha256") != plan_hash:
        failures.append("embedded plan hash does not match current contract")
    if expected.get("plan_sha256") != plan_hash:
        failures.append("verifier expected plan hash does not match current contract")
    if not actual.get("session_id"):
        failures.append("edited scene has no APatch session id")
    if not actual.get("envelope_hash"):
        failures.append("edited scene has no APatch envelope hash")
    if actual.get("requirement") != "SPEC-COIMBRA-BLENDER-1#R1":
        failures.append("edited scene is bound to the wrong requirement")

    protected = report.get("protected") or {}
    if protected.get("base_static_hash") != protected.get("edited_static_hash"):
        failures.append("protected static geometry changed")
    if protected.get("base_animation_hash") != protected.get("edited_animation_hash"):
        failures.append("protected animation changed")

    video = checks.get("video_probe") or {}
    if video.get("pass") is not True:
        failures.append("final video probe did not pass")

    summary = {
        "ok": not failures,
        "contract": report.get("contract"),
        "plan_sha256": plan_hash,
        "session_id": actual.get("session_id"),
        "envelope_hash": actual.get("envelope_hash"),
        "failures": failures,
    }
    print(json.dumps(summary, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
