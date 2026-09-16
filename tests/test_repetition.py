"""Regression for a real NLLB degenerate decode, using the installed CPU model."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'translation'))
from translate import Translator, repetitive_text


class RepetitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.translator = Translator(threads=4, beam=1)

    def test_travelers_does_not_loop(self):
        row = self.translator.translate('travelers people traveling airports who else ride in Waymos')
        self.assertLessEqual(row['chinese'].count('旅行者'), 2, row['chinese'])
        self.assertLess(row['target_tokens'], 80)
        self.assertIn('机场', row['chinese'])
        print(row['chinese'].encode('unicode_escape').decode(), flush=True)

    def test_wait_does_not_loop(self):
        row = self.translator.translate("don't shout it out like we did in the last class or shouting out wait wait to shout it out")
        self.assertFalse(repetitive_text(row['chinese']))
        self.assertLess(row['chinese'].count('等'), 6)
        self.assertLess(row['target_tokens'], 100)
        print(row['chinese'].encode('unicode_escape').decode(), flush=True)

    def test_short_natural_repetition_is_not_a_loop(self):
        self.assertFalse(repetitive_text('等一等，先等等。'))
        self.assertTrue(repetitive_text('等' * 244))
        self.assertTrue(repetitive_text('旅行者 ' * 85))


if __name__ == '__main__':
    unittest.main()
