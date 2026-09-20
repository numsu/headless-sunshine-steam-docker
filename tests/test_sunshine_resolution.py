import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts/sunshine-resolution"))
GLOBALS = MODULE["switch"].__globals__


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name) / "resolution.json"
        self.environment = patch.dict(os.environ, {
            "SUNSHINE_CLIENT_WIDTH": "1920", "SUNSHINE_CLIENT_HEIGHT": "1080",
            "SUNSHINE_CLIENT_FPS": "60",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.calls = []

    def execute(self, query, fail=None):
        def run(*args):
            self.calls.append(args)
            if fail and fail(args):
                raise subprocess.CalledProcessError(1, args, "test failure")
            if args == ("xrandr", "--query"):
                return query
            if args[0] == "cvt":
                return ('Modeline "1920x1080_60.00" 173.00 1920 2048 2248 2576 '
                        '1080 1083 1088 1120 -hsync +vsync\n')
            return ""
        return patch.dict(GLOBALS, {"run": run})

    def test_dvi_and_original_dp_setup_switch_and_restore(self):
        for connector, original, rate in (("DVI-D-0", "1024x768", "85.00"),
                                           ("DP-0", "3840x2160_60", "60.00")):
            with self.subTest(connector=connector):
                query = (f"{connector} connected primary\n"
                         f"   {original} {rate}*+\n"
                         "   1920x1080 59.97 60.01\n")
                with self.execute(query):
                    MODULE["switch"](self.state)
                    self.assertIn(("xrandr", "--output", connector, "--mode",
                                   "1920x1080", "--rate", "60.01"), self.calls)
                    MODULE["restore"](self.state)
                    self.assertEqual(self.calls[-1], (
                        "xrandr", "--output", connector, "--mode", original,
                        "--rate", rate))
                    self.assertFalse(self.state.exists())

    def test_primary_active_output_wins_and_other_outputs_stay_untouched(self):
        query = ("DP-0 connected\n   1920x1080 60.00*\n"
                 "DVI-D-0 connected primary\n   1024x768 85.00*\n"
                 "HDMI-0 disconnected\n")
        with self.execute(query):
            MODULE["switch"](self.state)
        self.assertIn(("xrandr", "--addmode", "DVI-D-0", "1920x1080_60.00"),
                      self.calls)
        self.assertFalse(any("--output" in call and "DP-0" in call
                             for call in self.calls))

    def test_inactive_primary_does_not_override_active_output(self):
        outputs = MODULE["parse_outputs"](
            "HDMI-0 connected primary\n   1920x1080 60.00\n"
            "DVI-D-0 connected\n   1024x768 85.00*\n")
        self.assertEqual(MODULE["select_output"](outputs)["name"], "DVI-D-0")

    def test_no_active_output_fails_without_mutation(self):
        with self.execute("DP-0 disconnected\n"):
            with self.assertRaisesRegex(ValueError, "No active"):
                MODULE["switch"](self.state)
        self.assertEqual(self.calls, [("xrandr", "--query")])
        self.assertFalse(self.state.exists())

    def test_repeated_preparation_keeps_original_restore_mode(self):
        self.state.write_text(json.dumps({
            "output": "DVI-D-0", "mode": "1024x768", "rate": "85.00",
        }))
        query = "DVI-D-0 connected primary\n   1920x1080 60.01*\n"
        with self.execute(query):
            MODULE["switch"](self.state)
        self.assertEqual(json.loads(self.state.read_text())["mode"], "1024x768")

    def test_existing_global_mode_can_be_added_after_duplicate_newmode(self):
        query = "DVI-D-0 connected primary\n   1024x768 85.00*\n"
        with self.execute(query, fail=lambda args: "--newmode" in args):
            MODULE["switch"](self.state)
        self.assertEqual(self.calls[-1], (
            "xrandr", "--output", "DVI-D-0", "--mode", "1920x1080_60.00"))

    def test_failed_addmode_does_not_switch_output(self):
        query = "DVI-D-0 connected primary\n   1024x768 85.00*\n"
        with self.execute(query, fail=lambda args: "--addmode" in args):
            with self.assertRaises(subprocess.CalledProcessError):
                MODULE["switch"](self.state)
        self.assertFalse(any("--output" in call for call in self.calls))
        self.assertFalse(self.state.exists())

    def test_failed_restore_keeps_state_for_retry(self):
        self.state.write_text(json.dumps({
            "output": "DVI-D-0", "mode": "1024x768", "rate": "85.00",
        }))
        with self.execute("", fail=lambda args: "--output" in args):
            with self.assertRaises(subprocess.CalledProcessError):
                MODULE["restore"](self.state)
        self.assertTrue(self.state.exists())

    def test_undo_without_state_is_a_noop(self):
        with self.execute(""):
            MODULE["restore"](self.state)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
