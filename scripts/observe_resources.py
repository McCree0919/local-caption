"""Read-only process-tree and llama-server timing observer for an existing app."""
import argparse
import json
from pathlib import Path
import re
import statistics
import time

import psutil


def summary(values):
    if not values:
        return {'count': 0}
    ordered = sorted(values)
    return dict(count=len(values), mean=statistics.mean(values), median=statistics.median(values),
                p95=ordered[max(0, __import__('math').ceil(.95 * len(ordered)) - 1)], max=max(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--output', type=Path, default=Path('diagnostics/active-resources.json'))
    args = parser.parse_args()
    root = psutil.Process(args.pid)
    known, baseline, latest = {}, {}, {}
    samples = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open(encoding='utf-8', errors='replace') as log:
        log.seek(0, 2)
        started_epoch = time.time()
        start = time.perf_counter()
        while time.perf_counter() - start < args.seconds:
            try:
                for process in [root] + root.children(recursive=True):
                    known[(process.pid, process.create_time())] = process
            except psutil.Error:
                pass
            groups = {}
            for key, process in list(known.items()):
                try:
                    name = process.name().lower()
                    group = 'asr' if name == 'nemo-speech.exe' else 'hymt' if name == 'llama-server.exe' else 'gui_and_workers'
                    memory = process.memory_info()
                    cpu = process.cpu_times()
                    value = cpu.user + cpu.system
                    baseline.setdefault(key, value)
                    latest[key] = value
                    item = groups.setdefault(group, dict(rss_bytes=0, private_bytes=0))
                    item['rss_bytes'] += memory.rss
                    item['private_bytes'] += getattr(memory, 'private', 0)
                except psutil.Error:
                    pass
            samples.append(dict(elapsed=time.perf_counter() - start, groups=groups,
                                available_ram_bytes=psutil.virtual_memory().available))
            time.sleep(1)
        elapsed = time.perf_counter() - start
        new_log = log.read()
    # Never save the log itself: it may contain paths or generated text.
    totals = [float(v) / 1000 for v in re.findall(r'total time\s*=\s*([\d.]+) ms', new_log)]
    generation = [float(v) for v in re.findall(r'(?<!prompt )eval time\s*=.*?,\s*([\d.]+) tokens per second', new_log)]
    resources = {}
    for group in ('asr', 'hymt', 'gui_and_workers', 'total'):
        rss, private = [], []
        for row in samples:
            selected = list(row['groups'].values()) if group == 'total' else [row['groups'].get(group, {})]
            rss.append(sum(v.get('rss_bytes', 0) for v in selected) / 2**20)
            private.append(sum(v.get('private_bytes', 0) for v in selected) / 2**20)
        resources[group] = dict(rss_mib=summary(rss), private_commit_mib=summary(private))
    result = dict(started_epoch=started_epoch, ended_epoch=time.time(), duration_seconds=elapsed,
                  sample_interval_seconds=1, sample_count=len(samples),
                  cpu_percent_machine=sum(latest[k] - baseline[k] for k in latest) / elapsed / psutil.cpu_count() * 100,
                  minimum_available_ram_gib=min(r['available_ram_bytes'] for r in samples) / 2**30,
                  resources=resources, inference_seconds=summary(totals), generation_tokens_per_second=summary(generation))
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
