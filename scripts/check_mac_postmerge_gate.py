#!/usr/bin/env python3
"""Read-only post-merge eligibility receipt for the Coimbra Mac CI pilot.

This script cannot start a Mac runner or authorize a new executable revision.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPOSITORY = "Dmitry-dev-pet/coimbra-video"
OWNER = "Dmitry-dev-pet"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def api_json(path: str) -> object:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise ValueError("Missing GitHub Actions token")
    request = Request(
        "https://api.github.com/" + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "coimbra-postmerge-gate",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def eligible(event: dict, branch: dict, related_prs: list[dict]) -> tuple[bool, str, int | None]:
    if event.get("action") != "completed":
        return False, "workflow_run event has not completed", None
    if event.get("repository", {}).get("full_name") != REPOSITORY:
        return False, "event repository mismatch", None
    run = event.get("workflow_run") or {}
    if run.get("name") != "Mac runtime package":
        return False, "unexpected validation workflow", None
    if (run.get("event"), run.get("status"), run.get("conclusion"), run.get("head_branch")) != (
        "push", "completed", "success", "main"
    ):
        return False, "not a successful main push validation", None
    sha = run.get("head_sha")
    if not isinstance(sha, str) or SHA_RE.fullmatch(sha) is None:
        return False, "invalid commit identity", None
    if run.get("repository", {}).get("full_name") != REPOSITORY:
        return False, "workflow source repository mismatch", None
    if branch.get("name") != "main" or branch.get("protected") is not True:
        return False, "main has no verified protection", None
    if branch.get("commit", {}).get("sha") != sha:
        return False, "validated commit is not current main HEAD", None

    for pr in related_prs:
        if (pr.get("merged_at") and
                pr.get("merge_commit_sha") == sha and
                pr.get("base", {}).get("ref") == "main" and
                pr.get("base", {}).get("repo", {}).get("full_name") == REPOSITORY and
                pr.get("head", {}).get("repo", {}).get("full_name") == REPOSITORY and
                pr.get("merged_by", {}).get("login", "").casefold() == OWNER.casefold() and
                isinstance(pr.get("number"), int)):
            return True, "protected main, owner-merged PR, matching successful test run", pr["number"]
    return False, "main HEAD has no matching owner-merged same-repository PR", None


def main() -> int:
    output = Path(os.environ.get("GITHUB_WORKSPACE", ".")) / "postmerge-mac-candidate.json"
    result: dict[str, object] = {
        "schema": "coimbra-mac-postmerge-readiness-v1",
        "eligible": False,
        "mac_dispatched": False,
        "not_authority": True,
    }
    try:
        event_path = Path(os.environ["GITHUB_EVENT_PATH"])
        event = json.loads(event_path.read_text(encoding="utf-8"))
        run = event.get("workflow_run") or {}
        sha = run.get("head_sha")
        result["validation_run_id"] = run.get("id")
        result["validated_sha"] = sha
        if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
            raise ValueError("Runner repository mismatch")
        if not isinstance(sha, str) or SHA_RE.fullmatch(sha) is None:
            raise ValueError("Invalid workflow SHA")
        branch = api_json(f"repos/{REPOSITORY}/branches/main")
        found = api_json(f"repos/{REPOSITORY}/commits/{sha}/pulls?per_page=10")
        if not isinstance(branch, dict) or not isinstance(found, list):
            raise ValueError("Malformed GitHub provenance response")
        prs = []
        for item in found[:10]:
            number = item.get("number") if isinstance(item, dict) else None
            if isinstance(number, int) and number > 0:
                detail = api_json(f"repos/{REPOSITORY}/pulls/{number}")
                if isinstance(detail, dict):
                    prs.append(detail)
        passed, reason, number = eligible(event, branch, prs)
        result.update(eligible=passed, reason=reason, pull_request=number)
    except (KeyError, ValueError, OSError, HTTPError, URLError, TypeError, json.JSONDecodeError) as exc:
        # Never print token, API response bodies, or PR-provided text.
        result["reason"] = "Unavailable or invalid provenance evidence"
        result["error_type"] = type(exc).__name__

    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"Eligibility: {result['eligible']} ({result.get('reason')})")
    print("This is only a read-only GitHub artifact; no Mac action was dispatched.")
    return 0 if result["eligible"] else 2


if __name__ == "__main__":
    sys.exit(main())
