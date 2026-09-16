"""Plan incremental translation from revisable ASR snapshots."""
import re

WORD = re.compile(r"\w+(?:['’\-]\w+)*", re.UNICODE)


def words(text):
    return [m.group().lower().replace('’', "'") for m in WORD.finditer(text)]


def matching_pairs(text, pairs):
    if not pairs:
        return [], 0
    current = words(text)
    count = 0
    kept = []
    for pair in pairs:
        tokens = words(pair['en'])
        if current[count:count + len(tokens)] != tokens:
            break
        kept.append(pair)
        count += len(tokens)
    return kept, count


def source_prefix(text, count):
    if not count:
        return ''
    spans = list(WORD.finditer(text))
    if count >= len(spans):
        return text
    return text[:spans[count].start()].rstrip()


def reconcile_pairs(text, pairs):
    """Reuse unchanged later captions after a local ASR correction.

    A changed earlier phrase must not invalidate minutes of later translations.
    Search is bounded to avoid aligning repeated text far away in the recording.
    """
    if not pairs:
        return []
    spans = list(WORD.finditer(text))
    current = words(text)
    kept = []
    count = 0
    for pair in pairs:
        tokens = words(pair['en'])
        if not tokens:
            continue
        found = None
        for position in range(count, min(len(current) - len(tokens) + 1, count + 128)):
            if current[position:position + len(tokens)] == tokens:
                found = position
                break
        if found is None:
            continue
        while count < found:
            gap_end = spans[found].start()
            gap = next_chunk(text[:gap_end], count, False, 0)
            if not gap:
                break
            kept.append({'en': gap, 'zh': '【待补译：识别文字有修订，已保留英文】', 'deferred': True})
            count += len(words(gap))
        kept.append(pair)
        count = found + len(tokens)
    return kept


def next_chunk(text, count, recording, stable_seconds):
    spans = list(WORD.finditer(text))
    if count >= len(spans):
        return ''
    tail = text[spans[count].start():].strip()
    remaining = list(WORD.finditer(tail))
    # Prefer sentence punctuation. Hold a changing, short unfinished tail.
    for end in re.finditer(r'[.!?](?:["\u201d\u2019])?(?=\s|$)', tail):
        candidate = tail[:end.end()]
        size = len(words(candidate))
        if 0 < size <= 28:
            return candidate
        if size > 28:
            break
    if len(remaining) >= 24:
        limit = remaining[23].end()
        clauses = [m.end() for m in re.finditer(r'[,;:]', tail[:limit])
                   if len(words(tail[:m.end()])) >= 8]
        return tail[:clauses[-1] if clauses else remaining[19].end()].strip()
    if not recording or (stable_seconds >= 1.5 and len(remaining) >= 4):
        return tail
    return ''


def valid_result(text, pairs, offset, source):
    _, completed = matching_pairs(text, pairs)
    tokens = words(source)
    return completed == offset and words(text)[offset:offset + len(tokens)] == tokens


def timestamp(seconds):
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


class Timeline:
    """Approximate audio-relative first-observed times, not word alignment."""
    def __init__(self):
        self.tokens = []
        self.times = []

    def observe(self, text, seconds):
        current = words(text)
        prefix = 0
        while prefix < min(len(current), len(self.tokens)) and current[prefix] == self.tokens[prefix]:
            prefix += 1
        suffix = 0
        while (suffix < min(len(current), len(self.tokens)) - prefix
               and current[-suffix - 1] == self.tokens[-suffix - 1]):
            suffix += 1
        # Rewritten words keep the original region's time; new words use now.
        middle = len(current) - prefix - suffix
        old_end = len(self.times) - suffix
        middle_times = self.times[prefix:old_end][:middle]
        # Newly appended audio must get its own time even when an earlier word
        # was corrected in the same snapshot. Insertions before an unchanged
        # suffix are retrospective ASR edits, so anchor those to that suffix.
        added_at = self.times[old_end] if suffix else seconds
        middle_times += [added_at] * (middle - len(middle_times))
        self.times = self.times[:prefix] + middle_times + (self.times[-suffix:] if suffix else [])
        self.tokens = current

    def at(self, offset):
        return self.times[min(offset, len(self.times) - 1)] if self.times else 0


def defer_until(text, count, timeline, now, max_words=60, max_age=12):
    """Bound live pending work; retain the skipped source explicitly for backfill."""
    total = len(timeline.tokens)
    if total - count <= max_words and (total - count <= 28 or now - timeline.at(count) <= max_age):
        return count
    target = max(count, total - 28)
    # Advance in the same chunks used by the translator, preserving all source.
    while count < target:
        chunk = next_chunk(text, count, False, 0)
        size = len(words(chunk))
        if not size or count + size > target:
            break
        count += size
    return count
