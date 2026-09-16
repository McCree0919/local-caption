"""NeMo streaming results are utterance-local, not whole-session snapshots."""
from translation_flow import words


class TranscriptHistory:
    def __init__(self):
        self.committed = ''
        self.partial = ''
        self.summary_rejected = False

    @property
    def text(self):
        return ' '.join(s for s in (self.committed, self.partial) if s)

    def observe(self, text, final=False):
        text = text.strip()
        # An empty flush must not erase the last visible partial after a stop.
        if not text:
            return self.text
        self.partial = text
        if final:
            self.committed = self.text
            self.partial = ''
        return self.text

    def summary(self, text):
        """CLI stdout at exit is a whole-session result, possibly multi-line."""
        text = text.strip()
        if not text:
            return self.text
        prefix = words(self.committed)
        if prefix and words(text)[:len(prefix)] != prefix:
            # Keep established history if a truncated/incompatible summary arrives.
            self.summary_rejected = True
            return self.text
        self.committed, self.partial = text, ''
        return self.text
