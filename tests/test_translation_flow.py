import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from translation_flow import matching_pairs, next_chunk, source_prefix, valid_result, Timeline, defer_until, words, timestamp, reconcile_pairs


class TranslationFlowTest(unittest.TestCase):
    def test_early_asr_correction_keeps_later_translations(self):
        pairs = [{'en': 'The wrong term.', 'zh': '旧译文'},
                 {'en': 'Later sentence stays.', 'zh': '后文不变'}]
        text = 'The corrected term. Later sentence stays. New words.'
        result = reconcile_pairs(text, pairs)
        self.assertTrue(result[0]['deferred'])
        self.assertEqual(result[0]['en'], 'The corrected term.')
        self.assertEqual(result[1], pairs[1])
        kept, count = matching_pairs(text, result)
        self.assertEqual(len(kept), 2)
        self.assertEqual(next_chunk(text, count, False, 0), 'New words.')

    def test_timestamps_survive_revisions(self):
        timeline = Timeline()
        timeline.observe('First wrong sentence.', 2)
        timeline.observe('First correct sentence. More words.', 6)
        self.assertEqual(timeline.at(0), 2)
        self.assertEqual(timeline.at(3), 6)
        timeline.observe('First correct sentence. More words. New ending.', 9)
        self.assertEqual(timeline.at(5), 9)
        self.assertEqual(timestamp(3661), '01:01:01')

    def test_backlog_is_bounded_without_losing_english(self):
        text = ' '.join(f'word{i}' for i in range(200))
        timeline = Timeline()
        timeline.observe(text, 1)
        until = defer_until(text, 0, timeline, 20)
        self.assertGreaterEqual(until, 140)
        prefix = source_prefix(text, until)
        remainder = text[len(prefix):].strip()
        self.assertEqual(words(prefix) + words(remainder), words(text))
        self.assertLessEqual(len(words(remainder)), 60)

    def test_only_new_sentence_is_requested(self):
        text = 'The first sentence is complete. The second sentence is complete.'
        pairs = [{'en': 'The first sentence is complete.', 'zh': '一'}]
        kept, count = matching_pairs(text, pairs)
        self.assertEqual(kept, pairs)
        self.assertEqual(next_chunk(text, count, True, 0), 'The second sentence is complete.')

    def test_punctuation_revision_keeps_completed_translation(self):
        pairs = [{'en': 'There are several methods.', 'zh': '一'}]
        kept, count = matching_pairs('There are several methods, and more', pairs)
        self.assertEqual(kept, pairs)
        self.assertEqual(count, 4)

    def test_word_revision_invalidates_only_changed_suffix(self):
        pairs = [{'en': 'First sentence.', 'zh': '一'}, {'en': 'Wrong statement.', 'zh': '二'}]
        kept, count = matching_pairs('First sentence. Correct statement.', pairs)
        self.assertEqual(len(kept), 1)
        self.assertFalse(valid_result('First sentence. Correct statement.', kept, count, 'Wrong statement.'))

    def test_no_punctuation_stream_makes_progress(self):
        text = ' '.join(f'word{i}' for i in range(60))
        chunk = next_chunk(text, 0, True, 0)
        self.assertEqual(len(chunk.split()), 20)
        self.assertNotEqual(next_chunk(text, 20, True, 0), chunk)

    def test_short_tail_waits_but_stop_flushes(self):
        self.assertEqual(next_chunk('I think', 0, True, 10), '')
        self.assertEqual(next_chunk('I think', 0, False, 0), 'I think')
        self.assertEqual(source_prefix('I think.', 2), 'I think.')


if __name__ == '__main__':
    unittest.main()
