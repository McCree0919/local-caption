from pathlib import Path
import sys
import tempfile
import unittest
import wave
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from audio_archive import AudioArchive


class ArchiveTest(unittest.TestCase):
    def test_saved_wav_keeps_channels_duration_and_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.wav'
            archive = AudioArchive(path, 48000, 2)
            # Distinct channels: archive must precede ASR mono downmix/enhancement.
            block = np.tile(np.array([.25, -.5], dtype='<f4'), 4800)
            for _ in range(3):
                archive.submit(block.tobytes())
            self.assertEqual(archive.close(), path)
            self.assertFalse(archive.partial_path.exists())
            with wave.open(str(path)) as f:
                self.assertEqual((f.getnchannels(), f.getframerate(), f.getnframes()), (2, 48000, 14400))
                samples = np.frombuffer(f.readframes(f.getnframes()), dtype='<i2').reshape(-1, 2)
            self.assertTrue(np.all(samples[:, 0] == 8192))
            self.assertTrue(np.all(samples[:, 1] == -16384))
            self.assertEqual(archive.close(), path)

    def test_existing_recording_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.wav'
            path.write_bytes(b'existing')
            with self.assertRaises(FileExistsError):
                AudioArchive(path, 16000, 1)
            self.assertEqual(path.read_bytes(), b'existing')


if __name__ == '__main__':
    unittest.main()
