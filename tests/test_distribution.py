"""Source package privacy boundary and archive traversal regression."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from assets import extract
from package_source import source_files, BASE


class DistributionTest(unittest.TestCase):
    def test_package_excludes_user_data_and_binaries(self):
        paths = [p.relative_to(BASE).as_posix() for p in source_files()]
        for path in paths:
            self.assertFalse(any(part in path.split('/') for part in
                ['transcripts', 'diagnostics', '.venv', 'models', 'runtime', '.downloads']))
            self.assertNotIn('preferences.json', path)
        self.assertIn('start.cmd', paths)
        self.assertIn('start.command', paths)

    def test_zip_cannot_escape_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../escaped.txt', 'bad')
            with self.assertRaises(ValueError):
                extract(archive, root / 'output')
            self.assertFalse((root / 'escaped.txt').exists())


if __name__ == '__main__':
    unittest.main()
