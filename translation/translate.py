"""Offline NLLB / CTranslate2 short-sentence trial, English -> Simplified Chinese."""
import argparse
import datetime
import json
import re
from pathlib import Path
import statistics
import sys
import time

import ctranslate2
import sentencepiece as spm

ROOT = Path(__file__).resolve().parent
SAMPLES = [
    'Could you speak a little more slowly?',
    'Please save the transcript to a local file.',
    'The meeting starts in ten minutes.',
    'I did not say that the model was wrong.',
    'There are likelihood-based methods.',
    'The quality is acceptable, but the latency is too high.',
    'We update the parameters using gradient descent.',
    'The training data does not include this example.',
    'Let us break this problem into smaller steps.',
    'Ask not what your country can do for you.',
]


def repeated_suffix(tokens):
    # Six identical consecutive token phrases is a decode-loop signal.
    for width in range(1, min(16, len(tokens) // 6) + 1):
        if tokens[-width:] * 6 == tokens[-width * 6:]:
            return True
    return False


def repetitive_text(text):
    compact = re.sub(r'[\s,，.。!?！？;；:：]+', '', text)
    return bool(re.search(r'(.{1,24}?)\1{5,}', compact))


class Translator:
    def __init__(self, threads=4, beam=2):
        start = time.perf_counter()
        self.sp = spm.SentencePieceProcessor(model_file=str(ROOT / 'models/sentencepiece.model'))
        self.engine = ctranslate2.Translator(str(ROOT / 'models/nllb-200-distilled-600M-int8'),
            device='cpu', compute_type='int8', inter_threads=1, intra_threads=threads)
        self.load_seconds = time.perf_counter() - start
        self.beam = beam

    def translate(self, text):
        text = text.strip()
        if not text:
            raise ValueError('请输入非空英语短句。')
        start = time.perf_counter()
        tokens = ['eng_Latn'] + self.sp.encode(text, out_type=str) + ['</s>']
        if len(tokens) > 256:
            raise ValueError('文本过长，请拆成短句（最多 256 个源 token）。')
        limit = min(256, max(64, len(tokens) * 4))
        generated = []
        loop_detected = False

        def on_token(step):
            nonlocal loop_detected
            generated.append(step.token_id)
            if repeated_suffix(generated):
                loop_detected = True
                return True
            return False

        def decode(guarded=False):
            options = dict(beam_size=self.beam, max_input_length=256,
                           max_decoding_length=limit, return_end_token=True)
            if guarded:
                options.update(no_repeat_ngram_size=3, repetition_penalty=1.1)
            elif self.beam == 1:
                options['callback'] = on_token
            result = self.engine.translate_batch([tokens], target_prefix=[['zho_Hans']], **options)[0]
            raw = result.hypotheses[0]
            if '<unk>' in raw:
                raise ValueError('模型输出了未知词，无法可靠还原术语；已保留英文。')
            target = [t for t in raw if t not in ('zho_Hans', '</s>', '<s>', '<pad>')]
            return self.sp.decode(target), target, '</s>' in raw

        output, target, ended = decode()
        retried = loop_detected or not ended or repetitive_text(output)
        if retried:
            output, target, ended = decode(guarded=True)
        if not ended or repetitive_text(output) or not output.strip():
            raise ValueError('该短句翻译出现重复或未能正常结束；已阻止异常结果，请保留英文或换成完整句重试。')
        return {'english': text, 'chinese': output,
                'seconds': round(time.perf_counter() - start, 4),
                'source_tokens': len(tokens), 'target_tokens': len(target),
                'repetition_retry': retried}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text', nargs='*')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--beam', type=int, default=2)
    args = parser.parse_args()
    if args.threads < 1 or args.beam < 1:
        parser.error('--threads and --beam must be positive')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    print('正在加载 NLLB 600M INT8 / CPU…', flush=True)
    translator = Translator(args.threads, args.beam)
    print(f'加载 {translator.load_seconds:.2f}s · {translator.engine.compute_type} · {args.threads} threads · beam {args.beam}', flush=True)
    output_dir = ROOT / 'results'
    output_dir.mkdir(exist_ok=True)

    def display(row):
        print(f"EN: {row['english']}\nZH: {row['chinese']}\n耗时: {row['seconds']:.3f}s\n", flush=True)

    if args.benchmark:
        cold = translator.translate(SAMPLES[0])
        rows = []
        for repetition in range(2):
            for sentence in SAMPLES:
                row = translator.translate(sentence)
                row['repetition'] = repetition + 1
                rows.append(row)
                display(row)
        times = sorted(row['seconds'] for row in rows)
        report = {'model': 'NLLB-200 Distilled 600M', 'ctranslate2': ctranslate2.__version__,
            'compute_type': translator.engine.compute_type, 'device': translator.engine.device,
            'threads': args.threads, 'beam': args.beam, 'load_seconds': translator.load_seconds,
            'first_inference': cold, 'median_seconds': statistics.median(times),
            'min_seconds': times[0], 'max_seconds': times[-1], 'rows': rows}
        path = output_dir / f'benchmark-beam{args.beam}-threads{args.threads}.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"中位数 {report['median_seconds']:.3f}s；范围 {times[0]:.3f}–{times[-1]:.3f}s\n结果: {path}")
    elif args.text:
        display(translator.translate(' '.join(args.text)))
    else:
        print('输入英语短句，回车翻译；输入 /quit 退出。结果自动保存为 JSONL。')
        path = output_dir / ('session-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.jsonl')
        while True:
            try:
                text = input('EN > ').strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text == '/quit':
                break
            if not text:
                continue
            try:
                row = translator.translate(text)
                display(row)
                with path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
            except (ValueError, OSError) as exc:
                print(f'错误: {exc}')


if __name__ == '__main__':
    main()
