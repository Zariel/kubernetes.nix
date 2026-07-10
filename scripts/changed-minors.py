#!/usr/bin/env python3
"""Emit a GitHub Actions matrix of changed Kubernetes minors."""

import argparse
import json
import subprocess
from pathlib import Path


BUILD_INPUTS = (
    ".github/workflows/ci.yaml",
    "flake.lock",
    "flake.nix",
    "nix/",
    "overlays/",
    "pkgs/",
)


def all_minors() -> list[str]:
    return sorted(path.stem for path in Path("versions").glob("*.json"))


def select_minors(changed_paths: list[str]) -> list[str]:
    if any(
        path in BUILD_INPUTS
        or any(
            path.startswith(prefix)
            for prefix in BUILD_INPUTS
            if prefix.endswith("/")
        )
        for path in changed_paths
    ):
        return all_minors()
    return sorted(
        {
            Path(path).stem
            for path in changed_paths
            if path.startswith("versions/") and path.endswith(".json")
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if bool(args.base) == args.all:
        parser.error("exactly one of --base or --all is required")

    if args.all:
        minors = all_minors()
    else:
        merge_base = subprocess.run(
            ["git", "merge-base", args.base, "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        result = subprocess.run(
            ["git", "diff", "--name-only", merge_base, "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        )
        minors = select_minors([line for line in result.stdout.splitlines() if line])
    print(json.dumps(minors, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
