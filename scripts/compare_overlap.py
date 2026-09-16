"""Experimental Hy-MT2 left-context overlap; never enabled in the desktop path."""
import argparse
import json
from pathlib import Path
import statistics
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'translation'))
from hymt_translate import Translator


class ContextTranslator(Translator):
    context = ''

    def _request(self, path, payload=None, timeout=60):
        if payload is not None and self.context:
            target = payload['messages'][0]['content'].split('\n\n', 1)[-1]
            payload['messages'][0]['content'] = (
                '参考以下前文理解语境。前文已经翻译，不要重复输出前文。只将待译文本翻译为简体中文，'
                '不要解释，不要补写未出现的信息。\n\n前文：\n' + self.context + '\n\n待译文本：\n' + target)
        return super()._request(path, payload, timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_json', type=Path, help='Local JSON containing sources[].chunks; never packaged')
    args = parser.parse_args()
    sources = json.loads(args.source_json.read_text(encoding='utf-8'))['sources']
    output = BASE / 'diagnostics/overlap-comparison.json'
    output.parent.mkdir(exist_ok=True)
    engine = ContextTranslator(threads=4)
    rows = []
    try:
        for source in sources:
            history = []
            for index, chunk in enumerate(source['chunks']):
                for mode in ('baseline', 'overlap16'):
                    engine.context = ' '.join(history[-16:]) if mode == 'overlap16' else ''
                    try:
                        result = engine.translate(chunk)
                    except ValueError as exc:
                        result = {'error': str(exc)}
                    rows.append(dict(source=source['id'], index=index, mode=mode, context=engine.context, **result))
                    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(source['id'], index, mode, result.get('seconds'), flush=True)
                history.extend(chunk.split())
    finally:
        engine.close()
    summary = {mode: {'requests': len([r for r in rows if r['mode'] == mode]),
                      'median_seconds': statistics.median(r['seconds'] for r in rows if r['mode'] == mode and 'seconds' in r),
                      'errors': sum('error' in r for r in rows if r['mode'] == mode)}
               for mode in ('baseline', 'overlap16')}
    (output.parent / 'overlap-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
