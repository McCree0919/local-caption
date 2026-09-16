"""Capture default Windows output using WASAPI; stream locally into NeMo ASR."""
import json
import ctypes
from ctypes import wintypes
import msvcrt
import os
from pathlib import Path
import queue
import sys
import threading
import time

BASE = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    lock = threading.Lock()
    def emit(event):
        with lock:
            print(json.dumps(event, ensure_ascii=True), flush=True)
    stop = threading.Event()
    ready = threading.Event()
    def listen():
        # A blocking CRT stdin read can deadlock NumPy's native-module import
        # on Windows. Poll the pipe without holding its CRT descriptor lock.
        peek = ctypes.WinDLL('kernel32', use_last_error=True).PeekNamedPipe
        peek.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        available = wintypes.DWORD()
        while peek(handle, None, 0, None, ctypes.byref(available), None) and not available.value:
            if stop.wait(0.05):
                return
        stop.set()
        if not ready.is_set():
            emit({'exit': 0, 'cancelled': True})
            os._exit(0)  # Cancels native model loading before capture starts.
    threading.Thread(target=listen, daemon=True).start()
    # Native DLL diagnostics must not fill the GUI's stderr pipe or enter subtitles.
    log_path = BASE / 'diagnostics' / f'loopback-{os.getpid()}.log'
    log_path.parent.mkdir(exist_ok=True)
    log = log_path.open('w', encoding='utf-8')
    os.dup2(log.fileno(), 2)
    recognizer = None
    capture = None
    audio = None
    code = 0
    try:
        import numpy as np
        import pyaudiowpatch as pa
        from asr_stream import StreamRecognizer
        audio = pa.PyAudio()
        device = audio.get_default_wasapi_loopback()
        rate, channels = int(device['defaultSampleRate']), int(device['maxInputChannels'])
        if not channels:
            raise RuntimeError('默认输出设备不支持系统声音采集。')
        recognizer = StreamRecognizer()
        blocks = queue.Queue(maxsize=120)  # 12 seconds, then stop explicitly; never silently drop.
        fault = []
        captured = 0
        peak = 0.0
        processed = 0.0
        started = time.monotonic()
        def callback(data, frame_count, timing, status):
            nonlocal captured, peak
            if stop.is_set():
                return (None, pa.paComplete)
            if status:
                fault.append(f'系统音频采集发生溢出或设备错误（{status}），请停止其他高负载任务后重试。')
                stop.set()
                return (None, pa.paComplete)
            samples = np.frombuffer(data, dtype=np.float32).reshape(-1, channels).mean(axis=1).astype(np.float32)
            peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
            try:
                blocks.put_nowait(samples)
                captured += len(samples)
            except queue.Full:
                fault.append('音频待识别超过 12 秒，已停止采集以避免继续积压；末尾可能不完整。')
                stop.set()
                return (None, pa.paComplete)
            return (None, pa.paContinue)
        capture = audio.open(format=pa.paFloat32, channels=channels, rate=rate,
            input=True, input_device_index=device['index'], frames_per_buffer=rate // 10,
            stream_callback=callback, start=False)
        ready.set()
        if stop.is_set():
            return
        capture.start_stream()
        emit({'line': '[live] listening system audio'})
        emit({'capture_device': device['name']})
        last_metrics = 0
        previous = ''
        def publish(results):
            nonlocal processed, previous
            for result in results:
                processed = max(processed, result['processed'])
                text = result['text']
                if text != previous or result['final']:
                    elapsed = max(0.0, time.monotonic() - started - max(0, captured / rate - processed))
                    emit({'line': f"[live {'final' if result['final'] else 'partial'} @ {elapsed:.2f}s] {text}"})
                    previous = text
        def metrics(force=False):
            nonlocal last_metrics
            now = time.monotonic()
            if force or now - last_metrics >= 0.5:
                emit({'audio_metrics': dict(elapsed=now - started, captured_seconds=captured / rate,
                    processed_seconds=processed, backlog_seconds=max(0, captured / rate - processed),
                    queued_blocks=blocks.qsize(), level=peak, stopped=stop.is_set())})
                last_metrics = now
        while not stop.is_set() or not blocks.empty():
            try:
                samples = blocks.get(timeout=0.1)
            except queue.Empty:
                if not capture.is_active() and not stop.is_set():
                    raise RuntimeError('系统声音设备已停止或断开，请重新选择默认播放设备后重试。')
                metrics()
                continue
            recognizer.push(samples, rate)
            publish(recognizer.results())
            metrics()
        capture.stop_stream()
        publish(recognizer.finish())
        metrics(True)
        if fault:
            raise RuntimeError(fault[0])
    except Exception as exc:
        code = 1
        emit({'line': '[error] 系统声音：' + str(exc)})
    finally:
        stop.set()
        if capture:
            capture.close()
        if audio:
            audio.terminate()
        if recognizer:
            recognizer.close()
        emit({'exit': code, 'cancelled': code == 0})
    return code


if __name__ == '__main__':
    sys.exit(main())
