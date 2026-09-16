"""Windows integration regression through the same worker used by the desktop UI."""
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

APP = Path(__file__).resolve().parents[1] / 'app/floating_asr.py'


class QuickStopTest(unittest.TestCase):
    def test_cancel_during_startup(self):
        for delay in (0.0, 0.1, 0.5):
            with self.subTest(delay=delay):
                startup = subprocess.STARTUPINFO()
                startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 0
                process = subprocess.Popen([sys.executable, str(APP), '--worker', 'live'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', creationflags=subprocess.CREATE_NEW_CONSOLE,
                    startupinfo=startup)
                time.sleep(delay)
                start = time.monotonic()
                try:
                    output, error = process.communicate('stop\n', timeout=16)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()
                events = [json.loads(line) for line in output.splitlines()]
                elapsed = time.monotonic() - start
                self.assertLess(elapsed, 4, 'Cancellation must not wait for the 12-second fallback')
                self.assertEqual(process.returncode, 0, error)
                self.assertEqual(events[-1].get('exit'), 0, events)
                self.assertTrue(events[-1].get('cancelled'), events)
                print(f'delay={delay}s stop={elapsed:.3f}s: cancelled cleanly', flush=True)


if __name__ == '__main__':
    unittest.main()
