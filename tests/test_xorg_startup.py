import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
if BASH is None and Path("C:/Program Files/Git/bin/bash.exe").is_file():
    BASH = "C:/Program Files/Git/bin/bash.exe"


@unittest.skipUnless(BASH, "Bash is needed to exercise the Xorg generator")
class XorgStartupTests(unittest.TestCase):
    def generate(self, **overrides):
        dockerfile = (ROOT / "Dockerfile").read_text()
        script = dockerfile.split(
            "RUN cat > /usr/local/bin/generate-xorg-config <<'EOF'\n", 1
        )[1].split("\nEOF", 1)[0]
        # Substitute hardware probes; run the real validation and config output.
        probes = '''
nvidia-smi() { echo '00000000:04:00.0'; }
cvt() {
    [[ "$*" == '-r 1920 1080 60' ]] || return 1
    echo 'Modeline "1920x1080R" 138.50 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync'
}
'''
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            script = script.replace("/etc/X11/xorg.conf.d", target.as_posix())
            script_path = target / "generate.sh"
            script_path.write_text(probes + script, encoding="utf-8", newline="\n")
            environment = {key: value for key, value in os.environ.items()
                           if key not in {"XORG_DISPLAY", "XORG_WIDTH", "XORG_HEIGHT"}}
            environment.update(overrides)
            result = subprocess.run([BASH, str(script_path)], env=environment,
                                    capture_output=True, text=True)
            config = target / "20-nvidia.conf"
            return result, config.read_text() if config.exists() else None

    def test_defaults_preserve_original_display_and_timings(self):
        result, config = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('BusID "PCI:4:0:0"', config)
        self.assertIn('Option "ConnectedMonitor" "DP-0"', config)
        self.assertIn('Option "UseDisplayDevice" "DP-0"', config)
        self.assertIn('Option "MetaModes" "DP-0: 3840x2160_60 +0+0"', config)
        self.assertIn('Modeline "3840x2160_60" 533.25 3840 3888 3920 4000 2160 2163 2168 2222 +HSync -VSync', config)
        self.assertIn('Virtual 3840 2160', config)

    def test_custom_display_and_size_are_used_consistently(self):
        result, config = self.generate(XORG_DISPLAY="DFP-0", XORG_WIDTH="1920", XORG_HEIGHT="1080")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Option "ConnectedMonitor" "DFP-0"', config)
        self.assertIn('Option "UseDisplayDevice" "DFP-0"', config)
        self.assertIn('Option "MetaModes" "DFP-0: 1920x1080R +0+0"', config)
        self.assertIn('Modes "1920x1080R"', config)
        self.assertIn('Virtual 1920 1080', config)
        self.assertNotIn('3840', config)

    def test_invalid_values_do_not_write_configuration(self):
        for overrides in ({"XORG_DISPLAY": 'DP-0"\nEndSection'},
                          {"XORG_WIDTH": "01920"}, {"XORG_HEIGHT": "0"},
                          {"XORG_WIDTH": "99999"}):
            with self.subTest(overrides=overrides):
                result, config = self.generate(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(config)


if __name__ == "__main__":
    unittest.main()
