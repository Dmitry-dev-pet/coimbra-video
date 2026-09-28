from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

from apatch.runtime.session import start_session
from apatch.sdd_integrity import (
    canonical_hash,
    freeze_contract,
    run_frozen_session_verification,
    session_attestation_projection,
    validate_task_envelope,
)
from apatch.session_state import load_session_state
from apatch.spec import resolve_requirement
from apatch_blender.contracts import load_contract
from apatch_blender.governance import plan_check, required_apatch_scope


JUDGE_PATH = "scripts/verify_apatch_blender_evidence.py"
PROBE_PATH = "verification/COIMBRA-BRIDGE-003-SLOW.probe"


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def build_documents(root: Path, contract_path: Path, baseline_path: Path) -> dict[str, Any]:
    contract = load_contract(contract_path)
    requirement = str(contract.governance.get("requirement") or "")
    if not requirement:
        raise RuntimeError("contract has no APatch requirement")

    resolved = resolve_requirement(str(root), requirement)
    if not resolved.get("ok"):
        raise RuntimeError(str(resolved))

    verify_line = str(resolved.get("verify") or "").strip()
    if not verify_line:
        raise RuntimeError("SPEC requirement has no frozen verify command")
    command = shlex.split(verify_line)

    judge_path = root / JUDGE_PATH
    probe_path = root / PROBE_PATH
    if not judge_path.is_file() or not probe_path.is_file():
        raise RuntimeError("frozen judge assets are missing")
    if not baseline_path.is_file():
        raise RuntimeError(f"baseline input is missing: {baseline_path}")

    scope = required_apatch_scope(contract, root)
    acceptance_id = plan_check(contract)
    judge_hash = sha256_path(judge_path)
    probe_hash = sha256_path(probe_path)
    baseline_hash = sha256_path(baseline_path)

    spec_id = requirement.split("#", 1)[0]
    spec_path = root / "docs" / "specs" / f"{spec_id}.md"
    if not spec_path.is_file():
        raise RuntimeError(f"SPEC file is missing: {spec_path}")

    obligation = {
        "acceptance_id": acceptance_id,
        "test_id": JUDGE_PATH,
        "oracle": (
            "The exact APatch-bound Blender plan produces a passing semantic report, "
            "preserves protected geometry/animation, and produces the declared video."
        ),
        "perspectives": ["positive", "negative", "boundary", "regression"],
        "asset_hashes": [judge_hash],
        "judge_assets": [{"path": JUDGE_PATH, "sha256": judge_hash}],
        "command": command,
        "command_hash": canonical_hash(command),
        "baseline": {
            "kind": "observed_red",
            "result_hash": sha256_bytes(
                b"pre-execution baseline: final semantic report is absent"
            ),
        },
        "falsification": {
            "kind": "reversible_seed",
            "expected": "red",
            "target_hash": probe_hash,
            "target_path": PROBE_PATH,
        },
        "approver": "owner:repository",
        "material": True,
    }

    frozen = freeze_contract(
        {
            "brief_hash": sha256_bytes(
                b"Govern the Coimbra slow Blender flight through APatch SDD"
            ),
            "rfp_hash": sha256_path(root / "AGENTS.md"),
            "spec_hash": sha256_path(spec_path),
            "plan_hash": sha256_path(contract.path),
            "baseline_hash": baseline_hash,
            "coverage": {
                "complete": True,
                "missing": [],
                "ambiguous": [],
                "waivers": [],
            },
            "obligations": [obligation],
            "authority": {"actor_id": "owner:repository", "role": "authority"},
            "source_mutation_count": 0,
            "frozen_at": "2026-09-28T00:00:00Z",
        }
    )

    report_path = str(contract.raw.get("verification_report") or "")
    allowed_reads = unique(
        list(scope["allowed_reads"])
        + [JUDGE_PATH, PROBE_PATH, spec_path.relative_to(root).as_posix()]
        + ([report_path] if report_path else [])
    )
    allowed_writes = unique(list(scope["allowed_writes"]) + [PROBE_PATH])

    envelope = validate_task_envelope(
        {
            "schema": "apatch.sdd.task-envelope.v1",
            "requirement": requirement,
            "contract_hash": frozen["document_hash"],
            "baseline_hash": baseline_hash,
            "allowed_reads": allowed_reads,
            "allowed_writes": allowed_writes,
            "allowed_symbols": [],
            "forbidden_paths": [
                "docs/specs/**",
                JUDGE_PATH,
                ".github/**",
                "blender/**",
                "data/**",
            ],
            "tools": list(scope["tools"]),
            "commands": [command],
            "network": [],
            "remote": [],
            "services": [],
            "budgets": {
                "files": len(allowed_writes),
                "insertions": 0,
                "deletions": 0,
                "seconds": 3600,
            },
            "checks": [acceptance_id],
            "rollback_owner": "session:self",
            "containment": "mediated_only",
        }
    )

    return {
        "contract": contract,
        "requirement": requirement,
        "resolved": resolved,
        "scope": scope,
        "frozen": frozen,
        "envelope": envelope,
        "acceptance_id": acceptance_id,
    }


def start(root: Path, contract_path: Path, baseline_path: Path, output: Path) -> None:
    documents = build_documents(root, contract_path, baseline_path)
    started = start_session(
        str(root),
        str(documents["resolved"]["intent"]),
        artifacts=[documents["resolved"]["artifact"]],
        sdd_contract=documents["frozen"],
        task_envelope=documents["envelope"],
        actor={"actor_id": "agent:github-actions", "role": "implementation"},
    )
    if not started.get("ok"):
        raise RuntimeError(str(started))

    evidence = {
        "ok": True,
        "session_id": started["session_capability"]["session_id"],
        "requirement": documents["requirement"],
        "spec_artifact": documents["resolved"]["artifact"],
        "acceptance_id": documents["acceptance_id"],
        "plan_sha256": sha256_path(documents["contract"].path),
        "verification_contract_hash": documents["frozen"]["document_hash"],
        "task_envelope_hash": documents["envelope"]["document_hash"],
        "scope": documents["scope"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


def verify(root: Path, output: Path) -> None:
    state = load_session_state(str(root))
    session_id = str(state.get("session_id") or "")
    if not session_id:
        raise RuntimeError("no APatch session state restored")

    result = run_frozen_session_verification(
        str(root),
        expected_session_id=session_id,
        timeout=300,
    )
    current = load_session_state(str(root))
    evidence = {
        "ok": bool(result.get("ok")),
        "session_id": session_id,
        "verification": result,
        "attestation_projection": session_attestation_projection(current),
        "external_mutation_recording": "not_available_in_apatch_0.8.48",
        "attestation_emitted": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    start_parser = sub.add_parser("start")
    start_parser.add_argument("--contract", required=True)
    start_parser.add_argument("--baseline", required=True)
    start_parser.add_argument(
        "--output",
        default="bridge_output_003/apatch-session-start.json",
    )

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument(
        "--output",
        default="bridge_output_003/apatch-sdd-verification.json",
    )

    parser.add_argument("--root", default=".")

    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "start":
        start(
            root,
            (root / args.contract).resolve(),
            (root / args.baseline).resolve(),
            (root / args.output).resolve(),
        )
    else:
        verify(root, (root / args.output).resolve())


if __name__ == "__main__":
    main()
