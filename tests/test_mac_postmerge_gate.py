from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_mac_postmerge_gate.py"
spec = importlib.util.spec_from_file_location("mac_postmerge_gate", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

REPOSITORY = "Dmitry-dev-pet/coimbra-video"
SHA = "a" * 40


def samples():
    event = {
        "action": "completed",
        "repository": {"full_name": REPOSITORY},
        "workflow_run": {
            "name": "Mac runtime package",
            "repository": {"full_name": REPOSITORY},
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "head_sha": SHA,
        },
    }
    branch = {"name": "main", "protected": True, "commit": {"sha": SHA}}
    prs = [{
        "number": 72,
        "merged_at": "2026-10-11T20:00:00Z",
        "merge_commit_sha": SHA,
        "merged_by": {"login": "Dmitry-dev-pet"},
        "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
        "head": {"repo": {"full_name": REPOSITORY}},
    }]
    return event, branch, prs


class PostmergeGateTests(unittest.TestCase):
    def test_accepts_only_owner_merged_current_protected_main(self):
        self.assertEqual(module.eligible(*samples()), (
            True, "protected main, owner-merged PR, matching successful test run", 72))

    def test_unprotected_main_fails_closed(self):
        event, branch, prs = samples()
        branch["protected"] = False
        self.assertFalse(module.eligible(event, branch, prs)[0])

    def test_direct_push_fails_closed(self):
        event, branch, _ = samples()
        self.assertFalse(module.eligible(event, branch, [])[0])

    def test_different_commit_fails_closed(self):
        event, branch, prs = samples()
        branch["commit"]["sha"] = "b" * 40
        self.assertFalse(module.eligible(event, branch, prs)[0])

    def test_failed_pr_ci_fails_closed(self):
        event, branch, prs = samples()
        event["workflow_run"]["conclusion"] = "failure"
        self.assertFalse(module.eligible(event, branch, prs)[0])

    def test_nonowner_merge_fails_closed(self):
        event, branch, prs = samples()
        prs[0]["merged_by"]["login"] = "someone-else"
        self.assertFalse(module.eligible(event, branch, prs)[0])

    def test_fork_head_fails_closed(self):
        event, branch, prs = samples()
        prs[0]["head"]["repo"]["full_name"] = "untrusted/coimbra-video"
        self.assertFalse(module.eligible(event, branch, prs)[0])

    def test_unexpected_run_fails_closed(self):
        event, branch, prs = samples()
        event["workflow_run"]["name"] = "Unrelated test"
        self.assertFalse(module.eligible(event, branch, prs)[0])

    def test_not_main_fails_closed(self):
        event, branch, prs = samples()
        event["workflow_run"]["head_branch"] = "dev"
        self.assertFalse(module.eligible(event, branch, prs)[0])


if __name__ == "__main__":
    unittest.main()
