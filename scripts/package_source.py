"""Build a source-only share archive from an explicit allowlist."""
from pathlib import Path
import zipfile

BASE = Path(__file__).resolve().parents[1]
ROOT_FILES = ['README.md', 'CONTRIBUTING.md', 'THIRD_PARTY.md', 'LICENSE', '.gitignore', '.gitattributes', 'assets.json',
              'requirements.txt', 'setup.cmd', 'start.cmd', 'doctor.cmd', 'setup.command', 'start.command']


def source_files():
    paths = [BASE / name for name in ROOT_FILES]
    for folder in ('app', 'translation', 'tests', 'scripts'):
        paths.extend(sorted((BASE / folder).glob('*.py')))
    paths.extend(sorted((BASE / 'docs').glob('*.md')))
    paths.extend(sorted((BASE / '.github/workflows').glob('*.yml')))
    paths.extend(sorted((BASE / '.github/ISSUE_TEMPLATE').glob('*.md')))
    paths.extend(sorted((BASE / '.github').glob('*.md')))
    return paths


if __name__ == '__main__':
    output = BASE / 'dist/local-caption-source.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in source_files():
            z.write(path, 'local-caption/' + path.relative_to(BASE).as_posix())
    print(output)
