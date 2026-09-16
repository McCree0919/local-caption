"""Local desktop UI and isolated Windows-console worker for NeMo Speech."""
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import signal
from platform_support import WINDOWS, PYTHON, process_options, kill_tree, open_folder
from translation_flow import matching_pairs, next_chunk, source_prefix, valid_result, words, Timeline, timestamp, defer_until, reconcile_pairs

BASE = Path(__file__).resolve().parents[1]
MODEL = BASE / 'models/nemotron-speech-streaming-en-0.6b.q8_0.gguf'
ENGINE = BASE / ('runtime/bin/nemo-speech.exe' if WINDOWS else 'runtime/nemo-speech/bin/nemo-speech')
SAVES = BASE / 'transcripts'
PREFERENCES = BASE / 'preferences.json'
BACKENDS = {'nllb': 'NLLB 600M INT8', 'hymt': 'Hy-MT2 1.8B Q4'}
INPUTS = {'live': '麦克风', **({'system': '系统声音'} if WINDOWS else {})}


def available_backends():
    return {key for key, path in {
        'nllb': 'translation/models/nllb-200-distilled-600M-int8/model.bin',
        'hymt': 'translation/hymt/models/Hy-MT2-1.8B-Q4_K_M.gguf',
    }.items() if (BASE / path).is_file()}


def worker(mode):
    # A dedicated hidden console lets Ctrl-C flush the recognizer without
    # signalling the GUI, its launcher, or unrelated console applications.
    if WINDOWS:
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        handler = handler_type(lambda event: True)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
    args = [str(ENGINE), 'transcribe']
    args += ['--live'] if mode == 'live' else [str(BASE / 'samples/jfk.wav'), '--stream']
    args += ['--model', str(MODEL), '--device', 'cpu']
    child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding='utf-8', errors='replace', bufsize=1,
                             start_new_session=not WINDOWS)
    ready = threading.Event()
    cancelled = threading.Event()

    def stop_listener():
        sys.stdin.readline()  # stop command, or parent disappearance/EOF
        if child.poll() is None:
            cancelled.set()
            if ready.is_set():
                if WINDOWS:
                    ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, 0)
                else:
                    child.send_signal(signal.SIGINT)
            else:
                # During model loading the engine's Ctrl-C handler may not yet
                # exist (or can be reset later). Nothing is recording to flush.
                child.terminate()
            try:
                child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.terminate()

    threading.Thread(target=stop_listener, daemon=True).start()
    for line in child.stdout:
        if line.startswith('[live] listening'):
            ready.set()
        print(json.dumps({'line': line.rstrip()}, ensure_ascii=True), flush=True)
    code = child.wait()
    print(json.dumps({'exit': 0 if cancelled.is_set() else code,
                      'cancelled': cancelled.is_set()}), flush=True)


