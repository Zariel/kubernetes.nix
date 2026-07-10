import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


def load_script(name: str):
    path = Path(__file__).parent.parent / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate = load_script("validate-versions.py")
changed = load_script("changed-minors.py")
add_minor = load_script("add-new-minor.py")
upstream = load_script("list-upstream-releases.py")


class VersionValidationTests(unittest.TestCase):
    def write_version(self, directory: Path, filename: str, **updates) -> Path:
        data = {
            "minor": "1.36",
            "version": "1.36.2",
            "srcHash": "sha256-7vKBoVfB5SoiTrW05/mIFVXMJKbIiR/7TDZiCVR9V8Q=",
            "vendorHash": None,
        }
        data.update(updates)
        path = directory / filename
        path.write_text(json.dumps(data))
        return path

    def test_accepts_stable_version_in_matching_minor(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            errors = []
            path = self.write_version(Path(raw_directory), "1.36.json")
            validate.validate_file(path, errors)
            self.assertEqual(errors, [])

    def test_rejects_cross_minor_update(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            errors = []
            path = self.write_version(
                Path(raw_directory), "1.36.json", version="1.37.0"
            )
            validate.validate_file(path, errors)
            self.assertTrue(any("outside minor" in error for error in errors))

    def test_rejects_prerelease_and_placeholder_hash(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            errors = []
            path = self.write_version(
                Path(raw_directory),
                "1.36.json",
                version="1.36.3-rc.0",
                srcHash="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            )
            validate.validate_file(path, errors)
            self.assertTrue(any("stable release" in error for error in errors))
            self.assertTrue(any("placeholder" in error for error in errors))

    def test_rejects_filename_minor_mismatch(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            errors = []
            path = self.write_version(Path(raw_directory), "1.35.json")
            validate.validate_file(path, errors)
            self.assertTrue(any("filename minor" in error for error in errors))


class ChangedMinorTests(unittest.TestCase):
    def test_version_change_selects_only_that_minor(self):
        self.assertEqual(changed.select_minors(["versions/1.36.json"]), ["1.36"])

    def test_lock_change_selects_entire_catalogue(self):
        self.assertEqual(changed.select_minors(["flake.lock"]), changed.all_minors())

    def test_package_change_selects_entire_catalogue(self):
        self.assertEqual(
            changed.select_minors(["pkgs/kubernetes/default.nix"]),
            changed.all_minors(),
        )

    def test_docs_change_does_not_rebuild_kubernetes(self):
        self.assertEqual(changed.select_minors(["README.md"]), [])


class ReleaseDiscoveryTests(unittest.TestCase):
    def test_selects_latest_stable_patch_for_each_minor(self):
        releases = [
            {"tag_name": "v1.36.1", "draft": False, "prerelease": False},
            {"tag_name": "v1.36.3", "draft": False, "prerelease": False},
            {"tag_name": "v1.36.2", "draft": False, "prerelease": False},
            {"tag_name": "v1.37.0-rc.1", "draft": False, "prerelease": True},
            {"tag_name": "v1.37.0", "draft": False, "prerelease": False},
            {"tag_name": "v1.38.0", "draft": True, "prerelease": False},
        ]

        self.assertEqual(
            upstream.newest_stable_releases(releases),
            {"1.36": "1.36.3", "1.37": "1.37.0"},
        )

    def test_adds_only_newer_missing_minors_without_touching_existing_files(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            versions = Path(raw_directory) / "versions"
            versions.mkdir()
            existing = versions / "1.36.json"
            existing.write_text('{"sentinel": true}\n')
            releases = {
                "1.35": "1.35.9",
                "1.36": "1.36.3",
                "1.37": "1.37.1",
                "1.38": "1.38.0",
            }
            helper = SimpleNamespace(fetch_releases=lambda: releases)

            with (
                mock.patch.object(add_minor, "load_release_helper", return_value=helper),
                mock.patch.object(
                    sys,
                    "argv",
                    ["add-new-minor.py", "--versions", str(versions)],
                ),
            ):
                self.assertEqual(add_minor.main(), 0)

            self.assertEqual(existing.read_text(), '{"sentinel": true}\n')
            self.assertFalse((versions / "1.35.json").exists())
            for minor, version in (("1.37", "1.37.1"), ("1.38", "1.38.0")):
                data = json.loads((versions / f"{minor}.json").read_text())
                self.assertEqual(data["minor"], minor)
                self.assertEqual(data["version"], version)
                self.assertEqual(data["srcHash"], add_minor.FAKE_HASH)
                self.assertIsNone(data["vendorHash"])


class AppendOnlyHistoryTests(unittest.TestCase):
    def make_repository(self, directory: Path) -> tuple[Path, str]:
        versions = directory / "versions"
        versions.mkdir()
        (versions / "1.36.json").write_text(
            json.dumps(
                {
                    "minor": "1.36",
                    "version": "1.36.2",
                    "srcHash": "sha256-7vKBoVfB5SoiTrW05/mIFVXMJKbIiR/7TDZiCVR9V8Q=",
                    "vendorHash": None,
                }
            )
        )
        subprocess.run(
            ["git", "-C", str(directory), "init", "-b", "main"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(directory), "add", "versions"],
            check=True,
            capture_output=True,
        )
        tree = subprocess.run(
            ["git", "-C", str(directory), "write-tree"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        commit = subprocess.run(
            [
                "git",
                "-C",
                str(directory),
                "-c",
                "user.name=Catalogue Tests",
                "-c",
                "user.email=tests@example.invalid",
                "commit-tree",
                tree,
                "-m",
                "initial catalogue",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(directory), "update-ref", "refs/heads/main", commit],
            check=True,
            capture_output=True,
        )
        return versions, commit

    def test_rejects_version_downgrade(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            repo = Path(raw_directory)
            versions, base = self.make_repository(repo)
            data = json.loads((versions / "1.36.json").read_text())
            data["version"] = "1.36.1"
            (versions / "1.36.json").write_text(json.dumps(data))
            errors = []
            validate.validate_append_only(repo, base, errors)
            self.assertTrue(any("downgrade" in error for error in errors))

    def test_rejects_version_deletion(self):
        with tempfile.TemporaryDirectory() as raw_directory:
            repo = Path(raw_directory)
            versions, base = self.make_repository(repo)
            (versions / "1.36.json").unlink()
            errors = []
            validate.validate_append_only(repo, base, errors)
            self.assertTrue(any("deletion/rename" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
