"""JSON-lines worker: keep NLLB resident and reuse unchanged short sentences."""
from collections import OrderedDict
import json
import re
import sys
import time

def segments(text):
    # Basic English sentence boundaries; cap long unpunctuated ASR runs.
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    for sentence in sentences:
        words = sentence.split()
        for i in range(0, len(words), 28):
            yield ' '.join(words[i:i + 28])


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    translator = None
    backend = None
    cache = OrderedDict()
    for line in sys.stdin:
        request = json.loads(line)
        try:
            start = time.perf_counter()
            selected = request.get('backend', 'nllb')
            if selected not in ('nllb', 'hymt'):
                raise ValueError('未知翻译模型')
            if backend != selected:
                if translator is not None:
                    if hasattr(translator, 'close'):
                        translator.close()
                    translator = None
                    import gc
                    gc.collect()
                backend = None
                cache.clear()
                if selected == 'hymt':
                    from hymt_translate import Translator
                    translator = Translator(threads=4)
                else:
                    from translate import Translator
                    translator = Translator(threads=4, beam=1)
                backend = selected
            pairs = []
            for sentence in segments(request['text']):
                try:
                    if sentence not in cache:
                        cache[sentence] = translator.translate(sentence)['chinese']
                except ValueError as exc:
                    # One unstable fragment must not stop the rest of a lecture.
                    # Keep its English explicitly instead of inventing a Chinese
                    # translation or caching the failed generation.
                    pairs.append({'en': sentence, 'zh': '【此句翻译异常，保留英文】 ' + sentence,
                                  'warning': str(exc)})
                    continue
                cache.move_to_end(sentence)
                pairs.append({'en': sentence, 'zh': cache[sentence]})
                while len(cache) > 256:
                    cache.popitem(last=False)
            response = {**request, 'pairs': pairs, 'seconds': time.perf_counter() - start}
        except Exception as exc:
            response = {**request, 'error': str(exc)}
        print(json.dumps(response, ensure_ascii=True), flush=True)
    if translator is not None and hasattr(translator, 'close'):
        translator.close()


if __name__ == '__main__':
    main()
