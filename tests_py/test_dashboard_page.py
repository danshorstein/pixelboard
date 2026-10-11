import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'targets/linux-sbc-hub75/runtime'))
from scoreboard_device.status_server import DASHBOARD_PAGE


class DashboardPageTests(unittest.TestCase):
    def test_every_inline_script_parses(self):
        # One stray quote in the embedded JavaScript disables every dashboard control.
        scripts = re.findall(r'<script>(.*?)</script>', DASHBOARD_PAGE, re.S)
        self.assertTrue(scripts)
        for index, script in enumerate(scripts):
            with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as handle:
                handle.write(script)
            result = subprocess.run(['node', '--check', handle.name], capture_output=True, text=True)
            Path(handle.name).unlink()
            self.assertEqual(result.returncode, 0, f'script {index}: {result.stderr}')


if __name__ == '__main__':
    unittest.main()
