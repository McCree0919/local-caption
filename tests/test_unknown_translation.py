"""Exercise unknown-word handling through the actual desktop JSONL worker."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UnknownTranslationTest(unittest.TestCase):
    def test_unknown_preserves_source_and_next_request_runs(self):
        sentences = [
            'But we had to contract with all the Silicon Manufacturers.',
            'Please save the transcript to a local file.',
        ]
        requests = [dict(text=text, session=1, offset=i) for i, text in enumerate(sentences)]
        result = subprocess.run(
            [str(ROOT / 'translation/.venv/Scripts/python.exe'),
             str(ROOT / 'translation/desktop_worker.py')],
            input=''.join(json.dumps(row) + '\n' for row in requests),
            text=True, encoding='utf-8', capture_output=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows), 2)
        bad = rows[0]['pairs'][0]
        self.assertNotIn('\u2047', bad['zh'])
        self.assertIn(sentences[0], bad['zh'])
        self.assertIn('未知词', bad['warning'])
        good = rows[1]['pairs'][0]
        self.assertNotIn('warning', good)
        self.assertIn('文件', good['zh'])
        self.assertEqual(rows[1]['offset'], 1)


if __name__ == '__main__':
    unittest.main()
