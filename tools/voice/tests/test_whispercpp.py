import hashlib
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from hg_voice.errors import ErrorCode
from hg_voice.adapters.whispercpp import WhisperAdapterError, WhisperConfig, WhisperCppAdapter


def wav_file(path: Path, seconds=0.1):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b'\0\0' * int(16000 * seconds))

class WhisperAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executable = self.root / 'fake-engine.py'
        self.executable.write_text('#!/usr/bin/env python3\nimport sys\nprint("Xin chao")\n', encoding='utf-8')
        self.executable.chmod(0o700)
        self.model = self.root / 'model.bin'; self.model.write_bytes(b'fake model')
        self.audio = self.root / 'audio.wav'; wav_file(self.audio)
        self.config = WhisperConfig(self.executable, self.model, self.sha(self.executable), self.sha(self.model), timeout_seconds=1)
        self.adapter = WhisperCppAdapter(self.config)

    def tearDown(self): self.tmp.cleanup()
    @staticmethod
    def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

    def test_fake_adapter_success(self):
        self.assertEqual(self.adapter.transcribe_wav(self.audio), 'Xin chao')

    def test_invalid_audio_format_rejected_before_subprocess(self):
        bad = self.root / 'bad.wav'; bad.write_bytes(b'not a wav file' * 20)
        with patch('hg_voice.adapters.whispercpp.subprocess.run') as run:
            with self.assertRaises(WhisperAdapterError) as e: self.adapter.transcribe_wav(bad)
            self.assertEqual(e.exception.code, ErrorCode.INVALID_AUDIO)
            run.assert_not_called()

    def test_missing_model(self):
        cfg = WhisperConfig(self.executable, self.root / 'missing.bin', self.sha(self.executable), '0' * 64)
        with self.assertRaises(WhisperAdapterError) as e: WhisperCppAdapter(cfg).transcribe_wav(self.audio)
        self.assertEqual(e.exception.code, ErrorCode.MODEL_NOT_INSTALLED)

    def test_digest_mismatch(self):
        cfg = WhisperConfig(self.executable, self.model, '0' * 64, self.sha(self.model))
        with self.assertRaises(WhisperAdapterError) as e: WhisperCppAdapter(cfg).transcribe_wav(self.audio)
        self.assertEqual(e.exception.code, ErrorCode.ARTIFACT_DIGEST_MISMATCH)

    def test_timeout_has_stable_code(self):
        with patch('hg_voice.adapters.whispercpp.subprocess.run', side_effect=__import__('subprocess').TimeoutExpired(['fake'], 1)):
            with self.assertRaises(WhisperAdapterError) as e: self.adapter.transcribe_wav(self.audio)
        self.assertEqual(e.exception.code, ErrorCode.ENGINE_TIMEOUT)

    def test_no_shell_or_network_fallback(self):
        with patch('hg_voice.adapters.whispercpp.subprocess.run', return_value=__import__('subprocess').CompletedProcess([], 0, b'Xin chao\n', b'')) as run:
            self.adapter.transcribe_wav(self.audio)
            args, kwargs = run.call_args
            self.assertFalse(kwargs['shell'])
            self.assertIn('--no-gpu', args[0])
            self.assertNotIn('https://', ' '.join(args[0]))
            self.assertNotIn('curl', args[0])

    def test_duration_limit(self):
        long_audio = self.root / 'long.wav'; wav_file(long_audio, seconds=31)
        with patch('hg_voice.adapters.whispercpp.subprocess.run') as run:
            with self.assertRaises(WhisperAdapterError) as e: self.adapter.transcribe_wav(long_audio)
            self.assertEqual(e.exception.code, ErrorCode.INVALID_AUDIO)
            run.assert_not_called()

if __name__ == '__main__': unittest.main()
