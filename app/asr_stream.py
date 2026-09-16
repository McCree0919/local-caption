"""Small ctypes binding to the installed NeMo-Speech.cpp v0.1.0 C ABI."""
import ctypes as C
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


class Backend(C.Structure):
    _fields_ = [('size', C.c_size_t), ('gpu', C.c_int32)]


class Model(C.Structure):
    _fields_ = [('size', C.c_size_t), ('path', C.c_char_p), ('name', C.c_char_p)]


class Config(C.Structure):
    _fields_ = [('size', C.c_size_t)] + [(key, C.c_void_p) for key in
        ('backend', 'model', 'streaming', 'decoder', 'vad', 'endpointing', 'postproc', 'diar', 'batching')]


class Options(C.Structure):
    _fields_ = [('size', C.c_size_t), ('request_id', C.c_char_p), ('language_code', C.c_char_p),
        ('interim_results', C.c_bool), ('enable_word_time_offsets', C.c_bool),
        ('enable_automatic_punctuation', C.c_bool), ('verbatim_transcripts', C.c_bool),
        ('profanity_filter', C.c_bool), ('stop_history_eou_ms', C.c_int32),
        ('speech_contexts', C.c_void_p), ('speech_context_count', C.c_size_t),
        ('max_alternatives', C.c_int32), ('enable_speaker_diarization', C.c_bool),
        ('max_speaker_count', C.c_int32)]


class StreamRecognizer:
    def __init__(self):
        self.recognizer = C.c_void_p()
        self.stream = C.c_void_p()
        self.directory = os.add_dll_directory(str(BASE / 'runtime/bin'))
        self.dll = C.CDLL(str(BASE / 'runtime/bin/nemo_speech_asr_c.dll'))
        pointer = C.c_void_p
        def bind(name, args, result=C.c_int):
            fn = getattr(self.dll, 'nemo_speech_asr_' + name)
            fn.argtypes, fn.restype = args, result
            setattr(self, name, fn)
        bind('last_error', [], C.c_char_p)
        bind('create', [C.POINTER(Config), C.POINTER(pointer)])
        bind('destroy', [pointer], None)
        bind('recognition_options_default', [], Options)
        bind('streaming_recognize', [pointer, C.POINTER(Options), C.POINTER(pointer)])
        bind('stream_push_f32', [pointer, C.POINTER(C.c_float), C.c_size_t, C.c_int32])
        bind('stream_next', [pointer, C.POINTER(pointer)])
        bind('stream_finish', [pointer])
        bind('stream_close', [pointer], None)
        bind('result_transcript', [pointer, C.c_size_t], C.c_char_p)
        bind('result_is_final', [pointer], C.c_bool)
        bind('result_audio_processed', [pointer], C.c_float)
        bind('result_destroy', [pointer], None)
        backend = Backend(C.sizeof(Backend), -1)
        model = Model(C.sizeof(Model), str(BASE / 'models/nemotron-speech-streaming-en-0.6b.q8_0.gguf').encode(), None)
        config = Config()
        config.size = C.sizeof(Config)
        config.backend, config.model = C.addressof(backend), C.addressof(model)
        try:
            self.check(self.create(C.byref(config), C.byref(self.recognizer)))
            options = self.recognition_options_default()
            options.interim_results = True
            options.enable_automatic_punctuation = True
            self.check(self.streaming_recognize(self.recognizer, C.byref(options), C.byref(self.stream)))
        except Exception:
            self.close()
            raise

    def check(self, code):
        if code:
            raise RuntimeError((self.last_error() or b'ASR stream failed').decode('utf-8', errors='replace'))

    def push(self, samples, rate):
        self.check(self.stream_push_f32(self.stream, samples.ctypes.data_as(C.POINTER(C.c_float)), len(samples), rate))

    def results(self):
        while True:
            result = C.c_void_p()
            self.check(self.stream_next(self.stream, C.byref(result)))
            if not result:
                return
            try:
                yield dict(text=(self.result_transcript(result, 0) or b'').decode('utf-8', errors='replace'),
                           final=self.result_is_final(result), processed=self.result_audio_processed(result))
            finally:
                self.result_destroy(result)

    def finish(self):
        self.check(self.stream_finish(self.stream))
        return self.results()

    def close(self):
        if self.stream:
            self.stream_close(self.stream)
            self.stream = C.c_void_p()
        if self.recognizer:
            self.destroy(self.recognizer)
            self.recognizer = C.c_void_p()
        if self.directory:
            self.directory.close()
            self.directory = None
