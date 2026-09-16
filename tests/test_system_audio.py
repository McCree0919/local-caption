"""Windows hardware integration: real speaker playback -> WASAPI -> ASR worker."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import winsound

BASE = Path(__file__).resolve().parents[1]
COMMAND = [str(BASE / 'translation/.venv/Scripts/python.exe'), str(BASE / 'app/loopback_worker.py')]


def launch():
    return subprocess.Popen(COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    for delay in (0, 0.1, 0.5):
        p = launch()
        time.sleep(delay)
        start = time.monotonic()
        output, error = p.communicate('stop\n', timeout=15)
        assert p.returncode == 0 and '"exit": 1' not in output, (output, error)
        assert time.monotonic() - start < 3, 'Quick cancellation blocked'
    p = launch()
    events = []
    inbox = queue.Queue()
    def read():
        for line in p.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            events.append(event)
            inbox.put(event)
    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                event = inbox.get(timeout=1)
            except queue.Empty:
                if p.poll() is not None:
                    raise AssertionError(events)
                continue
            if event.get('line', '').startswith('[live] listening'):
                break
            if event.get('exit'):
                raise AssertionError(events)
        else:
            raise AssertionError('Capture not ready')
        winsound.PlaySound(str(BASE / 'samples/jfk.wav'), winsound.SND_FILENAME | winsound.SND_ASYNC)
        time.sleep(13)
        p.stdin.write('stop\n')
        p.stdin.flush()
        p.wait(timeout=25)
        thread.join(timeout=3)
        lines = [e['line'] for e in events if e.get('line', '').startswith('[live final')]
        assert p.returncode == 0 and not any(e.get('exit') for e in events), events[-5:]
        assert lines and 'country' in lines[-1].lower() and 'fellow' in lines[-1].lower(), lines
        metrics = [e['audio_metrics'] for e in events if 'audio_metrics' in e]
        assert any(m['level'] > 0.001 for m in metrics), 'No real output audio captured'
        report = dict(final=lines[-1], device=next(e['capture_device'] for e in events if 'capture_device' in e),
                      max_audio_backlog=max(m['backlog_seconds'] for m in metrics),
                      final_audio_backlog=metrics[-1]['backlog_seconds'], events=len(events),
                      immediate_stop='passed 0/0.1/0.5 seconds')
        (BASE / 'diagnostics/system-audio-test.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True))
    finally:
        winsound.PlaySound(None, 0)
        if p.poll() is None:
            p.kill()
            p.wait()


if __name__ == '__main__':
    main()
