from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ops" / "mac"
sys.path.insert(0, str(PACKAGE))
from prepare import fixed_environment

EXPECTED = {"coimbra_027", "coimbra_028", "coimbra_029", "coimbra_031", "coimbra_032",
            "coimbra_033", "coimbra_034", "coimbra_035", "coimbra_036", "coimbra_037",
            "coimbra_v2_001"}
PREPARE_STEP = {
    "name": "Prepare project package", "shell": "bash",
    "env": {"COIMBRA_ACTION_DIR": "${{ github.action_path }}"},
    "run": 'python3 "$COIMBRA_ACTION_DIR/../prepare.py"',
}


class MacActionsTests(unittest.TestCase):
    def test_action_inventory_is_complete_and_closed(self):
        lanes = json.loads((PACKAGE / "lanes.json").read_text())["lanes"]
        self.assertEqual(set(lanes), EXPECTED)
        self.assertEqual({p.parent.name for p in PACKAGE.glob("*/action.yml")}, EXPECTED)

    def test_composite_contract_and_shell_syntax(self):
        for lane in sorted(EXPECTED):
            with self.subTest(lane=lane):
                action = yaml.safe_load((PACKAGE / lane / "action.yml").read_text())
                self.assertNotIn("inputs", action)
                self.assertEqual(action["runs"]["using"], "composite")
                steps = action["runs"]["steps"]
                self.assertEqual(steps[0], PREPARE_STEP)
                self.assertEqual(action["outputs"]["result"]["value"],
                                 "${{ steps.result.outputs.result }}")
                self.assertEqual(sum(s.get("id") == "result" for s in steps), 1)
                self.assertEqual(steps[-1]["uses"], "actions/upload-artifact@v4")
                self.assertEqual(steps[-1]["with"]["if-no-files-found"], "error")
                for step in steps:
                    if "uses" in step:
                        self.assertIn(step["uses"], {
                            "actions/download-artifact@v4", "actions/upload-artifact@v4"})
                    if "run" in step:
                        self.assertEqual(step["shell"], "bash")
                        script = re.sub(r"\$\{\{.*?\}\}", "/expression", step["run"])
                        subprocess.run(["bash", "-n"], input=script, text=True, check=True)
                        for code in re.findall(r"<<'PY'\n(.*?)^PY\s*$", script,
                                               flags=re.MULTILINE | re.DOTALL):
                            ast.parse(code, filename=f"{lane}:{step.get('name', 'step')}")
                serialized = json.dumps(action)
                self.assertNotIn("github.event.issue.body", serialized)
                self.assertNotIn("inputs.command", serialized)
                self.assertNotIn("secrets.", serialized)

    def test_each_action_prepares_only_helpers_and_fixed_environment(self):
        for lane in sorted(EXPECTED):
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                environment_file = workspace / "github-env"
                environment_file.touch()
                environment = {
                    "PATH": os.environ["PATH"],
                    "GITHUB_WORKSPACE": str(workspace),
                    "GITHUB_ENV": str(environment_file),
                    "COIMBRA_ACTION_DIR": str(PACKAGE / lane),
                }
                subprocess.run([sys.executable, str(PACKAGE / "prepare.py")],
                               cwd=workspace, env=environment, check=True)
                values = dict(line.split("=", 1) for line in
                              environment_file.read_text().splitlines())
                self.assertEqual(values, fixed_environment(PACKAGE, lane))
                self.assertEqual(len(list((workspace / "scripts").iterdir())), 9)
                self.assertEqual({p.name for p in workspace.iterdir()}, {"scripts", "github-env"})

    def test_unknown_lane_cannot_choose_a_runtime(self):
        with self.assertRaises(ValueError):
            fixed_environment(PACKAGE, "../../arbitrary-command")


if __name__ == "__main__":
    unittest.main()
