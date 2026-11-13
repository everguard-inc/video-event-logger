"""Keep the computer from idle-sleeping while downloads run.

macOS: `caffeinate -i -w <pid>` (ships with the OS, exits with the app).
Linux: `systemd-inhibit --what=idle` when available.
Closing a laptop lid still sleeps the machine; downloads then wait for the
network and continue after wake.
"""
import os
import shutil
import subprocess
import sys


class SleepInhibitor:
    def __init__(self):
        self.process = None

    @staticmethod
    def command():
        if sys.platform == "darwin" and shutil.which("caffeinate"):
            return ["caffeinate", "-i", "-w", str(os.getpid())]
        if sys.platform.startswith("linux") and shutil.which("systemd-inhibit"):
            return [
                "systemd-inhibit", "--what=idle", "--who=Video Event Logger",
                "--why=Downloading videos", "--mode=block", "sleep", "infinity",
            ]
        return None

    @property
    def active(self):
        return self.process is not None and self.process.poll() is None

    def set_active(self, active):
        if active == self.active:
            return
        if active:
            command = self.command()
            if command is None:
                return
            try:
                self.process = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True,
                )
            except OSError:
                self.process = None
            return
        process, self.process = self.process, None
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass
