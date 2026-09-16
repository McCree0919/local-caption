"""Pinned downloads, SHA-256 checks, and safe archive extraction."""
import hashlib
import json
import sys
from pathlib import Path
import shutil
import subprocess
import zipfile
import tarfile

BASE = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((BASE / 'assets.json').read_text(encoding='utf-8'))


def platform_manifest():
    target = 'windows' if sys.platform == 'win32' else 'macos'
    return [a for a in MANIFEST if a['platform'] in ('all', target)]


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def files(item):
    target = BASE / item['target']
    return {target / name: sha for name, sha in item['files'].items()} if item['archive'] else {target: item['sha256']}


def installed(item, full=False):
    regular = all(p.is_file() and (not full or digest(p) == sha) for p, sha in files(item).items())
    links = all((BASE / item['target'] / name).is_file() for name in item.get('links', {}))
    return regular and links


def extract(archive, target, kind='zip'):
    target = target.resolve()
    if kind == 'tar':
        with tarfile.open(archive) as t:
            t.extractall(target, filter='data')
        return
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            resolved = (target / member.filename).resolve()
            if not resolved.is_relative_to(target):
                raise ValueError('Unsafe archive entry: ' + member.filename)
        z.extractall(target)


def install(item, source=None, endpoint=None):
    if installed(item, full=True):
        print('Verified:', item['name'], flush=True)
        return
    cache = BASE / '.downloads' / (item['name'] + ('.zip' if item['archive'] else '.bin'))
    cache.parent.mkdir(exist_ok=True)
    if not cache.exists() or digest(cache) != item['sha256']:
        original = source / item['source'] if source else None
        part = cache.with_suffix(cache.suffix + '.part')
        if original and original.is_file():
            print('Import verified asset:', item['name'], flush=True)
            if digest(original) != item['sha256']:
                raise ValueError('Source hash mismatch: ' + str(original))
            shutil.copyfile(original, part)
        else:
            url = item['url']
            if endpoint and url.startswith('https://huggingface.co/'):
                url = endpoint.rstrip('/') + url[len('https://huggingface.co'):]
            print('Download:', item['name'], url, flush=True)
            curl = 'curl.exe' if sys.platform == 'win32' else 'curl'
            if not shutil.which(curl):
                raise RuntimeError('curl is required for resumable downloads.')
            subprocess.run([curl, '--fail', '--location', '--retry', '3',
                            '--connect-timeout', '20', '--continue-at', '-', '--output', str(part), url], check=True)
        if digest(part) != item['sha256']:
            part.unlink()  # Known partial cache file only; preserve installed assets.
            raise ValueError('Download hash mismatch: ' + item['name'] + '; rerun setup.')
        part.replace(cache)
    target = BASE / item['target']
    if item['archive']:
        extract(cache, target, item.get('format', 'zip'))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cache, target)
    if not installed(item, full=True):
        raise RuntimeError('Installed asset verification failed: ' + item['name'])
