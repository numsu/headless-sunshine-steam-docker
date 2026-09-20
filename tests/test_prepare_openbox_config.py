from pathlib import Path
import runpy
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
PREPARE = runpy.run_path(str(ROOT / "scripts/prepare-openbox-config"))["prepare_config"]
MENU_NS = {"m": "http://openbox.org/"}


class OpenboxConfigTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "saved-rc.xml"
        self.destination = self.root / "session-rc.xml"
        self.menu_path = self.root / "openbox-menu.xml"

    def test_saved_menus_replaced_without_modifying_saved_files_or_bindings(self):
        for namespace in ("", ' xmlns="http://openbox.org/3.4/rc"'):
            with self.subTest(namespace=namespace):
                original = (
                    f'<openbox_config{namespace}>'
                    '<keyboard><keybind key="A-F1"><action name="ShowMenu">'
                    '<menu>root-menu</menu></action></keybind></keyboard>'
                    '<theme><name>Custom</name></theme>'
                    '<menu><file>menu.xml</file><file>/etc/xdg/openbox/menu.xml</file>'
                    '<showIcons>yes</showIcons></menu>'
                    '<applications><application class="Example"><desktop>2</desktop>'
                    '</application></applications></openbox_config>'
                )
                self.source.write_text(original)
                saved_menu = self.root / "menu.xml"
                saved_menu.write_text('<openbox_menu><action name="Exit"/></openbox_menu>')
                PREPARE(self.source, self.destination, bolt_available=True)
                self.assertEqual(self.source.read_text(), original)
                self.assertIn('name="Exit"', saved_menu.read_text())
                config = ET.parse(self.destination).getroot()
                prefix = "{http://openbox.org/3.4/rc}" if namespace else ""
                files = config.findall(f"{prefix}menu/{prefix}file")
                self.assertEqual([entry.text for entry in files], [str(self.menu_path.resolve())])
                self.assertEqual(config.find(f"{prefix}theme/{prefix}name").text, "Custom")
                self.assertEqual(config.find(f"{prefix}keyboard/{prefix}keybind").get("key"), "A-F1")
                self.assertEqual(config.find(f"{prefix}menu/{prefix}showIcons").text, "yes")
                applications = config.find(f"{prefix}applications")
                self.assertEqual(applications[0].find(f"{prefix}desktop").text, "2")
                self.assertEqual(applications[-1].find(f"{prefix}decor").text, "yes")

    def test_runtime_bolt_detection_and_regeneration_remove_stale_launcher(self):
        self.source.write_text('<openbox_config xmlns="http://openbox.org/3.4/rc"/>')
        for available in (True, False):
            with self.subTest(available=available):
                with patch.dict(PREPARE.__globals__, os=Mock()):
                    # Runtime detection follows the installed executable, not saved menus.
                    PREPARE.__globals__["os"].access.return_value = available
                    PREPARE(self.source, self.destination)
                menu = ET.parse(self.menu_path).getroot()
                commands = [element.text for element in menu.findall(".//m:command", MENU_NS)]
                self.assertIn("/usr/local/bin/steam steam://open/main", commands)
                self.assertIn("/usr/local/bin/steam -gamepadui", commands)
                self.assertEqual("/usr/local/bin/bolt" in commands, available)
                actions = {element.get("name") for element in menu.findall(".//m:action", MENU_NS)}
                self.assertEqual(actions, {"Execute", "Reconfigure"})
                menus = {element.get("id") for element in menu.findall(".//m:menu", MENU_NS)}
                self.assertEqual(menus, {"root-menu", "client-list-combined-menu"})

    def test_invalid_saved_config_does_not_write_session_files(self):
        self.source.write_text("<wrong/>")
        with self.assertRaises(ValueError):
            PREPARE(self.source, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.menu_path.exists())


if __name__ == "__main__":
    unittest.main()
