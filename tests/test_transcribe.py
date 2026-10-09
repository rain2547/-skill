"""Offline transcription/output contracts and real FFmpeg workflow integration."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "douyin-media" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import media_workflow as workflow
import transcribe as asr


def options(**overrides):
    values = {"model": "base", "language": "zh", "beam_size": 5, "cpu_threads": 1,
              "decode_timeout": 20, "max_duration": 7200, "initial_prompt": "普通话",
              "ffmpeg": "ffmpeg", "ffmpeg_dir": None, "url": [], "input": [],
              "output": "outputs", "mode": "both", "audio_format": "mp3",
              "backend": "ytdlp", "timeout": 20, "max_bytes": 1024 * 1024,
              "dtk_base_url": "", "proxy": None, "cookies_file": None, "cookies_browser": None}
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeModel:
    def __init__(self, rows=None, fail_after=False):
        self.rows = rows if rows is not None else [(0.0, 0.8, " 中文转写。 ")]
        self.fail_after = fail_after
        self.inputs = []

    def transcribe(self, audio, **kwargs):
        self.inputs.append((audio, kwargs))

        def segments():
            for start, end, text in self.rows:
                yield SimpleNamespace(start=start, end=end, text=text)
            if self.fail_after:
                raise RuntimeError("private cookie session=do-not-log https://media.example/a?signature=secret")

        return segments(), SimpleNamespace(language="zh", language_probability=0.99)


class OutputContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "原始音频 空格.wav"
        self.source.write_bytes(b"unchanged media fixture")
        self.target = self.root / "转写结果"
        self.audio = [0.0] * asr.SAMPLE_RATE

    def transcribe(self, model):
        with patch.object(asr, "decode_audio", return_value=self.audio):
            return asr.Transcriber(options(), model=model).transcribe(self.source, self.target)

    def test_structured_unicode_outputs_and_source_preservation(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        result = self.transcribe(FakeModel())
        self.assertEqual(result["status"], "success")
        data = json.loads((self.target / "transcript.json").read_text(encoding="utf-8"))
        self.assertEqual(data["segments"], [{"start": 0.0, "end": 0.8, "text": "中文转写。"}])
        self.assertEqual(data["model"]["compute_type"], "int8")
        self.assertIn("[00:00:00,000 --> 00:00:00,800] 中文转写。",
                      (self.target / "transcript.txt").read_text(encoding="utf-8"))
        self.assertEqual((self.target / "transcript.srt").read_text(encoding="utf-8"),
                         "1\n00:00:00,000 --> 00:00:00,800\n中文转写。\n\n")
        self.assertEqual(before, hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_existing_file_is_never_overwritten(self):
        self.target.mkdir()
        existing = self.target / "transcript.srt"
        existing.write_bytes(b"existing work")
        with patch.object(asr, "decode_audio") as decoder, self.assertRaises(asr.TranscriptionError) as caught:
            asr.Transcriber(options(), model=FakeModel()).transcribe(self.source, self.target)
        self.assertEqual(caught.exception.code, "output_exists")
        decoder.assert_not_called()
        self.assertEqual(existing.read_bytes(), b"existing work")
        self.assertFalse((self.target / "transcript.txt").exists())

    def test_no_speech_has_explicit_status_and_empty_subtitles(self):
        result = self.transcribe(FakeModel(rows=[]))
        self.assertEqual(result["status"], "no_speech")
        data = json.loads((self.target / "transcript.json").read_text(encoding="utf-8"))
        self.assertEqual(data["segments"], [])
        self.assertEqual((self.target / "transcript.srt").read_bytes(), b"")
        self.assertIn("No speech detected.", (self.target / "transcript.txt").read_text(encoding="utf-8"))

    def test_generator_failure_retains_completed_segments_without_secrets(self):
        result = self.transcribe(FakeModel(fail_after=True))
        self.assertEqual(result["status"], "partial")
        data = (self.target / "transcript.json").read_text(encoding="utf-8")
        self.assertEqual(len(json.loads(data)["segments"]), 1)
        self.assertNotIn("signature=secret", data)
        self.assertNotIn("session=do-not-log", data)

    def test_failure_before_speech_does_not_create_false_transcript(self):
        with self.assertRaises(asr.TranscriptionError) as caught:
            self.transcribe(FakeModel(rows=[], fail_after=True))
        self.assertEqual(caught.exception.code, "transcription_failed")
        self.assertFalse(self.target.exists())
        self.assertNotIn("signature", str(caught.exception))

    def test_invalid_timestamps_are_not_published(self):
        with self.assertRaises(asr.TranscriptionError):
            self.transcribe(FakeModel(rows=[(float("nan"), 1, "invalid")]))
        self.assertFalse(self.target.exists())

    def test_model_names_are_resolved_inside_portable_package(self):
        self.assertEqual(asr.resolve_model("small"), asr.PACKAGE_ROOT / "runtime" / "models" / "small")
        self.assertEqual(asr.resolve_model("base"), asr.PACKAGE_ROOT / "runtime" / "models" / "base")
        with self.assertRaises(asr.TranscriptionError) as caught:
            asr.validate_model(self.root)
        self.assertEqual(caught.exception.code, "model_missing")
        for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
            (self.root / name).write_bytes(b"local model fixture")
        # faster-whisper defaults FeatureExtractor settings when this optional file is absent.
        asr.validate_model(self.root)
        self.assertFalse((self.root / "preprocessor_config.json").exists())

    def test_timestamp_rounding_crosses_minutes_and_hours(self):
        self.assertEqual(asr.fmt_ts(59.9996), "00:01:00,000")
        self.assertEqual(asr.fmt_ts(3600.001), "01:00:00,001")

    def test_file_presence_alone_does_not_make_model_ready(self):
        for name in asr.MODEL_FILES:
            (self.root / name).write_bytes(b"incomplete weight fixture")
        factory = Mock(side_effect=RuntimeError("invalid payload signature=do-not-log"))
        dependency = SimpleNamespace(get_supported_compute_types=lambda device: {"int8"})
        with patch.object(asr.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                patch.object(asr.importlib, "import_module", return_value=dependency), \
                patch.object(asr, "version", return_value="test"), \
                patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
            tools = asr.check_environment(options(model=str(self.root)))
        self.assertTrue(tools["model"]["available"])
        self.assertFalse(tools["model"]["loadable"])
        self.assertFalse(asr.environment_ready(tools))
        self.assertEqual(tools["model"]["error"]["code"], "model_load_failed")
        self.assertNotIn("do-not-log", json.dumps(tools))
        self.assertTrue(factory.call_args.kwargs["local_files_only"])

    def test_summary_is_pending_and_contains_no_claim_of_model_call(self):
        result = self.transcribe(FakeModel())
        root = self.root
        path = workflow.prepare_summary(root, [{"index": 1, "media_status": "success", "transcriptions": [result]}])
        text = path.read_text(encoding="utf-8")
        self.assertIn("Summary status: pending", text)
        self.assertIn("has not called a language model", text)
        self.assertIn("中文转写。", text)
        with self.assertRaises(asr.TranscriptionError):
            workflow.prepare_summary(root, [])


class FFmpegIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = os.environ.get("MEDIA_FFMPEG_DIR")
        cls.ffmpeg = str(Path(directory) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")) if directory else shutil.which("ffmpeg")
        if not cls.ffmpeg or not Path(cls.ffmpeg).is_file():
            raise unittest.SkipTest("Set MEDIA_FFMPEG_DIR or install FFmpeg")
        try:
            import numpy as np
            cls.np = np
        except ImportError:
            raise unittest.SkipTest("NumPy is required for FFmpeg decoding tests")
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / "中文音频 文件.wav"
        cls.video = cls.root / "中文视频 文件.mp4"
        cls.silent_video = cls.root / "无音轨.mp4"
        subprocess.run([cls.ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", str(cls.source)], check=True, timeout=20)
        base = [cls.ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=c=blue:s=160x120:r=10:d=2"]
        subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264",
                               "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.video)], check=True, timeout=20)
        subprocess.run(base + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.silent_video)], check=True, timeout=20)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_unicode_decode_returns_float32_mono_16k_array(self):
        before = self.source.read_bytes()
        samples = asr.decode_audio(self.source, self.ffmpeg, timeout=10)
        self.assertEqual(samples.dtype, self.np.dtype("float32"))
        self.assertEqual(samples.shape, (32000,))
        self.assertGreater(float(abs(samples).max()), 0)
        self.assertEqual(before, self.source.read_bytes())

    def test_long_audio_is_rejected_instead_of_silently_truncated(self):
        with self.assertRaises(asr.TranscriptionError) as caught:
            asr.decode_audio(self.source, self.ffmpeg, timeout=10, max_duration=1)
        self.assertEqual(caught.exception.code, "duration_limit")

    def test_bad_media_has_safe_error(self):
        bad = self.root / "bad-signature=secret.wav"
        bad.write_bytes(b"not media")
        with self.assertRaises(asr.TranscriptionError) as caught:
            asr.decode_audio(bad, self.ffmpeg, timeout=10)
        self.assertEqual(caught.exception.code, "decode_failed")
        self.assertNotIn("secret", str(caught.exception))

    def test_real_fetch_workflow_retains_partial_batch_and_sources(self):
        output = self.root / "工作流输出"
        before = self.video.read_bytes()
        args = options(ffmpeg=self.ffmpeg, ffmpeg_dir=str(Path(self.ffmpeg).parent),
                       input=[str(self.silent_video), str(self.video)], output=str(output))
        model = FakeModel()
        with patch.object(asr.Transcriber, "load", return_value=model):
            manifest, data = workflow.run_workflow(args)
        self.assertTrue(manifest.is_file())
        self.assertEqual(data["status"], "partial")
        self.assertEqual([item["media_status"] for item in data["results"]], ["partial", "success"])
        self.assertEqual(data["results"][0]["media_error"]["code"], "no_audio")
        self.assertEqual(data["results"][1]["transcriptions"][0]["status"], "success")
        self.assertEqual(data["summary"]["status"], "pending")
        self.assertTrue(data["summary"]["ready"])
        self.assertTrue(Path(data["summary"]["input"]).is_file())
        self.assertEqual(before, self.video.read_bytes())
        self.assertEqual(len(model.inputs), 1)
        self.assertIsInstance(model.inputs[0][0], self.np.ndarray)
        self.assertEqual(model.inputs[0][0].dtype, self.np.dtype("float32"))

    def test_workflow_continues_after_asr_failure(self):
        output = self.root / "ASR故障后继续"
        args = options(ffmpeg=self.ffmpeg, ffmpeg_dir=str(Path(self.ffmpeg).parent),
                       input=[str(self.video), str(self.video)], output=str(output))
        real = asr.Transcriber.transcribe
        calls = []

        def fail_first(engine, audio, destination):
            calls.append(audio)
            if len(calls) == 1:
                raise asr.TranscriptionError("model_load_failed", "Local model unavailable")
            return real(engine, audio, destination)

        with patch.object(asr.Transcriber, "load", return_value=FakeModel()), patch.object(asr.Transcriber, "transcribe", new=fail_first):
            manifest, data = workflow.run_workflow(args)
        self.assertEqual(data["status"], "partial")
        self.assertEqual([item["transcriptions"][0]["status"] for item in data["results"]], ["failed", "success"])
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["results"], data["results"])
        media = json.loads(Path(data["media_manifest"]).read_text(encoding="utf-8"))
        self.assertTrue(all(Path(entry["path"]).is_file() for item in media["results"] for entry in item["files"]))

    def test_missing_model_keeps_media_and_explicitly_defers_summary(self):
        args = options(ffmpeg=self.ffmpeg, ffmpeg_dir=str(Path(self.ffmpeg).parent),
                       input=[str(self.video)], output=str(self.root / "缺模型工作流"),
                       model=str(self.root / "missing-local-model"))
        manifest, data = workflow.run_workflow(args)
        self.assertTrue(manifest.is_file())
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["results"][0]["media_status"], "success")
        self.assertEqual(data["results"][0]["transcriptions"][0]["error"]["code"], "model_missing")
        self.assertEqual(data["summary"]["status"], "pending")
        self.assertFalse(data["summary"]["ready"])
        self.assertIn("restore a usable local model", data["summary"]["reason"])
        summary = Path(data["summary"]["input"]).read_text(encoding="utf-8")
        self.assertIn("No transcript is available.", summary)
        media = json.loads(Path(data["media_manifest"]).read_text(encoding="utf-8"))
        self.assertTrue(all(Path(entry["path"]).is_file() for item in media["results"] for entry in item["files"]))


if __name__ == "__main__":
    unittest.main()
