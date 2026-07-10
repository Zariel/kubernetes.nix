#!/usr/bin/env python3
"""Validate the append-only Kubernetes version catalogue."""

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

MINOR_RE = re.compile(r"^1\.(0|[1-9][0-9]*)$")
VERSION_RE = re.compile(r"^1\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SRI_RE = re.compile(r"^sha256-([A-Za-z0-9+/]{43}=)$")
FAKE_HASHES = {
    "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "sha256-0000000000000000000000000000000000000000000=",
}
REQUIRED_KEYS = {"minor", "version", "srcHash", "vendorHash"}


def version_files(directory: Path) -> Iterable[Path]:
    return sorted(directory.glob("*.json"))


def validate_sri(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not SRI_RE.fullmatch(value):
        errors.append(f"{label}: must be a sha256 SRI hash")
        return
    if value in FAKE_HASHES:
        errors.append(f"{label}: placeholder hashes are forbidden")
        return
    try:
        decoded = base64.b64decode(value.removeprefix("sha256-"), validate=True)
    except ValueError:
        errors.append(f"{label}: invalid base64 payload")
        return
    if len(decoded) != 32:
        errors.append(f"{label}: sha256 payload must contain 32 bytes")


def validate_file(path: Path, errors: list[str]) -> None:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return

    if not isinstance(data, dict):
        errors.append(f"{path}: top-level value must be an object")
        return

    missing = REQUIRED_KEYS - data.keys()
    extra = data.keys() - REQUIRED_KEYS
    if missing:
        errors.append(f"{path}: missing keys: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"{path}: unknown keys: {', '.join(sorted(extra))}")

    minor = data.get("minor")
    version = data.get("version")
    filename_minor = path.stem
    if not isinstance(minor, str) or not MINOR_RE.fullmatch(minor):
        errors.append(f"{path}: minor must look like 1.36")
    elif minor != filename_minor:
        errors.append(f"{path}: filename minor {filename_minor} != JSON minor {minor}")

    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        errors.append(f"{path}: version must be a stable release such as 1.36.2")
    elif isinstance(minor, str) and not version.startswith(f"{minor}."):
        errors.append(f"{path}: version {version} is outside minor {minor}")

    validate_sri(data.get("srcHash"), f"{path}: srcHash", errors)
    if data.get("vendorHash") is not None:
        errors.append(
            f"{path}: vendorHash must be null because upstream Kubernetes ships a vendor tree"
        )


def validate_append_only(repo: Path, base_ref: str, errors: list[str]) -> None:
    merge_base_result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", base_ref, "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if merge_base_result.returncode != 0:
        errors.append(
            f"cannot find merge base with {base_ref}: {merge_base_result.stderr.strip()}"
        )
        return
    merge_base = merge_base_result.stdout.strip()
    command = [
        "git",
        "-C",
        str(repo),
        "diff",
        "--name-status",
        "--find-renames",
        merge_base,
        "--",
        "versions",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        errors.append(f"cannot compare catalogue with {base_ref}: {result.stderr.strip()}")
        return
    for line in result.stdout.splitlines():
        status, *paths = line.split("\t")
        if status.startswith(("D", "R")):
            errors.append(
                "version catalogue is append-only; deletion/rename is forbidden: "
                + " -> ".join(paths)
            )
        elif status == "M" and paths and paths[0].endswith(".json"):
            relative_path = paths[0]
            previous = subprocess.run(
                ["git", "-C", str(repo), "show", f"{merge_base}:{relative_path}"],
                text=True,
                capture_output=True,
                check=False,
            )
            try:
                old_version = json.loads(previous.stdout)["version"]
                new_version = json.loads((repo / relative_path).read_text())["version"]
                old_parts = tuple(int(part) for part in old_version.split("."))
                new_parts = tuple(int(part) for part in new_version.split("."))
            except (KeyError, OSError, ValueError, json.JSONDecodeError):
                continue
            if new_parts < old_parts:
                errors.append(
                    f"{relative_path}: version downgrade {old_version} -> {new_version} is forbidden"
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("versions", nargs="?", type=Path, default=Path("versions"))
    parser.add_argument("--base-ref", help="Git revision used to reject deletions and renames")
    args = parser.parse_args()

    directory = args.versions.resolve()
    errors: list[str] = []
    files = list(version_files(directory))
    if not files:
        errors.append(f"{directory}: no version files found")
    for path in files:
        validate_file(path, errors)

    if args.base_ref:
        repo = directory.parent
        validate_append_only(repo, args.base_ref, errors)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"validated {len(files)} Kubernetes minor version file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
