#!/usr/bin/env python3
"""List the newest stable Kubernetes patch release for each recent minor."""

import argparse
import json
import os
import re
import urllib.request

VERSION_RE = re.compile(r"^v(1\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))$")
API_URL = "https://api.github.com/repos/kubernetes/kubernetes/releases?per_page=100"


def version_key(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))


def newest_stable_releases(releases: list[dict[str, object]]) -> dict[str, str]:
    newest: dict[str, str] = {}
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        match = VERSION_RE.fullmatch(str(release.get("tag_name", "")))
        if not match:
            continue
        version = match.group(1)
        minor = version.rsplit(".", 1)[0]
        if minor not in newest or version_key(version) > version_key(newest[minor]):
            newest[minor] = version
    return dict(sorted(newest.items(), key=lambda item: version_key(item[1])))


def fetch_releases() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "kubernetes.nix-release-discovery",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(API_URL, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.load(response)
    if not isinstance(releases, list):
        raise ValueError("GitHub releases response must be a list")
    return newest_stable_releases(releases)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit a JSON object")
    args = parser.parse_args()
    releases = fetch_releases()
    if args.json:
        print(json.dumps(releases, indent=2, sort_keys=True))
    else:
        for minor, version in releases.items():
            print(f"{minor}\t{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
