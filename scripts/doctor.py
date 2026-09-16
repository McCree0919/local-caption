"""Check runtime dependencies and assets before opening the GUI."""
import argparse
import importlib
import os
import platform
import sys
from assets import BASE, platform_manifest, installed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='Hash all installed model and runtime files')
    args = parser.parse_args()
    errors = []
    supported = (os.name == 'nt' and platform.machine().lower() in ('amd64', 'x86_64')) or (sys.platform == 'darwin' and platform.machine() == 'arm64')
    if not supported:
        errors.append('Requires Windows x64 or native Apple Silicon macOS.')
    for module in ('tkinter', 'ctranslate2', 'numpy', 'sentencepiece') + (('pyaudiowpatch',) if os.name == 'nt' else ()):
        try:
            importlib.import_module(module)
        except Exception as exc:
            errors.append(f'{module}: {exc}')
    ready = {g: all(installed(a, args.verify) for a in platform_manifest() if a['group'] == g) for g in ('core', 'hymt', 'nllb')}
    if not ready['core']:
        errors.append('ASR runtime/model/demo missing or invalid. Rerun setup.')
    if not (ready['hymt'] or ready['nllb']):
        errors.append('No complete translation backend. Rerun setup.')
    for directory in ('transcripts', 'diagnostics'):
        try:
            p = BASE / directory
            p.mkdir(exist_ok=True)
            import tempfile
            with tempfile.TemporaryFile(dir=p):
                pass
        except OSError as exc:
            errors.append(f'{directory} is not writable: {exc}')
    print('Local Caption | Python', platform.python_version())
    print('Backends:', ready)
    if errors:
        print('\n'.join('ERROR: ' + e for e in errors))
        return 1
    print('Ready. First model load can take several seconds. No audio capture started.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
