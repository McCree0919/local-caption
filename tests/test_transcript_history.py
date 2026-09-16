import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from transcript_history import TranscriptHistory


class HistoryTest(unittest.TestCase):
    def test_revisions_only_replace_active_segment(self):
        h = TranscriptHistory()
        h.observe('First wrong')
        h.observe('First corrected.', True)
        h.observe('Second wrong')
        self.assertEqual(h.observe('Second corrected.', True), 'First corrected. Second corrected.')

    def test_repeated_speech_is_not_deduplicated(self):
        h = TranscriptHistory()
        h.observe('Yes.', True)
        self.assertEqual(h.observe('Yes.', True), 'Yes. Yes.')

    def test_empty_flush_keeps_partial(self):
        h = TranscriptHistory()
        h.observe('First.', True)
        h.observe('Tail')
        self.assertEqual(h.observe('', True), 'First. Tail')

    def test_summary_is_not_appended_twice_and_preserves_paragraphs(self):
        h = TranscriptHistory()
        h.observe('First.', True)
        h.observe('Second')
        self.assertEqual(h.summary('First.\nSecond.'), 'First.\nSecond.')
        self.assertEqual(h.summary('First.\nSecond.'), 'First.\nSecond.')

    def test_short_summary_cannot_erase_committed_history(self):
        h = TranscriptHistory()
        h.observe('First.', True)
        h.observe('Second.', True)
        self.assertEqual(h.summary('Second.'), 'First. Second.')
        self.assertTrue(h.summary_rejected)

    def test_long_history_is_not_limited_to_display_size(self):
        h = TranscriptHistory()
        paragraphs = [f'Lecture section {i} ' + 'test ' * 30 for i in range(80)]
        for paragraph in paragraphs:
            h.observe(paragraph, True)
        self.assertGreater(len(h.text), 5000)
        self.assertEqual(h.text, ' '.join(p.strip() for p in paragraphs))


if __name__ == '__main__':
    unittest.main()
