"""Bounded, independent disk writer for captured audio before enhancement/downmix."""
from pathlib import Path
import queue
import threading
import wave
import numpy as np


class AudioArchive:
    def __init__(self, destination, rate, channels):
        self.path = Path(destination)
        self.partial_path = self.path.with_suffix('.partial.wav')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise FileExistsError(self.path)
        self.file = self.partial_path.open('xb')
        self.wave = wave.open(self.file, 'wb')
        self.wave.setnchannels(channels)
        self.wave.setsampwidth(2)
        self.wave.setframerate(rate)
        self.wave.writeframes(b'')
        self.queue = queue.Queue(maxsize=120)
        self.error = None
        self.frames = 0
        self.channels = channels
        self.closed = False
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()

    def submit(self, float32_bytes):
        if self.closed:
            raise RuntimeError('录音写入器已关闭')
        if self.error:
            raise RuntimeError('录音保存失败：' + str(self.error))
        try:
            self.queue.put_nowait(float32_bytes)
        except queue.Full:
            raise RuntimeError('录音磁盘写入积压超过 12 秒；停止采集以防继续丢失') from None

    def _write(self):
        try:
            while True:
                data = self.queue.get()
                if data is None:
                    break
                x = np.frombuffer(data, dtype='<f4')
                if len(x) % self.channels:
                    raise ValueError('Incomplete audio frame')
                pcm = (np.clip(x, -1, 32767 / 32768) * 32768).astype('<i2')
                # writeframes updates the WAV header each block, so a partial file
                # remains readable if capture is interrupted before normal close.
                self.wave.writeframes(pcm.tobytes())
                self.file.flush()
                self.frames += len(x) // self.channels
        except Exception as exc:
            self.error = exc
        finally:
            try:
                self.wave.close()
            except Exception as exc:
                self.error = self.error or exc
            self.file.close()

    def close(self):
        if not self.closed:
            self.closed = True
            if self.thread.is_alive():
                try:
                    self.queue.put(None, timeout=10)
                except queue.Full:
                    raise RuntimeError('录音写盘未完成，保留 partial.wav 文件') from None
                self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError('录音写盘未完成，保留 partial.wav 文件')
            if self.error:
                raise RuntimeError('录音保存失败，保留 partial.wav：' + str(self.error))
            self.partial_path.rename(self.path)
        return self.path
