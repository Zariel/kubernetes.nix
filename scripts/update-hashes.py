#!/usr/bin/env python3
"""Refresh fetchFromGitHub hashes in Kubernetes version files."""

import argparse
import json
import subprocess
from pathlib import Path


def changed_version_files() -> list[Path]:
    modified = subprocess.run(
        ["git", "diff", "--name-only", "--", "versions/*.json"],
        text=True,
        capture_output=True,
        check=True,
    )
    untracked = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "versions/*.json",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    paths = set(modified.stdout.splitlines()) | set(untracked.stdout.splitlines())
    return [Path(line) for line in sorted(paths) if line]


def source_hash(version: str) -> str:
    url = f"https://github.com/kubernetes/kubernetes/archive/refs/tags/v{version}.tar.gz"
    result = subprocess.run(
        ["nix", "store", "prefetch-file", "--json", "--unpack", url],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)["hash"]


def update(path: Path) -> None:
    data = json.loads(path.read_text())
    new_hash = source_hash(data["version"])
    if data.get("srcHash") == new_hash and data.get("vendorHash") is None:
        print(f"unchanged {path}")
        return
    data["srcHash"] = new_hash
    data["vendorHash"] = None
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"updated {path} ({data['version']})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--changed", action="store_true")
    args = parser.parse_args()
    if args.paths and args.changed:
        parser.error("paths and --changed are mutually exclusive")
    if args.paths:
        paths = args.paths
    elif args.changed:
        paths = changed_version_files()
    else:
        paths = sorted(Path("versions").glob("*.json"))
    for path in paths:
        update(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
