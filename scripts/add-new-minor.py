#!/usr/bin/env python3
"""Add newly released Kubernetes minors without changing existing files."""

import argparse
import importlib.util
import json
from pathlib import Path

FAKE_HASH = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def load_release_helper(script_dir: Path):
    path = script_dir / "list-upstream-releases.py"
    spec = importlib.util.spec_from_file_location("list_upstream_releases", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def minor_key(minor: str) -> tuple[int, int]:
    return tuple(int(part) for part in minor.split("."))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", type=Path, default=Path("versions"))
    args = parser.parse_args()
    directory = args.versions.resolve()
    directory.mkdir(parents=True, exist_ok=True)

    existing = {path.stem for path in directory.glob("*.json")}
    if not existing:
        raise SystemExit("refusing discovery without an initial catalogue")
    newest_existing = max(existing, key=minor_key)

    helper = load_release_helper(Path(__file__).resolve().parent)
    upstream = helper.fetch_releases()
    additions = [
        minor
        for minor in upstream
        if minor not in existing and minor_key(minor) > minor_key(newest_existing)
    ]
    for minor in sorted(additions, key=minor_key):
        path = directory / f"{minor}.json"
        data = {
            "minor": minor,
            "version": upstream[minor],
            "srcHash": FAKE_HASH,
            "vendorHash": None,
        }
        path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"added {path.relative_to(directory.parent)} at {upstream[minor]}")

    if not additions:
        print("no new Kubernetes minor releases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
