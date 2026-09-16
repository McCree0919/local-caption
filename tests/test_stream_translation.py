"""Synthetic ASR snapshots, real desktop queue and real local NLLB worker."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

BASE = Path(__file__).resolve().parents[1]
REPORT = BASE / 'diagnostics/stream-translation.json'
UNKNOWN = '--unknown' in sys.argv
SENTENCES = [
    'Could you speak a little more slowly?',
    'Please save the transcript to a local file.',
    'The meeting starts in ten minutes.',
    'We update the parameters using gradient descent.',
    'The training data does not include this example.',
    'The quality is acceptable, but the latency is too high.',
]
if UNKNOWN:
    REPORT = BASE / 'diagnostics/unknown-stream-translation.json'
    SENTENCES = ['But we had to contract with all the Silicon Manufacturers.',
                 'Please save the transcript to a local file.']


def child():
    os.environ['ASR_TRANSLATION_BACKEND'] = 'nllb'
    sys.path.insert(0, str(BASE / 'app'))
    from floating_asr import main
    def driver(app):
        app.autosave.set(False)
        app.proc = SimpleNamespace(stdin=io.StringIO())  # capture boundary only
        app.session_id = 1
        start = time.monotonic()
        snapshots = []
        for sentence in SENTENCES:
            snapshots.extend(sentence.split())
        index = 0

        def feed():
            nonlocal index
            index = min(index + 2, len(snapshots))
            app.events.put({'line': '[live partial @ 1s] ' + ' '.join(snapshots[:index])})
            if index < len(snapshots):
                app.root.after(160, feed)
            else:
                app.proc = None

        def complete():
            if (index == len(snapshots) and not app.translation_busy
                    and app.translation_source == ' '.join(snapshots)):
                result = {'seconds': time.monotonic() - start,
                          'source': app.text, 'pairs': app.translation_pairs,
                          'error': app.translation_error, 'export': app.export_text()}
                REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                app.dirty = False
                app.shutdown()
            else:
                app.root.after(100, complete)
        feed()
        complete()
    main(driver)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        p = subprocess.Popen([sys.executable, __file__, '--child'] + (['--unknown'] if UNKNOWN else []), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = p.communicate(timeout=40)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill.exe', '/PID', str(p.pid), '/T', '/F'], capture_output=True)
            raise AssertionError('Translation never caught up')
        assert p.returncode == 0, err.decode(errors='replace')
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        assert not report['error'], report
        assert [p['en'] for p in report['pairs']] == SENTENCES, report
        assert all(p['zh'] for p in report['pairs']), report
        assert '中文翻译未完成' not in report['export'], report
        if UNKNOWN:
            assert '\u2047' not in report['export'], report
            assert '【此句翻译异常，保留英文】 ' + SENTENCES[0] in report['export'], report
            assert '文件' in report['pairs'][1]['zh'], report
        print(f"{len(SENTENCES)} sentences processed incrementally without loss or duplication in {report['seconds']:.2f}s")
