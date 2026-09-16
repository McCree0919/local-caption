"""Synthetic ASR boundary; real Tk queue, both models, switch, backfill and TXT IO."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

BASE = Path(__file__).resolve().parents[1]
REPORT = BASE / 'diagnostics/caption-backlog.json'
SENTENCES = [
    'The first group will discuss how to build a better product.',
    'The second group will interview customers about their daily work.',
    'Our next meeting will start in ten minutes near the main entrance.',
    'We need to save the transcript to a local file after class.',
    'The training data does not include the examples from this new course.',
    'We use gradient descent to update the parameters of the model.',
    'We need to sign a contract with all the silicon manufacturers.',
    'Please speak a little more slowly so everyone can understand the instructions.',
]


def child():
    os.environ['ASR_TRANSLATION_BACKEND'] = 'hymt'
    sys.path.insert(0, str(BASE / 'app'))
    from floating_asr import main
    def driver(app):
        app.autosave.set(False)
        app.session_file = BASE / 'diagnostics/caption-backlog.txt'
        app.proc = SimpleNamespace(stdin=io.StringIO())
        app.recording_started = time.monotonic() - 30
        app.events.put({'line': '[live partial @ 3s] ' + ' '.join(SENTENCES)})
        start = time.monotonic()
        stage = 0
        report = {}
        def check():
            nonlocal stage
            deferred = [p for p in app.translation_pairs if p.get('deferred')]
            if stage == 0 and deferred:
                report['deferred_count'] = len(deferred)
                report['early_export'] = app.export_text()
                app.proc = None
                app.begin_backfill()
                stage = 1
            elif (stage == 1 and not app.translation_busy and not app.backfill
                  and app.translation_source == app.text):
                report['hymt_pairs'] = app.translation_pairs[:]
                report['hymt_export'] = app.export_text()
                app.backend.set('nllb')
                app.change_backend()
                stage = 2
            elif (stage == 2 and not app.translation_busy and not app.hints_pending
                  and app.translation_source == app.text):
                app.save_auto()
                report.update(seconds=time.monotonic() - start, pairs=app.translation_pairs,
                              error=app.translation_error, text=app.text,
                              saved=app.session_file.read_text(encoding='utf-8'),
                              visible=app.view.get('1.0', 'end'))
                REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                app.dirty = False
                app.shutdown()
                return
            if app.translation_error:
                raise RuntimeError(app.translation_error)
            app.root.after(100, check)
        app.root.after(100, check)
    main(driver)


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        p = subprocess.Popen([sys.executable, __file__, '--child'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            _, err = p.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill.exe', '/PID', str(p.pid), '/T', '/F'], capture_output=True)
            raise AssertionError('Backfill or model switch did not finish')
        assert p.returncode == 0, err.decode(errors='replace')
        r = json.loads(REPORT.read_text(encoding='utf-8'))
        assert r['deferred_count'] > 0 and '待补译' in r['early_export'], r
        assert '待补译' not in r['hymt_export'] and not r['error'], r
        assert [pair['en'] for pair in r['pairs']] == SENTENCES, r
        assert all(pair['backend'] == 'nllb' for pair in r['pairs']), r
        assert all(pair['backend'] == 'hymt' for pair in r['hymt_pairs']), r
        assert '[00:03]' in r['saved'] and '[00:03]' in r['visible'], r
        assert '硅' in r['hymt_pairs'][6]['zh'] and '合同' in r['hymt_pairs'][6]['zh'], r
        assert all(s in r['saved'] for s in SENTENCES), r
        print(f"Deferred {r['deferred_count']} chunks, backfilled, switched models and verified timestamped TXT in {r['seconds']:.2f}s")
