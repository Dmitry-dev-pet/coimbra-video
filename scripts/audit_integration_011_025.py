"""Read-only historical acceptance audit for the 2026-09-30 stack integration."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote

REPO = "Dmitry-dev-pet/coimbra-video"
PINS = [
    (9, "83fc6e594210df927a3141d794150df391b79e54", "coimbra-011-photo-patch.yml"),
    (10, "bcceed994f0bf1f092d43fd7837de2b2e3ea9339", "coimbra-012-hero-buildings.yml"),
    (11, "4b2579e973a0060913e5e9c347a94a1eb8731997", "coimbra-013-hero-realism.yml"),
    (12, "1e2f0d26ea9601e6eef0a09043b6f831f20af590", "coimbra-014-environment-realism.yml"),
    (13, "ef4c8d5a8a0013063dd51e7faf3d70ef67e8623e", "coimbra-015-final-look.yml"),
    (14, "da4704e1cdaf894322a18b62cc26c33b4ff88292", "coimbra-017-smooth-full-render.yml"),
    (15, "0ee74b21fd66de393820d6704d4bdc2665f5a0b9", "coimbra-018-full-route-roof-audit.yml"),
    (16, "8b73ccf4887fdab8c1b1bfe650c4129923269a10", "coimbra-019-full-route-pitched-roofs.yml"),
    (17, "dcae729af2d4a6c3ee8d236696337d74697d05e0", "coimbra-020-smooth-pitched-roofs.yml"),
    (18, "217f6630a2cacea17cfa311e14ca2f3ceb7d0080", "coimbra-021-ortho-semantic-details.yml"),
    (19, "f59f8554a2351563db1352c87a354c627fb46885", "coimbra-023-semantic-objects.yml"),
    (20, "d5583af1a837c6a3a0831f42ffdc667abd6b37ab", "coimbra-024-render-backend-ab.yml"),
    (21, "d178382d10eef41ec00da3fe562fcc445438f8da", "coimbra-025-cycles-production-baseline.yml"),
]


def api(path):
    response = subprocess.run(["gh", "api", f"repos/{REPO}/{path}"],
                              check=True, capture_output=True, text=True)
    return json.loads(response.stdout)


def ancestor(sha, head="HEAD"):
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, head],
                          capture_output=True).returncode == 0


def audit(pin):
    number, sha, workflow = pin
    pr = api(f"pulls/{number}")
    result = {"pr": number, "head": sha, "url": pr["html_url"], "errors": []}
    if pr["head"]["sha"] != sha:
        result["errors"].append("PR head changed since the integration snapshot")
    if not ancestor(sha):
        result["errors"].append("Source commit is not preserved in integration ancestry")
    expected_path = f".github/workflows/{workflow}"
    runs = api(f"actions/runs?head_sha={sha}&per_page=100")["workflow_runs"]
    successful = [r for r in runs if r["head_sha"] == sha and r["path"] == expected_path
                  and r["status"] == "completed" and r["conclusion"] == "success"]
    evidence = "exact head"
    if not successful:
        branch = quote(pr["head"]["ref"], safe="")
        runs = api(f"actions/runs?branch={branch}&per_page=100")["workflow_runs"]
        for run in runs:
            if run["path"] != expected_path or run["conclusion"] != "success":
                continue
            previous = run["head_sha"]
            if not ancestor(previous, sha):
                continue
            diff = subprocess.run(["git", "diff", "--name-only", previous, sha, "--",
                                   "blender", "scripts", ".github"],
                                  check=True, capture_output=True, text=True).stdout.strip()
            if not diff:
                successful = [run]
                evidence = "accepted green ancestor; executable code/workflows identical"
                break
    if successful:
        run = successful[0]
        result.update(run_id=run["id"], run_url=run["html_url"], evidence=evidence,
                      tested_sha=run["head_sha"], conclusion=run["conclusion"])
    else:
        result["errors"].append("No successful matching render workflow for this executable state")
    result["passed"] = not result["errors"]
    return result


def main():
    if os.environ.get("GITHUB_REPOSITORY", REPO) != REPO:
        raise SystemExit("This milestone audit is scoped to the Coimbra repository")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(audit, PINS))
    report = {"version": "coimbra-stack-integration-audit-v1", "snapshot_date": "2026-09-30",
              "integration_sha": os.environ.get("GITHUB_SHA"),
              "complete": all(r["passed"] for r in results), "prs": results}
    Path("integration-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as handle:
            handle.write("## Coimbra 011–025 integration audit\n\n")
            for row in results:
                handle.write(f"- PR #{row['pr']}: {'PASS' if row['passed'] else 'FAIL'}; "
                             f"{row.get('run_url', '; '.join(row['errors']))}\n")
    if not report["complete"]:
        raise SystemExit("Stack integration is blocked; inspect integration-audit.json")


if __name__ == "__main__":
    main()
