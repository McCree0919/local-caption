"""Local Hy-MT2 GGUF adapter. The worker owns a loopback-only llama server."""
import atexit
import ctypes
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent / 'hymt'


class Translator:
    def __init__(self, threads=4):
        start = time.perf_counter()
        self.process = None
        self.log = None
        self.job = None
        model = ROOT / 'models/Hy-MT2-1.8B-Q4_K_M.gguf'
        engine = ROOT / ('runtime/llama-server.exe' if os.name == 'nt' else 'runtime/llama-b11005/llama-server')
        if not model.is_file() or not engine.is_file():
            raise FileNotFoundError('缺少 Hy-MT2 模型或 llama-server，请检查 translation/hymt。')
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.key = uuid.uuid4().hex
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.log = (ROOT / f'server-{os.getpid()}.log').open('w', encoding='utf-8')
        self.process = subprocess.Popen([
            str(engine), '-m', str(model), '--host', '127.0.0.1', '--port', str(port),
            '--api-key', self.key, '-ngl', '0', '-t', str(threads), '-tb', str(threads),
            '-c', '2048', '-np', '1', '--jinja', '--no-warmup', '--cache-ram', '0',
        ], stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            if os.name == 'nt':
                self._own_process()
            atexit.register(self.close)
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('Hy-MT2 加载失败，请查看 translation/hymt/server 日志。')
                try:
                    self._request('/health', timeout=1)
                    self.load_seconds = time.perf_counter() - start
                    return
                except (OSError, ValueError):
                    time.sleep(0.15)
            raise TimeoutError('Hy-MT2 加载超过 75 秒。')
        except Exception:
            self.close()
            raise

    def _own_process(self):
        # KILL_ON_JOB_CLOSE releases the model even if its Python worker crashes.
        from ctypes import wintypes
        class Limits(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                        ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', wintypes.DWORD),
                        ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
                        ('ActiveProcessLimit', wintypes.DWORD), ('Affinity', ctypes.c_size_t),
                        ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                         'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', Limits), ('IoInfo', IO),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.job = kernel.CreateJobObjectW(None, None)
        if not self.job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000
        if not kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(self.job, int(self.process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def _request(self, path, payload=None, timeout=60):
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(self.url + path, data=body,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        with self.http.open(request, timeout=timeout) as response:
            return json.load(response)

    def translate(self, text):
        text = text.strip()
        if not text or len(text) > 2000:
            raise ValueError('请输入不超过 2000 字符的英语短句。')
        start = time.perf_counter()
        response = self._request('/v1/chat/completions', {
            'messages': [{'role': 'user', 'content':
                '将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n' + text}],
            'temperature': 0.7, 'top_p': 0.6, 'top_k': 20, 'repeat_penalty': 1.05,
            'seed': 42, 'max_tokens': 256, 'stream': False,
        })
        choice = response['choices'][0]
        output = choice['message']['content'].strip()
        compact = re.sub(r'[\s,，.。!?！？;；:：]+', '', output)
        if (choice['finish_reason'] != 'stop' or not output or '<unk>' in output
                or '\u2047' in output or re.search(r'(.{1,24}?)\1{5,}', compact)):
            raise ValueError('Hy-MT2 输出异常或达到长度上限，已保留英文。')
        usage = response.get('usage', {})
        return dict(english=text, chinese=output, seconds=round(time.perf_counter() - start, 4),
                    source_tokens=usage.get('prompt_tokens'), target_tokens=usage.get('completion_tokens'))

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.log:
            self.log.close()
            self.log = None
        atexit.unregister(self.close)
