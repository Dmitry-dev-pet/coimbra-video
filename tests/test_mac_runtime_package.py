from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ops" / "mac"
spec = importlib.util.spec_from_file_location("materialize", PACKAGE / "materialize.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MacRuntimePackageTests(unittest.TestCase):
    def test_all_nine_hashes_match(self):
        self.assertEqual(len(module.package_files(PACKAGE)), 9)

    def test_python_compiles_without_importing_blender(self):
        for name, content in module.package_files(PACKAGE).items():
            if name.endswith(".py"):
                with self.subTest(name=name):
                    ast.parse(content, filename=name)

    def test_shell_syntax(self):
        for name in module.package_files(PACKAGE):
            if name.endswith(".sh"):
                with self.subTest(name=name):
                    subprocess.run(["bash", "-n", str(PACKAGE / name)], check=True)

    def test_stage_and_repeat_do_not_execute_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            files = module.package_files(PACKAGE)
            self.assertEqual(module.materialize(PACKAGE, workspace), sorted(files))
            self.assertEqual(module.materialize(PACKAGE, workspace), sorted(files))
            self.assertEqual({p.name for p in workspace.iterdir()}, {"scripts"})
            for name, content in files.items():
                self.assertEqual((workspace / "scripts" / name).read_bytes(), content)

    def test_different_existing_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            target = workspace / "scripts" / "render_coimbra_036_preview.py"
            target.parent.mkdir()
            target.write_text("keep me")
            with self.assertRaises(module.PackageError):
                module.materialize(PACKAGE, workspace)
            self.assertEqual(target.read_text(), "keep me")

    def test_symlink_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, outside = root / "workspace", root / "outside"
            workspace.mkdir()
            outside.mkdir()
            (workspace / "scripts").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(OSError):
                module.materialize(PACKAGE, workspace)
            self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "scripts").mkdir()
            target = workspace / "outside"
            target.write_text("untouched")
            (workspace / "scripts" / "render_coimbra_036_preview.py").symlink_to(target)
            with self.assertRaises(OSError):
                module.materialize(PACKAGE, workspace)
            self.assertEqual(target.read_text(), "untouched")

    def test_manifest_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / "manifest.json").write_text(json.dumps({
                "version": 1, "files": {"../escape.py": "a" * 40}}))
            with self.assertRaises(module.PackageError):
                module.package_files(package)

    def test_source_tampering_is_rejected_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({
                "version": 1, "files": {"test.py": "a" * 40}}))
            (root / "test.py").write_text("raise RuntimeError('not executed')")
            with self.assertRaises(module.PackageError):
                module.package_files(root)

    def test_webgpu_relocation_has_only_documented_change(self):
        changed = (PACKAGE / "run_coimbra_034_webgpu_benchmark.py").read_text()
        original = changed.replace(
            "# The caller's execution workspace, not the installed project package directory.\nROOT = Path.cwd()",
            "ROOT = Path(__file__).resolve().parents[1]",
        )
        self.assertEqual(module.git_blob(original.encode()),
                         "67449c938757ad9905535b58ade78a622c70f76c")


if __name__ == "__main__":
    unittest.main()