def main(test_driver=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        pass

    class App:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title('Local Caption · 本地字幕')
            scale = self.root.winfo_fpixels('1i') / 96
            self.root.geometry(f'{int(420*scale)}x{int(240*scale)}+80+80')
            self.root.minsize(int(340*scale), int(180*scale))
            self.root.configure(bg='#111827')
            self.root.overrideredirect(WINDOWS)
            self.root.attributes('-topmost', True)
            self.root.attributes('-alpha', 0.90)
            self.opacity = tk.DoubleVar(value=90)
            self.proc = None
            self.stopping = False
            self.events = queue.Queue()
            self.text = ''
            self.session_file = None
            self.dirty = False
            self.closing = False
            self.last_save = 0
            self.errors = []
            self.translation_proc = None
            self.translation_busy = False
            self.translation_started = 0
            self.translation_timeout_sent = False
            self.translation_source = ''
            self.translation_pairs = []
            self.translation_error = ''
            try:
                preferences = json.loads(PREFERENCES.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                preferences = {}
            preferred = preferences.get('translation_backend', 'hymt' if (BASE / 'translation/hymt/models/Hy-MT2-1.8B-Q4_K_M.gguf').is_file() else 'nllb')
            preferred = os.environ.get('ASR_TRANSLATION_BACKEND', preferred)
            available = available_backends()
            self.backend = tk.StringVar(value=preferred if preferred in available else
                                        ('hymt' if 'hymt' in available else 'nllb'))
            self.active_backend = self.backend.get()
            source = os.environ.get('ASR_AUDIO_SOURCE', preferences.get('audio_source', 'live'))
            self.audio_source = tk.StringVar(value=source if source in INPUTS else 'live')
            self.active_source = self.audio_source.get()
            self.audio_metrics = {}
            self.capture_device = ''
            self.metrics_file = None
            self.stopped_at = None
            self.translation_revision = 0
            self.backfill = False
            self.timeline = Timeline()
            self.recording_started = time.monotonic()
            self.text_changed_at = 0
            self.session_id = 0
            self.chinese = tk.BooleanVar(value=True)
            self.translation_status = tk.StringVar(value='中文 · 等待英语短句')
            self.pinned = tk.BooleanVar(value=True)
            self.autosave = tk.BooleanVar(value=True)
            self.status = tk.StringVar(value='就绪 · ' + INPUTS[self.active_source] + ' · 仅英语')
            self.save_status = tk.StringVar(value='文字自动保存到 transcripts 文件夹')
            # Only one compact toolbar; all remaining area belongs to subtitles.
            bar = tk.Frame(self.root, bg='#111827', cursor='fleur')
            bar.pack(side='top', fill='x', padx=3, pady=2)
            bar.bind('<ButtonPress-1>', self.begin_drag)
            bar.bind('<B1-Motion>', self.drag_window)
            grip = tk.Label(bar, text='⋮⋮', fg='#64748b', bg='#111827', cursor='fleur')
            grip.pack(side='left', padx=(0, 3))
            grip.bind('<ButtonPress-1>', self.begin_drag)
            grip.bind('<B1-Motion>', self.drag_window)

            def button(label, action, accent=False, side='left'):
                b = tk.Button(bar, text=label, command=action, relief='flat', bd=0,
                              padx=5, pady=1, font=('Microsoft YaHei UI', 9),
                              bg='#5eead4' if accent else '#111827',
                              fg='#102522' if accent else '#cbd5e1',
                              activebackground='#334155', activeforeground='white')
                b.pack(side=side, padx=1)
                return b
            self.start_button = button('开始', lambda: self.start('live'), True)
            self.stop_button = button('停止', self.stop)
            self.stop_button.configure(state='disabled')
            button('复制', self.copy)
            button('保存', self.save_as)
            self.demo_button = button('示例', lambda: self.start('demo'))
            button('×', self.close, side='right')
            self.settings = tk.Menu(self.root, tearoff=False)
            self.settings.add_checkbutton(label='始终置顶', variable=self.pinned,
                command=lambda: self.root.attributes('-topmost', self.pinned.get()))
            self.settings.add_checkbutton(label='自动保存', variable=self.autosave)
            self.settings.add_checkbutton(label='中文翻译', variable=self.chinese, command=self.toggle_translation)
            for key, label in INPUTS.items():
                self.settings.add_radiobutton(label='输入：' + label, variable=self.audio_source,
                    value=key, command=self.change_audio_source)
            for key, label in BACKENDS.items():
                self.settings.add_radiobutton(label='翻译：' + label + ('' if key in available else '（未安装）'), variable=self.backend,
                    value=key, command=self.change_backend, state='normal' if key in available else 'disabled')
            self.settings.add_command(label='补译待译片段（停止后）', command=self.begin_backfill)
            opacity_menu = tk.Menu(self.settings, tearoff=False)
            for value in (70, 80, 90, 100):
                opacity_menu.add_radiobutton(label=f'{value}%', variable=self.opacity, value=value,
                    command=lambda: self.root.attributes('-alpha', self.opacity.get() / 100))
            self.settings.add_cascade(label='不透明度', menu=opacity_menu)
            self.settings.add_separator()
            self.settings.add_command(label='打开保存目录', command=self.open_folder)
            self.settings.add_command(label='查看运行 / 保存状态', command=lambda: messagebox.showinfo(
                '当前状态', self.status.get() + '\n' + self.translation_status.get() + '\n' + self.save_status.get(), parent=self.root))
            button('···', lambda: self.settings.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery()), side='right')
            self.view = ScrolledText(self.root, wrap='word', font=('Segoe UI', 11),
                                     bg='#1c2637', fg='#f1f5f9', relief='flat',
                                     padx=6, pady=4, height=3)
            self.view.pack(fill='both', expand=True, padx=3, pady=(0, 1))
            self.view.configure(state='disabled')
            self.zh_view = self.view
            self.view.configure(font=('Microsoft YaHei UI', 11))
            for view in (self.view,):
                view.tag_configure('hint', foreground='#94a3b8', font=('Microsoft YaHei UI', 9))
                view.tag_configure('english', foreground='#b8c6da')
                view.tag_configure('stamp', foreground='#5eead4', font=('Consolas', 10))
            self.hints_pending = False
            for variable in (self.status, self.save_status, self.translation_status):
                variable.trace_add('write', self.refresh_hints)
            self.render()
            self.render_chinese()
            resize = tk.Label(self.root, text='◢', bg='#111827', fg='#64748b', cursor='size_nw_se' if WINDOWS else 'bottom_right_corner', font=('Segoe UI', 8))
            resize.place(relx=1, rely=1, anchor='se')
            resize.bind('<ButtonPress-1>', self.begin_resize)
            resize.bind('<B1-Motion>', self.resize_window)
            self.root.protocol('WM_DELETE_WINDOW', self.close)
            self.root.bind('<Control-s>', lambda e: self.save_as())
            self.root.after(100, self.register_borderless_window)
            self.root.after(80, self.poll)

        def register_borderless_window(self):
            if not WINDOWS:
                return
            # Keep the frameless window discoverable in the taskbar and Alt-Tab.
            user32 = ctypes.windll.user32
            user32.GetParent.restype = ctypes.c_void_p
            hwnd = user32.GetParent(self.root.winfo_id())
            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            style = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, (style | 0x00040000) & ~0x00000080)
            user32.SetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
            user32.SetWindowTextW(hwnd, 'Local Caption · 本地字幕')

        def begin_drag(self, event):
            self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

        def drag_window(self, event):
            x, y, left, top = self.drag_origin
            self.root.geometry(f'+{max(0, left + event.x_root - x)}+{max(0, top + event.y_root - y)}')

        def begin_resize(self, event):
            self.resize_origin = (event.x_root, event.y_root, self.root.winfo_width(), self.root.winfo_height())

        def resize_window(self, event):
            x, y, width, height = self.resize_origin
            min_width, min_height = self.root.minsize()
            self.root.geometry(f'{max(min_width, width + event.x_root - x)}x{max(min_height, height + event.y_root - y)}')

        def render(self):
            hint = self.status.get() + '\n' + BACKENDS[self.active_backend] + ' · ' + self.translation_status.get()
            if self.text:
                hint += ' · ' + self.save_status.get().split(' · ')[0]
            rows = []
            count = 0
            for pair in self.translation_pairs:
                rows.append(f"[{timestamp(pair.get('start', self.timeline.at(count)))}]  {pair['en']}\n{pair['zh']}")
                count += len(words(pair['en']))
            tail = self.text[len(source_prefix(self.text, count)):].strip()
            if tail:
                rows.append(f'[{timestamp(self.timeline.at(count))}]  {tail}\n' + ('待翻译…' if self.chinese.get() else '翻译已暂停'))
            if self.translation_error:
                hint += '\n' + self.translation_error
            deferred = sum(bool(pair.get('deferred')) for pair in self.translation_pairs)
            if deferred:
                hint += f' · {deferred} 段待补译'
            if self.active_source == 'system' and self.audio_metrics:
                pending = self.queue_metrics()
                hint += (f"\n音频待识别 {self.audio_metrics.get('backlog_seconds', 0):.1f}s"
                         f" · 待译 {pending['pending_words']} 词 / 最早 {pending['oldest_pending_seconds']:.1f}s"
                         + (' · 采集已停止' if not self.proc or self.audio_metrics.get('stopped') else
                            ' · 无声' if self.audio_metrics.get('level', 0) < 0.001 else ' · 有声音'))
            self.draw_subtitle(self.view, '\n\n'.join(rows), hint)

        def refresh_hints(self, *_):
            if not self.hints_pending:
                self.hints_pending = True
                self.root.after(120, self.render_hints)

        def render_hints(self):
            self.hints_pending = False
            self.render()

        def draw_subtitle(self, view, text, hint):
            # UI-only annotations never become transcript or clipboard data.
            # Keep layout bounded even when the ASR supplies an hour of history.
            if len(text) > 5000:
                text = '…（较早内容保留在保存文件中）\n' + text[-5000:]
            signature = (text, hint)
            if getattr(view, '_last_content', None) == signature:
                return
            was_at_end = view.yview()[1] >= 0.99
            scroll_position = view.yview()[0]
            view.configure(state='normal')
            view.delete('1.0', 'end')
            if text:
                for line in text.splitlines():
                    stamp = re.match(r'^(\[\d{2}:\d{2}(?::\d{2})?\])(.*)', line)
                    if stamp:
                        view.insert('end', stamp.group(1), 'stamp')
                        view.insert('end', stamp.group(2) + '\n', 'english')
                    else:
                        view.insert('end', line + '\n')
            view.insert('end', hint, 'hint')
            view.configure(state='disabled')
            view._last_content = signature
            if was_at_end:
                # Tk 9 Text.see synchronously re-enters layout and was captured
                # hanging in the running app. Fractional scrolling avoids it.
                view.yview_moveto(1.0)
            else:
                view.yview_moveto(scroll_position)

        def preserve(self):
            if not self.dirty:
                return True
            if self.autosave.get():
                return self.save_auto()
            choice = messagebox.askyesnocancel('保存文字', '保存当前文字后再继续？', parent=self.root)
            if choice is None:
                return False
            return self.save_as() if choice else True

        def start(self, mode):
            if self.proc or self.translation_busy or not self.preserve():
                return
            if not MODEL.is_file() or not ENGINE.is_file():
                messagebox.showerror('缺少文件', '未找到本地模型或识别程序，请检查 models 和 runtime 文件夹。', parent=self.root)
                return
            self.text, self.errors = '', []
            if mode == 'live':
                mode = self.audio_source.get()
            self.active_source = mode
            self.audio_metrics = {}
            self.capture_device = ''
            self.stopped_at = None
            self.stopping = False
            self.session_id += 1
            self.timeline = Timeline()
            self.recording_started = time.monotonic()
            self.backfill = False
            self.translation_source = ''
            self.translation_pairs = []
            self.translation_error = ''
            self.translation_status.set('中文 · 等待英语短句')
            self.render_chinese()
            self.dirty = False
            self.session_file = SAVES / (dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f') + '.txt')
            self.metrics_file = self.session_file.with_suffix('.metrics.jsonl') if mode == 'system' else None
            self.save_status.set('新会话 · 有识别文字后自动保存中英文本')
            self.render()
            self.status.set('正在转写示例音频…' if mode == 'demo' else '正在加载 · ' + INPUTS[mode])
            self.start_button.configure(state='disabled')
            self.demo_button.configure(state='disabled')
            self.stop_button.configure(state='normal')
            python = Path(sys.executable).with_name('python.exe') if WINDOWS else Path(sys.executable)
            command = [str(python), str(Path(__file__).resolve()), '--worker', mode]
            options = process_options(console=True)
            if mode == 'system':
                command = [str(PYTHON), str(BASE / 'app/loopback_worker.py')]
                options = process_options()
            try:
                self.proc = subprocess.Popen(command,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    encoding='utf-8', errors='replace', bufsize=1,
                    **options)
            except OSError as exc:
                self.finish(str(exc))
                return
            proc = self.proc

            def reader():
                for line in proc.stdout:
                    try:
                        self.events.put(json.loads(line))
                    except ValueError:
                        self.events.put({'line': line.strip()})
                error = proc.stderr.read().strip()
                code = proc.wait()
                self.events.put({'done': code, 'error': error})
            threading.Thread(target=reader, daemon=True).start()

        def stop(self):
            if self.proc:
                self.stopping = True
                self.status.set('正在停止并整理文字…')
                self.stop_button.configure(state='disabled')
                try:
                    self.proc.stdin.write('stop\n')
                    self.proc.stdin.flush()
                except (OSError, ValueError):
                    pass

        def poll(self):
            deadline = time.monotonic() + 0.012
            handled = 0
            batch = []
            while handled < 64 and time.monotonic() < deadline:
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                handled += 1
                if (batch and 'line' in event and 'line' in batch[-1]
                        and event['line'].startswith('[live partial')
                        and batch[-1]['line'].startswith('[live partial')):
                    batch[-1] = event
                else:
                    batch.append(event)
            for event in batch:
                if 'audio_metrics' in event:
                    self.audio_metrics = event['audio_metrics']
                    self.record_metrics('audio')
                    self.refresh_hints()
                elif 'capture_device' in event:
                    self.capture_device = event['capture_device']
                    if not self.stopping:
                        self.status.set('● 系统声音 · ' + self.capture_device)
                elif 'done' in event:
                    self.finish(event.get('error') or '\n'.join(self.errors[-4:]))
                elif 'translation' in event:
                    self.translation_busy = False
                    result = event['translation']
                    if (result['session'] == self.session_id
                            and result.get('revision', 0) == self.translation_revision):
                        if 'error' in result:
                            self.translation_error = result['error']
                            self.translation_status.set('翻译失败 · 可关闭再勾选中文翻译重试')
                            self.render_chinese()
                        elif self.chinese.get() and 'replace_index' in result:
                            index = result['replace_index']
                            if (index < len(self.translation_pairs)
                                    and self.translation_pairs[index].get('deferred')
                                    and self.translation_pairs[index]['en'] == result['text']):
                                pair = result['pairs'][0]
                                pair['start'] = result['start']
                                pair['backend'] = result['backend']
                                self.translation_pairs[index:index + 1] = [pair]
                                self.dirty = True
                                self.refresh_hints()
                        elif self.chinese.get() and valid_result(self.text, self.translation_pairs,
                                                               result['offset'], result['text']):
                            for pair in result['pairs']:
                                pair['start'] = result.get('start', 0)
                                pair['backend'] = result.get('backend', 'nllb')
                            self.translation_pairs.extend(result['pairs'])
                            self.translation_pairs, count = matching_pairs(self.text, self.translation_pairs)
                            self.translation_source = source_prefix(self.text, count)
                            self.dirty = True
                            self.refresh_hints()
                            self.translation_status.set(f"中文 · 本次 {result['seconds']:.2f} 秒 · 按短句翻译")
                    self.record_metrics('translation')
                elif 'exit' in event:
                    if event['exit']:
                        self.errors.append('识别程序退出码：' + str(event['exit']))
                elif 'line' in event:
                    line = event['line']
                    match = re.match(r'\[live (?:partial|final)[^\]]*\]\s*(.*)', line)
                    if match or (line and not line.startswith('[') and not line.startswith('nemo-speech')):
                        updated = match.group(1) if match else line
                        if updated != self.text:
                            audio_time = re.search(r'@\s*([\d.]+)s', line)
                            elapsed = float(audio_time.group(1)) if audio_time else time.monotonic() - self.recording_started
                            self.timeline.observe(updated, elapsed)
                            self.text = updated
                            self.text_changed_at = time.monotonic()
                            self.dirty = True
                            self.translation_pairs = reconcile_pairs(self.text, self.translation_pairs)
                            self.translation_pairs, count = matching_pairs(self.text, self.translation_pairs)
                            offset = 0
                            for pair in self.translation_pairs:
                                pair.setdefault('start', self.timeline.at(offset))
                                pair.setdefault('backend', self.active_backend)
                                offset += len(words(pair['en']))
                            self.translation_source = source_prefix(self.text, count)
                            self.refresh_hints()
                    elif line.startswith('[live] listening'):
                        if not self.stopping:
                            self.recording_started = time.monotonic()
                            self.status.set('● 正在聆听 · ' + INPUTS.get(self.active_source, '示例') + ' · 点击停止结束')
                    elif 'failed' in line.lower() or 'error' in line.lower() or line.startswith('nemo-speech'):
                        self.errors.append(line)
            self.schedule_translation()
            pending = self.translation_busy or (self.chinese.get() and not self.translation_error
                       and bool(self.text) and self.translation_source != self.text)
            if not self.proc:
                self.start_button.configure(state='disabled' if pending else 'normal')
                self.demo_button.configure(state='disabled' if pending else 'normal')
            if self.closing and not self.proc and not pending:
                if self.preserve():
                    self.shutdown()
                    return
                self.closing = False
            if self.dirty and self.autosave.get() and time.monotonic() - self.last_save > 1:
                self.save_auto()
            self.root.after(80, self.poll)

        def finish(self, error=''):
            self.proc = None
            self.stopped_at = time.monotonic()
            if error and error not in self.errors:
                self.errors.append(error)
            self.record_metrics('stopped')
            self.start_button.configure(state='normal')
            self.demo_button.configure(state='normal')
            self.stop_button.configure(state='disabled')
            if self.autosave.get() and self.dirty:
                self.save_auto()
            self.status.set('已停止 · 可以继续新一轮识别' if not error else '识别未完成 · 请查看错误')
            if error:
                messagebox.showerror('识别错误', error[-1500:], parent=self.root)

        def save_auto(self):
            self.last_save = time.monotonic()
            if not self.text:
                return True
            try:
                SAVES.mkdir(exist_ok=True)
                temporary = self.session_file.with_suffix('.txt.tmp')
                temporary.write_text(self.export_text(), encoding='utf-8')
                temporary.replace(self.session_file)
                self.dirty = False
                self.save_status.set('已自动保存 · ' + self.session_file.name)
                return True
            except OSError as exc:
                self.autosave.set(False)
                self.save_status.set('自动保存失败，请使用另存为')
                messagebox.showerror('保存失败', str(exc), parent=self.root)
                return False

        def save_as(self):
            if not self.text:
                self.status.set('暂无文字 · 请先开始识别或运行示例')
                return False
            SAVES.mkdir(exist_ok=True)
            destination = filedialog.asksaveasfilename(parent=self.root, title='保存转写文字',
                initialdir=str(SAVES), initialfile=self.session_file.name,
                defaultextension='.txt', filetypes=[('文本文件', '*.txt')])
            if not destination:
                return False
            try:
                Path(destination).write_text(self.export_text(), encoding='utf-8')
                self.dirty = False
                self.save_status.set('已保存 · ' + Path(destination).name)
                return True
            except OSError as exc:
                messagebox.showerror('保存失败', str(exc), parent=self.root)
                return False

        def copy(self):
            if self.text:
                self.root.clipboard_clear()
                self.root.clipboard_append(self.export_text())
                self.status.set('已复制文字' + (' · 仍在识别' if self.proc else ''))

        def open_folder(self):
            SAVES.mkdir(exist_ok=True)
            open_folder(SAVES)

        def close(self):
            if self.proc or self.translation_busy or (self.chinese.get() and self.text
                    and not self.translation_error and self.translation_source != self.text):
                self.closing = True
                self.status.set('正在整理并保存中英文本…')
                self.stop()
            elif self.preserve():
                self.shutdown()

        def render_chinese(self):
            self.render()

        def export_text(self):
            body = 'ENGLISH\n' + self.text + '\n\n中文 · ' + BACKENDS[self.active_backend] + '\n'
            body += '\n\n'.join(f"[{timestamp(pair.get('start', 0))}] {pair['en']}\n{pair['zh']}" for pair in self.translation_pairs)
            if self.translation_source != self.text:
                body += '\n[中文翻译未完成或已关闭]'
            body += '\n\n输入：' + INPUTS.get(self.active_source, '示例音频')
            if self.capture_device:
                body += ' · ' + self.capture_device
            if self.errors:
                body += '\n[识别未完成：' + '；'.join(self.errors[-2:]) + ']'
            return body + '\n'

        def queue_metrics(self):
            completed = len(words(self.translation_source))
            pending = max(0, len(self.timeline.tokens) - completed)
            elapsed = (self.stopped_at or time.monotonic()) - self.recording_started
            return {'pending_words': pending,
                    'oldest_pending_seconds': max(0, elapsed - self.timeline.at(completed)) if pending else 0,
                    'deferred_chunks': sum(bool(p.get('deferred')) for p in self.translation_pairs),
                    'translation_busy': self.translation_busy}

        def record_metrics(self, reason):
            if not self.metrics_file:
                return
            try:
                SAVES.mkdir(exist_ok=True)
                row = dict(reason=reason, elapsed=time.monotonic() - self.recording_started,
                           backend=self.active_backend, **self.queue_metrics(), audio=self.audio_metrics)
                with self.metrics_file.open('a', encoding='utf-8') as file:
                    file.write(json.dumps(row) + '\n')
            except OSError:
                self.save_status.set('运行指标保存失败 · 文本仍按原设置保存')

        def save_preferences(self):
            if os.environ.get('ASR_TRANSLATION_BACKEND') or os.environ.get('ASR_AUDIO_SOURCE'):
                return
            try:
                temporary = PREFERENCES.with_suffix('.tmp')
                temporary.write_text(json.dumps({'translation_backend': self.active_backend,
                    'audio_source': self.audio_source.get()}), encoding='utf-8')
                temporary.replace(PREFERENCES)
            except OSError:
                self.status.set('设置已应用，但未能保存默认设置')

        def change_audio_source(self):
            self.save_preferences()
            if self.proc:
                self.status.set('当前采集保持不变 · 下次开始使用' + INPUTS[self.audio_source.get()])
            else:
                self.status.set('下次开始使用' + INPUTS[self.audio_source.get()] + ' · 仅英语')

        def toggle_translation(self):
            self.translation_error = ''
            self.translation_status.set('中文 · 等待翻译' if self.chinese.get() else '中文翻译已暂停')

        def change_backend(self):
            selected = self.backend.get()
            if selected == self.active_backend:
                return
            # Save the old model's result separately before re-translating.
            if self.text:
                SAVES.mkdir(exist_ok=True)
                snapshot = SAVES / (dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f') + '-' + self.active_backend + '.txt')
                try:
                    snapshot.write_text(self.export_text(), encoding='utf-8')
                except OSError as exc:
                    self.backend.set(self.active_backend)
                    self.status.set('切换取消：旧译文保存失败 · ' + str(exc))
                    return
            self.active_backend = selected
            self.translation_revision += 1
            self.translation_pairs = []
            self.translation_source = ''
            self.translation_error = ''
            self.backfill = False
            self.dirty = bool(self.text)
            self.translation_status.set('等待当前请求结束后切换…' if self.translation_busy else '等待新模型翻译…')
            self.save_preferences()
            self.refresh_hints()

        def begin_backfill(self):
            if self.proc:
                self.status.set('请先停止录音，再补译较早片段')
                return
            self.backfill = True
            self.translation_error = ''
            self.chinese.set(True)
            self.translation_status.set('正在补译待译片段…')

        def schedule_translation(self):
            if self.translation_busy:
                if time.monotonic() - self.translation_started > 90 and not self.translation_timeout_sent:
                    self.translation_timeout_sent = True
                    self.translation_status.set('翻译超时 · 正在释放后台进程')
                    if self.translation_proc and self.translation_proc.poll() is None:
                        pid = self.translation_proc.pid
                        threading.Thread(target=kill_tree, args=(pid,), daemon=True).start()
                return
            if not self.chinese.get() or self.translation_error or not self.text:
                return
            self.translation_pairs, count = matching_pairs(self.text, self.translation_pairs)
            if self.proc:
                until = defer_until(self.text, count, self.timeline, time.monotonic() - self.recording_started)
                while count < until:
                    deferred = next_chunk(self.text, count, False, 0)
                    self.translation_pairs.append({'en': deferred, 'zh': '【待补译：已保留英文，实时字幕优先】',
                        'start': self.timeline.at(count), 'deferred': True, 'backend': self.active_backend})
                    count += len(words(deferred))
                    self.dirty = True
                self.refresh_hints()
            self.translation_source = source_prefix(self.text, count)
            target = next_chunk(self.text, count, bool(self.proc), time.monotonic() - self.text_changed_at)
            replace_index = None
            if not target and self.backfill and not self.proc:
                for index, pair in enumerate(self.translation_pairs):
                    if pair.get('deferred'):
                        target, replace_index = pair['en'], index
                        break
                if replace_index is None:
                    self.backfill = False
                    self.translation_status.set('待译片段已全部补齐')
            if not target:
                return
            self.translation_busy = True
            self.translation_started = time.monotonic()
            self.translation_timeout_sent = False
            self.translation_status.set('中文 · 正在翻译…')
            request = {'text': target, 'session': self.session_id, 'offset': count,
                       'backend': self.active_backend, 'revision': self.translation_revision,
                       'start': self.timeline.at(count)}
            if replace_index is not None:
                request.update(replace_index=replace_index, start=self.translation_pairs[replace_index].get('start', 0))

            def run_translation():
                try:
                    if self.translation_proc is None or self.translation_proc.poll() is not None:
                        python = PYTHON
                        self.translation_proc = subprocess.Popen(
                            [str(python), str(BASE / 'translation/desktop_worker.py')],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            encoding='utf-8', bufsize=1, **process_options())
                    self.translation_proc.stdin.write(json.dumps(request) + '\n')
                    self.translation_proc.stdin.flush()
                    line = self.translation_proc.stdout.readline()
                    if not line:
                        raise RuntimeError('翻译进程退出或超时，请检查 translation 模型与环境。')
                    response = json.loads(line)
                except Exception as exc:
                    response = {**request, 'error': str(exc)}
                self.events.put({'translation': response})
            threading.Thread(target=run_translation, daemon=True).start()

        def shutdown(self):
            if self.translation_proc and self.translation_proc.poll() is None:
                # venv Python on Windows may use a redirector process. Closing
                # stdin lets the real worker exit too, instead of killing only
                # the launcher and leaving its child behind.
                try:
                    self.translation_proc.stdin.close()
                    self.translation_proc.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    kill_tree(self.translation_proc.pid)
            self.root.destroy()

    app = App()
    if test_driver:
        app.root.after(0, lambda: test_driver(app))
    app.root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(sys.argv[2])
    else:
        main()
