import hashlib
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from hg_voice.adapters.espeakng import EspeakNgAdapter, EspeakTTSAdapterError, play_wav
from hg_voice.errors import ErrorCode
from hg_voice.cli import main


def make_wav(path: Path, seconds=0.2):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(22050)
        out.writeframes(b"\0\0" * int(22050 * seconds))


class EspeakAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executable = self.root / "fake-espeak-ng"
        self.executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.executable.chmod(0o700)
        self.adapter = EspeakNgAdapter(str(self.executable), timeout_seconds=1)
        self.text = "Xin thông báo thử nghiệm."

    def tearDown(self):
        self.temp.cleanup()

    def test_synthesize_success_validates_and_hashes_pcm_wav(self):
        target = self.root / "notice.wav"
        def fake_run(args, **kwargs):
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["input"], self.text)
            self.assertNotIn(self.text, args)
            make_wav(Path(args[args.index("-w") + 1]))
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("hg_voice.adapters.espeakng.subprocess.run", side_effect=fake_run):
            result = self.adapter.synthesize_to_wav(self.text, target)
        self.assertTrue(target.is_file())
        self.assertEqual(result.sha256, hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertEqual(result.sample_rate_hz, 22050)
        self.assertEqual(result.channels, 1)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_existing_output_is_not_overwritten_by_default(self):
        target = self.root / "notice.wav"
        target.write_bytes(b"keep")
        with patch("hg_voice.adapters.espeakng.subprocess.run") as run:
            with self.assertRaises(EspeakTTSAdapterError) as error:
                self.adapter.synthesize_to_wav(self.text, target)
        self.assertEqual(error.exception.code, ErrorCode.OUTPUT_WRITE_FAILED)
        run.assert_not_called()
        self.assertEqual(target.read_bytes(), b"keep")

    def test_blank_text_rejected_before_subprocess(self):
        with patch("hg_voice.adapters.espeakng.subprocess.run") as run:
            with self.assertRaises(EspeakTTSAdapterError) as error:
                self.adapter.synthesize_to_wav("  ", self.root / "blank.wav")
        self.assertEqual(error.exception.code, ErrorCode.INVALID_ARGUMENT)
        run.assert_not_called()

    def test_oversized_text_rejected(self):
        with self.assertRaises(EspeakTTSAdapterError) as error:
            self.adapter.synthesize_to_wav("x" * 10001, self.root / "large.wav")
        self.assertEqual(error.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_unknown_voice_rejected(self):
        with self.assertRaises(EspeakTTSAdapterError) as error:
            self.adapter.synthesize_to_wav(self.text, self.root / "bad.wav", voice="remote")
        self.assertEqual(error.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_out_of_range_rate_rejected(self):
        with self.assertRaises(EspeakTTSAdapterError) as error:
            self.adapter.synthesize_to_wav(self.text, self.root / "bad.wav", rate=999)
        self.assertEqual(error.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_timeout_has_stable_code_and_cleans_temp(self):
        with patch("hg_voice.adapters.espeakng.subprocess.run", side_effect=subprocess.TimeoutExpired(["fake"], 1)):
            with self.assertRaises(EspeakTTSAdapterError) as error:
                self.adapter.synthesize_to_wav(self.text, self.root / "timeout.wav")
        self.assertEqual(error.exception.code, ErrorCode.ENGINE_TIMEOUT)
        self.assertFalse((self.root / "timeout.wav").exists())
        self.assertEqual(list(self.root.glob(".hg-voice-*.wav")), [])

    def test_bad_wav_rejected_and_cleaned(self):
        def fake_run(args, **kwargs):
            Path(args[args.index("-w") + 1]).write_bytes(b"not a wav")
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("hg_voice.adapters.espeakng.subprocess.run", side_effect=fake_run):
            with self.assertRaises(EspeakTTSAdapterError) as error:
                self.adapter.synthesize_to_wav(self.text, self.root / "bad.wav")
        self.assertEqual(error.exception.code, ErrorCode.ENGINE_FAILED)
        self.assertFalse((self.root / "bad.wav").exists())

    def test_playback_requires_existing_wav_and_uses_no_shell(self):
        audio = self.root / "notice.wav"
        make_wav(audio)
        player = self.root / "play-audio"
        player.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        player.chmod(0o700)
        with patch("hg_voice.adapters.espeakng.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            result = play_wav(audio, player=str(player))
        self.assertTrue(result["played"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_playback_missing_file_fails_closed(self):
        with self.assertRaises(EspeakTTSAdapterError) as error:
            play_wav(self.root / "missing.wav", player=str(self.root / "missing-player"))
        self.assertEqual(error.exception.code, ErrorCode.OUTPUT_WRITE_FAILED)


    def test_cli_tts_reads_text_file_and_returns_metadata(self):
        target = self.root / "cli.wav"
        text_file = self.root / "notice.txt"
        text_file.write_text(self.text, encoding="utf-8")
        fake = type("FakeResult", (), {"as_dict": lambda self: {"engine": "espeak-ng", "sha256": "a" * 64, "path": str(target)}})()
        with patch("hg_voice.cli.EspeakNgAdapter") as adapter_class:
            adapter_class.return_value.synthesize_to_wav.return_value = fake
            from contextlib import redirect_stdout
            import io
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["tts", "--text-file", str(text_file), "--output", str(target)])
        self.assertEqual(code, 0)
        result = __import__("json").loads(out.getvalue())
        self.assertEqual(result["synthesis"], "PASS")
        self.assertEqual(result["audio"]["engine"], "espeak-ng")
        self.assertFalse(result["network_used"])
        self.assertEqual(adapter_class.return_value.synthesize_to_wav.call_args.args[0], self.text)

    def test_cli_play_calls_local_player_adapter(self):
        audio = self.root / "notice.wav"
        make_wav(audio)
        from contextlib import redirect_stdout
        import io
        out = io.StringIO()
        with patch("hg_voice.cli.play_wav", return_value={"played": True, "player": "play-audio", "exit_code": 0}):
            with redirect_stdout(out):
                code = main(["play", str(audio)])
        self.assertEqual(code, 0)
        self.assertTrue(__import__("json").loads(out.getvalue())["played"])



if __name__ == "__main__":
    unittest.main()
