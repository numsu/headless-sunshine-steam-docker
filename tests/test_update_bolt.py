import os
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import patch


MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/update-bolt.py"))
UPDATE = MODULE['update_pins']
OLD = 'a' * 40
NEW = 'b' * 40
DOCKERFILE = f'ARG BOLT_VERSION=0.24.0\nARG BOLT_COMMIT={OLD}\nARG CEF_VERSION=139\nARG ENABLE_BOLT\n'


class UpdateBoltTests(unittest.TestCase):
    def test_updates_both_pins_only(self):
        updated, version = UPDATE(DOCKERFILE, {'tag_name': '0.25.0'}, NEW)
        self.assertEqual(version, '0.25.0')
        self.assertEqual(updated, DOCKERFILE.replace('0.24.0', '0.25.0').replace(OLD, NEW))

    def test_current_version_is_noop(self):
        self.assertEqual(UPDATE(DOCKERFILE, {'tag_name': '0.24.0'}, OLD)[0], DOCKERFILE)

    def test_rejects_unstable_invalid_and_downgraded_releases(self):
        for release in ({'tag_name': '0.25.0', 'draft': True},
                        {'tag_name': '0.25.0', 'prerelease': True},
                        {'tag_name': '0.25.0-rc1'}, {'tag_name': '0.23.2'},
                        {'tag_name': '0.25.0\nRUN bad'}):
            with self.subTest(release=release), self.assertRaises(ValueError):
                UPDATE(DOCKERFILE, release, NEW)

    def test_rejects_moved_tag_and_invalid_commit(self):
        for commit in (NEW, 'master', ''):
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                UPDATE(DOCKERFILE, {'tag_name': '0.24.0'}, commit)

    def test_requires_both_unique_pins(self):
        for original in ('', DOCKERFILE * 2, DOCKERFILE.replace(f'ARG BOLT_COMMIT={OLD}\n', '')):
            with self.subTest(original=original), self.assertRaises(ValueError):
                UPDATE(original, {'tag_name': '0.25.0'}, NEW)

    def test_resolves_lightweight_and_annotated_tags(self):
        for output, expected in ((f'{OLD}\trefs/tags/0.24.0\n', OLD),
                                 (f'{OLD}\trefs/tags/0.24.0\n{NEW}\trefs/tags/0.24.0^{{}}\n', NEW)):
            with patch('subprocess.run', return_value=SimpleNamespace(stdout=output)):
                self.assertEqual(MODULE['resolve_commit']('0.24.0'), expected)

    def test_disabled_skips_network_and_files(self):
        for env in ({}, {'ENABLE_BOLT': 'false'}):
            with patch.dict(os.environ, env, clear=True), patch('urllib.request.urlopen') as fetch, \
                    patch.object(Path, 'write_text') as write, patch('subprocess.run') as git:
                MODULE['main']()
                fetch.assert_not_called()
                write.assert_not_called()
                git.assert_not_called()
