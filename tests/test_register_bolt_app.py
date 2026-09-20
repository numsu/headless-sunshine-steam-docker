import copy
import json
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
merge_app = runpy.run_path(str(ROOT / "scripts/register-bolt-app"))["merge_app"]
deduplicate_desktops = runpy.run_path(str(ROOT / "scripts/register-bolt-app"))["deduplicate_desktops"]
sync_apps = runpy.run_path(str(ROOT / "scripts/register-bolt-app"))["sync_apps"]
MANAGED_KEY = "x-headless-sunshine-steam-managed"


class RegisterBoltAppTests(unittest.TestCase):
    def setUp(self):
        self.app = json.loads((ROOT / "sunshine-config/osrs-app.json").read_text())

    def test_existing_apps_and_environment_survive_registration(self):
        config = {"apps": [{"name": "Steam", "cmd": "steam"}], "env": {"FOO": "bar"}}
        original = copy.deepcopy(config)
        self.assertTrue(merge_app(config, self.app))
        self.assertEqual(config["apps"][:-1], original["apps"])
        self.assertEqual(config["env"], original["env"])
        self.assertEqual(config["apps"][-1], self.app)
        self.assertFalse(merge_app(config, self.app))
        self.assertEqual(len(config["apps"]), 2)

    def test_repairs_launch_fields_without_losing_custom_settings(self):
        config = {"apps": [{
            MANAGED_KEY: "bolt",
            "name": "Old School RuneScape",
            "cmd": "steam",
            "detached": [],
            "image-path": "custom.png",
            "prep-cmd": [{"do": "custom-prep"}],
        }]}
        self.assertTrue(merge_app(config, self.app))
        actual = config["apps"][0]
        self.assertEqual(actual["cmd"], "")
        self.assertEqual(actual["detached"], self.app["detached"])
        self.assertEqual(actual["image-path"], "custom.png")
        self.assertEqual(actual["prep-cmd"], [{"do": "custom-prep"}])
        self.assertFalse(merge_app(config, self.app))

    def test_rejects_invalid_app_list_without_changing_it(self):
        for apps in ({}, ["invalid"]):
            config = {"apps": apps}
            original = copy.deepcopy(config)
            with self.assertRaises(ValueError):
                merge_app(config, self.app)
            self.assertEqual(config, original)

    def test_keeps_first_desktop_and_preserves_other_launchers(self):
        retained = [
            {"name": "Low Res Desktop", "image-path": "desktop.png"},
            self.app,
            {"name": "Steam Desktop", "cmd": "steam"},
            {"name": "Desktop", "cmd": "custom-launcher"},
            {"name": "Desktop", "detached": ["custom-launcher"]},
        ]
        config = {"apps": [
            {"name": "Desktop", "image-path": "desktop.png"},
            {"name": "Desktop", "cmd": "", "detached": []},
        ] + copy.deepcopy(retained), "env": {"FOO": "bar"}}
        first_desktop = copy.deepcopy(config["apps"][0])
        self.assertTrue(deduplicate_desktops(config))
        self.assertEqual(config["apps"], [first_desktop] + retained)
        self.assertEqual(config["env"], {"FOO": "bar"})
        self.assertFalse(deduplicate_desktops(config))

    def test_single_desktop_is_unchanged(self):
        config = {"apps": [{"name": "Desktop", "image-path": "custom.png"}]}
        original = copy.deepcopy(config)
        self.assertFalse(deduplicate_desktops(config))
        self.assertEqual(config, original)

    def test_upgrades_placeholder_cover_once(self):
        for old_cover in (None, "", "desktop.png"):
            existing = {**self.app, "image-path": old_cover}
            config = {"apps": [existing]}
            self.assertTrue(merge_app(config, self.app))
            self.assertEqual(existing["image-path"], self.app["image-path"])
            self.assertFalse(merge_app(config, self.app))

    def test_enable_disable_reenable_with_persistent_config(self):
        config = json.loads((ROOT / "sunshine-config/apps.json").read_text())
        original = copy.deepcopy(config)
        self.assertFalse(sync_apps(config))
        self.assertTrue(sync_apps(config, self.app))
        self.assertFalse(sync_apps(config, self.app))
        self.assertTrue(sync_apps(config))
        self.assertEqual(config, original)
        self.assertFalse(sync_apps(config))
        self.assertTrue(sync_apps(config, self.app))
        self.assertEqual(config["apps"][-1], self.app)

    def test_disabled_removes_managed_duplicates_only(self):
        config = {"apps": [self.app.copy(), self.app.copy(),
                           {"name": "Steam Desktop", "cmd": "steam"}],
                  "env": {"FOO": "bar"}}
        self.assertTrue(sync_apps(config))
        self.assertEqual(config, {"apps": [{"name": "Steam Desktop", "cmd": "steam"}],
                                  "env": {"FOO": "bar"}})

    def test_independent_osrs_app_survives_enabled_and_disabled_builds(self):
        independent = {"name": "Old School RuneScape", "cmd": "my-launcher",
                       "image-path": "my-cover.png"}
        config = {"apps": [independent], "env": {"CUSTOM": "value"}}
        original = copy.deepcopy(config)
        self.assertFalse(sync_apps(config, self.app))
        self.assertEqual(config, original)
        self.assertFalse(sync_apps(config))
        self.assertEqual(config, original)

    def test_adopts_legacy_bundled_app_and_removes_it_when_disabled(self):
        legacy = dict(self.app)
        del legacy[MANAGED_KEY]
        config = {"apps": [legacy]}
        self.assertTrue(sync_apps(config, self.app))
        self.assertEqual(config["apps"][0][MANAGED_KEY], "bolt")
        self.assertFalse(sync_apps(config, self.app))
        self.assertTrue(sync_apps(config))
        self.assertEqual(config["apps"], [])

    def test_disabled_recognizes_legacy_without_intermediate_enabled_build(self):
        legacy = dict(self.app)
        del legacy[MANAGED_KEY]
        config = {"apps": [legacy]}
        self.assertTrue(sync_apps(config))
        self.assertEqual(config["apps"], [])

    def test_partial_legacy_matches_do_not_claim_user_apps(self):
        for change in ({"image-path": "custom.png"}, {"detached": ["custom-launcher"]}):
            independent = {**self.app, **change}
            del independent[MANAGED_KEY]
            config = {"apps": [independent]}
            original = copy.deepcopy(config)
            self.assertFalse(sync_apps(config, self.app))
            self.assertEqual(config, original)
            self.assertFalse(sync_apps(config))
            self.assertEqual(config, original)

    def test_managed_entry_can_be_renamed_without_losing_ownership(self):
        config = {"apps": [{**self.app, "name": "My RuneLite"}]}
        self.assertFalse(sync_apps(config, self.app))
        self.assertEqual(config["apps"][0]["name"], "My RuneLite")
        self.assertTrue(sync_apps(config))
        self.assertEqual(config["apps"], [])

    def test_distinct_desktop_configurations_are_preserved(self):
        config = {"apps": [
            {"name": "Desktop", "prep-cmd": [{"do": "mode-a"}]},
            {"name": "Desktop", "prep-cmd": [{"do": "mode-b"}]},
            {"name": "Desktop", "image-path": "custom.png"},
        ]}
        original = copy.deepcopy(config)
        self.assertFalse(deduplicate_desktops(config))
        self.assertEqual(config, original)


if __name__ == "__main__":
    unittest.main()
