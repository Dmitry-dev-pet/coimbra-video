"""Stage this immutable action's fixed helpers into the caller's workspace.

No network, code execution, credential access or user-selected paths. The caller
owns admission and resource limits. This module only replaces the old checked-in
helper locations for compatibility with unchanged render scripts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


class PackageError(ValueError):
    pass


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def package_files(package: Path) -> dict[str, bytes]:
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("files")
    if manifest.get("version") != 1 or not isinstance(files, dict) or not files:
        raise PackageError("Invalid helper manifest")
    result: dict[str, bytes] = {}
    for name, expected in files.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*\.(py|sh)", name):
            raise PackageError("Invalid helper name")
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{40}", expected):
            raise PackageError("Invalid helper digest")
        source = package / name
        if source.is_symlink() or not source.is_file():
            raise PackageError("Helper must be a regular file")
        data = source.read_bytes()
        if git_blob(data) != expected:
            raise PackageError(f"Helper digest mismatch: {name}")
        result[name] = data
    return result


def materialize(package: Path, workspace: Path) -> list[str]:
    files = package_files(package)
    workspace = workspace.resolve(strict=True)
    directory = workspace / "scripts"
    directory.mkdir(exist_ok=True)
    nofollow = os.O_NOFOLLOW
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | nofollow)
    try:
        for name, data in files.items():
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
                             0o600, dir_fd=directory_fd)
            except FileExistsError:
                fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | nofollow, dir_fd=directory_fd)
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise PackageError("Existing helper is not a regular file")
                    existing = stream.read(len(data) + 1)
                if existing != data:
                    raise PackageError(f"Refusing to overwrite a different helper: {name}")
            else:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
    finally:
        os.close(directory_fd)
    return sorted(files)


if __name__ == "__main__":
    package = Path(__file__).resolve().parent
    workspace = Path(os.environ["GITHUB_WORKSPACE"])
    if Path.cwd().resolve() != workspace.resolve():
        raise SystemExit("Run helper preparation from GITHUB_WORKSPACE")
    names = materialize(package, workspace)
    print(f"Prepared {len(names)} verified project-owned helpers")
