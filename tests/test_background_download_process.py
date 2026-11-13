"""Run real Qt threads + HTTP transfers in child processes: native crashes fail tests."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class BackgroundDownloadProcessTest(unittest.TestCase):
    def test_transfer_archive_and_exit_do_not_crash_or_hang(self):
        scenario = Path(__file__).with_name("background_download_scenario.py")
        for mode in ("complete", "exit"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [sys.executable, "-X", "faulthandler", str(scenario), mode],
                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("BACKGROUND_SCENARIO_PASS " + mode, result.stdout)
                self.assertNotIn("QThread: Destroyed", result.stdout)
                self.assertNotIn("QObject::", result.stdout)
                self.assertNotIn("QWaitCondition::", result.stdout)
