from pathlib import Path
import runpy
import unittest


UPDATE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/update-sunshine.py"))["update_pin"]


def release(tag="v2026.914.233613", **overrides):
    result = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [{"name": f"sunshine_{tag[1:]}-1+ubuntu24.04_amd64.deb"}],
    }
    return result | overrides


class UpdateSunshineTests(unittest.TestCase):
    def test_updates_only_pin(self):
        original = "FROM ubuntu:24.04\nARG SUNSHINE_VERSION=v2026.906.222525\nARG ENABLE_BOLT\n"
        updated, tag = UPDATE(original, release())
        self.assertEqual(updated, original.replace("v2026.906.222525", tag))

    def test_current_release_is_noop(self):
        original = "ARG SUNSHINE_VERSION=v2026.914.233613\n"
        self.assertEqual(UPDATE(original, release())[0], original)

    def test_rejects_prerelease_draft_and_invalid_tag(self):
        for overrides in ({"prerelease": True}, {"draft": True}, {"tag_name": "latest"},
                          {"tag_name": "v2026.914.233613\nRUN unexpected"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                UPDATE("ARG SUNSHINE_VERSION=v2026.906.222525\n", release(**overrides))

    def test_requires_correct_ubuntu_architecture_package(self):
        for name in ("sunshine_2026.914.233613-1+ubuntu22.04_amd64.deb",
                     "sunshine_2026.914.233613-1+ubuntu24.04_arm64.deb"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                UPDATE("ARG SUNSHINE_VERSION=v2026.906.222525\n", release(assets=[{"name": name}]))

    def test_rejects_missing_and_duplicate_pins(self):
        for original in ("FROM ubuntu:24.04\n", "ARG SUNSHINE_VERSION=v2026.906.222525\n" * 2):
            with self.subTest(original=original), self.assertRaises(ValueError):
                UPDATE(original, release())

    def test_does_not_downgrade(self):
        with self.assertRaises(ValueError):
            UPDATE("ARG SUNSHINE_VERSION=v2026.914.233613\n", release("v2026.906.222525"))
