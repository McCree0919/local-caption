"""Real Tk event queue and autosave; controlled ASR events, no model inference."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = Path(os.environ.get('CAPTION_TEST_BASE', Path(__file__).resolve().parents[1]))


def child(output):
    sys.path.insert(0, str(BASE / 'app'))
    import floating_asr
    temporary = tempfile.TemporaryDirectory(prefix='caption-persistence-')
    floating_asr.SAVES = Path(temporary.name)
    outcome = {'checks': [], 'errors': []}

    def driver(app):
        app.root.withdraw()
        app.chinese.set(False)
        app.session_file = Path(temporary.name) / 'session.txt'
        steps = [
            ('[live partial @ 1s] First lesson wrong.', 'First lesson wrong.'),
            ('[live final @ 2s] First lesson complete.', 'First lesson complete.'),
            ('[live partial @ 3s] Second lesson wrong.', 'First lesson complete. Second lesson wrong.'),
            ('[live partial @ 3.5s] Second lesson\ncorrected.', 'First lesson complete. Second lesson\ncorrected.'),
            ('[live final @ 4s] Second lesson corrected.', 'First lesson complete. Second lesson corrected.'),
            ({'transcript_summary': 'First lesson complete.\nSecond lesson corrected.\nLast paragraph.'},
             'First lesson complete.\nSecond lesson corrected.\nLast paragraph.'),
            ('unprefixed engine diagnostic', 'First lesson complete.\nSecond lesson corrected.\nLast paragraph.'),
        ]

        def feed(index=0):
            if index == len(steps):
                Path(output).write_text(json.dumps(outcome), encoding='utf-8')
                app.dirty = False
                app.shutdown()
                return
            line, expected = steps[index]
            app.last_save = 0
            app.events.put(line if isinstance(line, dict) else {'line': line})

            def check():
                saved = app.session_file.read_text(encoding='utf-8')
                actual = saved.split('\n\n中文')[0].removeprefix('ENGLISH\n')
                outcome['checks'].append({'expected': expected, 'actual': actual})
                if actual != expected:
                    outcome['errors'].append(f'step {index}: saved history was replaced')
                if index == 1:
                    # Controlled completed translation; no translation model involved.
                    app.translation_pairs = [{'en': 'First lesson complete.', 'zh': '第一段已完成。', 'start': 1}]
                if index >= 2 and '第一段已完成。' not in saved:
                    outcome['errors'].append(f'step {index}: earlier translation was lost')
                feed(index + 1)
            app.root.after(350, check)
        feed()
    floating_asr.main(driver)
    temporary.cleanup()


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[-1])
    else:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            p = subprocess.run([sys.executable, __file__, '--child', str(output)],
                               capture_output=True, timeout=20)
            assert p.returncode == 0, p.stderr.decode(errors='replace')
            result = json.loads(output.read_text(encoding='utf-8'))
            print(json.dumps(result, indent=2))
            assert not result['errors'], result['errors']
