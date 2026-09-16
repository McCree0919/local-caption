"""Exercise the real Tk event loop with a burst of synthetic ASR snapshots."""
import json
from pathlib import Path
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parents[1]
REPORT = BASE / 'diagnostics/render-stress.json'


def run_child():
    sys.path.insert(0, str(BASE / 'app'))
    from floating_asr import main
    def driver(app):
        import faulthandler
        diagnostic = (BASE / 'diagnostics/render-stress-stack.txt').open('w')
        faulthandler.dump_traceback_later(12, repeat=True, file=diagnostic)
        app.chinese.set(False)
        app.autosave.set(False)
        start = time.monotonic()
        previous = start
        gaps = []
        text = 'This is a synthetic subtitle used to test responsive scrolling. ' * 250
        for index in range(5000):
            app.events.put({'line': f'[live partial @ {index}s] {text} {index}'})

        def heartbeat():
            nonlocal previous
            now = time.monotonic()
            gaps.append(now - previous)
            previous = now
            if app.events.empty() and app.text.endswith('4999') and not app.hints_pending:
                visible = app.view.get('1.0', 'end')
                report = {'snapshots': 5000, 'seconds': now - start,
                          'max_heartbeat_gap': max(gaps), 'heartbeats': len(gaps),
                          'visible_chars': len(visible), 'source_chars': len(app.text),
                          'latest_visible': '4999' in visible}
                REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
                faulthandler.cancel_dump_traceback_later()
                diagnostic.close()
                app.dirty = False
                app.shutdown()
            else:
                app.root.after(25, heartbeat)
        app.root.after(25, heartbeat)
    main(driver)


if __name__ == '__main__':
    if '--child' in sys.argv:
        run_child()
    else:
        process = subprocess.Popen([sys.executable, __file__, '--child'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, error = process.communicate(timeout=35)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise AssertionError('Tk event loop stopped responding')
        assert process.returncode == 0, error
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        assert report['max_heartbeat_gap'] < 1, report
        assert report['latest_visible'] and report['visible_chars'] < 5500, report
        print(json.dumps(report, indent=2))
