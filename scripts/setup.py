"""Create a local Python environment and install fixed runtime/model assets."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv
from assets import BASE, platform_manifest, install


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['hymt', 'nllb', 'both'], default='hymt')
    parser.add_argument('--from-existing', type=Path, help='Reuse verified assets from a previous installation; no transcripts copied')
    parser.add_argument('--hf-endpoint', help='Optional HTTPS Hugging Face mirror chosen by the user')
    args = parser.parse_args()
    supported = (os.name == 'nt' and platform.machine().lower() in ('amd64', 'x86_64')) or (sys.platform == 'darwin' and platform.machine() == 'arm64')
    if not supported or sys.maxsize < 2**32:
        parser.error('Requires Windows x64 or macOS Apple Silicon with native arm64 Python.')
    if sys.version_info[:2] != (3, 11) or sys.version_info < (3, 11, 8):
        parser.error('Use Python 3.11.8 or newer 3.11. With Conda: conda create -n local-caption python=3.11; conda activate local-caption')
    if args.hf_endpoint and not args.hf_endpoint.startswith('https://'):
        parser.error('--hf-endpoint must use HTTPS')
    import tkinter
    print('Model/runtime license references: THIRD_PARTY.md. Downloads contain no private transcripts.', flush=True)
    env = BASE / 'translation/.venv'
    python = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        # Standalone macOS Python needs its original path to find libpython.
        venv.EnvBuilder(with_pip=True, symlinks=os.name != 'nt').create(env)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(BASE / 'requirements.txt')], check=True)
    groups = {'core', 'hymt', 'nllb'} if args.backend == 'both' else {'core', args.backend}
    for item in platform_manifest():
        if item['group'] in groups:
            install(item, args.from_existing, args.hf_endpoint)
    for name in ('diagnostics', 'transcripts'):
        (BASE / name).mkdir(exist_ok=True)
    (BASE / 'installed.json').write_text(json.dumps({'backend': args.backend, 'python': sys.version.split()[0]}), encoding='utf-8')
    subprocess.run([str(python), str(BASE / 'scripts/doctor.py'), '--verify'], check=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('Setup failed:', exc, file=sys.stderr)
        sys.exit(1)
