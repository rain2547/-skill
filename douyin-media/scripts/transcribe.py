"""Offline CPU transcription using local models and FFmpeg-decoded NumPy audio."""
from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATE = 16000
OUTPUT_NAMES = ("transcript.txt", "transcript.srt", "transcript.json")
MODEL_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
_DLL_HANDLES = []


class TranscriptionError(Exception):
    """An error whose fixed message is safe for manifests and console output."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

    def record(self):
        return {"code": self.code, "message": str(self)}


def bootstrap_runtime():
    """Locate dependencies relative to the package, including embedded Python."""
    packages = PACKAGE_ROOT / "runtime" / "site-packages"
    if packages.is_dir() and str(packages) not in sys.path:
        sys.path.insert(0, str(packages))
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for directory in (PACKAGE_ROOT / "runtime" / "python",
                          packages / "ctranslate2", packages / "onnxruntime" / "capi"):
            if directory.is_dir():
                try:
                    _DLL_HANDLES.append(os.add_dll_directory(str(directory)))
                except OSError:
                    pass


bootstrap_runtime()


def resolve_ffmpeg(directory=None):
    executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    if directory:
        return str(Path(directory).expanduser().resolve() / executable)
    bundled = PACKAGE_ROOT / "runtime" / "ffmpeg" / "bin" / executable
    return str(bundled) if bundled.is_file() else (shutil.which("ffmpeg") or executable)


def resolve_model(value="small"):
    if value in ("small", "base"):
        return PACKAGE_ROOT / "runtime" / "models" / value
    return Path(value).expanduser().resolve()


def fmt_ts(seconds):
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def validate_model(directory):
    if any(not (directory / name).is_file() for name in MODEL_FILES):
        raise TranscriptionError("model_missing", "Local model files are missing or incomplete; select a bundled model or a complete local CT2 directory")


def decode_audio(path, ffmpeg, timeout=300, max_duration=7200):
    """Decode without PyAV; never modify the input or retain intermediate PCM."""
    try:
        import numpy as np
    except Exception:
        raise TranscriptionError("dependency_missing", "NumPy could not be imported from the local runtime") from None
    command = [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
               "-vn", "-t", str(max_duration + 1), "-ac", "1", "-ar", str(SAMPLE_RATE),
               "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
    try:
        # A temporary file bounds pipe buffering for long inputs and supports Unicode paths.
        with tempfile.TemporaryFile() as pcm:
            completed = subprocess.run(command, stdout=pcm, stderr=subprocess.PIPE,
                                       timeout=timeout)
            if completed.returncode:
                raise TranscriptionError("decode_failed", "FFmpeg could not decode an audio stream from the selected input")
            size = pcm.tell()
            if not size:
                raise TranscriptionError("no_audio", "The input contains no decodable audio samples")
            if size % 4:
                raise TranscriptionError("invalid_audio", "FFmpeg returned invalid PCM audio")
            if size / (4 * SAMPLE_RATE) > max_duration:
                raise TranscriptionError("duration_limit", "Audio exceeds the configured transcription duration limit")
            pcm.seek(0)
            audio = np.fromfile(pcm, dtype="<f4")
            if not np.isfinite(audio).all():
                raise TranscriptionError("invalid_audio", "Decoded audio contains invalid samples")
            return audio
    except subprocess.TimeoutExpired:
        raise TranscriptionError("decode_timeout", "FFmpeg exceeded the audio decoding time limit") from None
    except OSError:
        raise TranscriptionError("tool_missing", "FFmpeg or its temporary audio output could not be opened") from None


def ensure_output_available(output):
    if any((output / name).exists() for name in OUTPUT_NAMES):
        raise TranscriptionError("output_exists", "Transcript output already exists; choose a new output directory")


def write_outputs(output, data):
    """Create the output set exclusively; never replace an existing user file."""
    ensure_output_available(output)
    rows = data["segments"]
    info = data["info"]
    lines = ["Transcript", f"Status: {data['status']}",
             f"Language: {info.get('language') or 'unknown'}",
             f"Duration: {info['duration']:.3f} seconds", ""]
    lines.extend(f"[{fmt_ts(row['start'])} --> {fmt_ts(row['end'])}] {row['text']}" for row in rows)
    if not rows:
        lines.append("No speech detected.")
    if data.get("error"):
        lines.append("Transcription stopped before completion.")
    srt = "".join(f"{index}\n{fmt_ts(row['start'])} --> {fmt_ts(row['end'])}\n{row['text']}\n\n"
                  for index, row in enumerate(rows, 1))
    contents = ("\n".join(lines) + "\n", srt,
                json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    created = []
    try:
        output.mkdir(parents=True, exist_ok=True)
        for name, content in zip(OUTPUT_NAMES, contents):
            path = output / name
            with path.open("x", encoding="utf-8", newline="\n") as writer:
                created.append(path)
                writer.write(content)
        return [{"kind": path.suffix[1:], "path": str(path), "bytes": path.stat().st_size}
                for path in created]
    except FileExistsError:
        for path in created:
            path.unlink(missing_ok=True)
        raise TranscriptionError("output_exists", "Transcript output already exists; choose a new output directory") from None
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise TranscriptionError("output_error", "The transcript output set could not be written") from None


class Transcriber:
    """Reuse one local model across a batch; arrays bypass faster-whisper's decoder."""

    def __init__(self, options, model=None):
        self.options = options
        self.model_directory = resolve_model(options.model)
        self.model = model

    def load(self):
        if self.model is None:
            validate_model(self.model_directory)
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel(str(self.model_directory), device="cpu", compute_type="int8",
                                          cpu_threads=self.options.cpu_threads,
                                          local_files_only=True)
            except Exception:
                raise TranscriptionError("model_load_failed", "The local CPU int8 model could not be loaded; check the packaged runtime and model files") from None
        return self.model

    def transcribe(self, source, output):
        source = Path(source).expanduser().resolve()
        output = Path(output).expanduser().resolve()
        ensure_output_available(output)
        try:
            if not source.is_file() or source.stat().st_size == 0:
                raise TranscriptionError("invalid_input", "The selected local audio file is missing or empty")
        except OSError:
            raise TranscriptionError("invalid_input", "The selected local audio file cannot be accessed") from None
        audio = decode_audio(source, self.options.ffmpeg, self.options.decode_timeout,
                             self.options.max_duration)
        model = self.load()
        rows = []
        info_data = {"language": None, "language_probability": None,
                     "duration": len(audio) / SAMPLE_RATE}
        error = None
        try:
            segments, info = model.transcribe(
                audio, language=None if self.options.language == "auto" else self.options.language,
                beam_size=self.options.beam_size, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False, initial_prompt=self.options.initial_prompt)
            info_data["language"] = info.language
            probability = float(info.language_probability)
            info_data["language_probability"] = probability if math.isfinite(probability) else None
            for segment in segments:
                text = segment.text.strip()
                if not text:
                    continue
                start, end = float(segment.start), float(segment.end)
                if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
                    raise ValueError("Invalid segment timestamps")
                rows.append({"start": start, "end": end, "text": text})
        except Exception:
            error = TranscriptionError("transcription_failed", "Offline transcription stopped; any completed segments are retained")
            if not rows:
                raise error from None
        status = "partial" if error else ("success" if rows else "no_speech")
        data = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "status": status, "input": {"name": source.name, "path": str(source)},
                "model": {"name": self.model_directory.name, "device": "cpu", "compute_type": "int8"},
                "info": info_data, "segments": rows}
        if error:
            data["error"] = error.record()
        files = write_outputs(output, data)
        return {"status": status, "files": files, "segments": len(rows),
                "characters": sum(len(row["text"]) for row in rows),
                "info": info_data, **({"error": error.record()} if error else {})}


def add_asr_arguments(parser):
    parser.add_argument("--model", default="small", help="Bundled small/base, or a complete local CT2 model directory")
    parser.add_argument("--language", default="zh", help="Language code, or auto")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--cpu-threads", type=int, default=0)
    parser.add_argument("--decode-timeout", type=float, default=300)
    parser.add_argument("--max-duration", type=float, default=7200, help="Maximum decoded audio duration in seconds")
    parser.add_argument("--initial-prompt", default="以下是普通话视频的内容转写，包含标点符号。")
    parser.add_argument("--ffmpeg-dir", help="Override the bundled directory containing ffmpeg and ffprobe")


def validate_options(parser, options):
    if (options.beam_size <= 0 or options.cpu_threads < 0
            or not math.isfinite(options.decode_timeout) or options.decode_timeout <= 0
            or not math.isfinite(options.max_duration) or options.max_duration <= 0):
        parser.error("Beam size, decoding timeout and maximum duration must be positive; CPU threads must be nonnegative")
    options.ffmpeg = resolve_ffmpeg(options.ffmpeg_dir)


def check_environment(options):
    tools = {"offline": True, "device": "cpu", "compute_type": "int8",
             "audio_decoder": "ffmpeg_numpy"}
    try:
        completed = subprocess.run([options.ffmpeg, "-version"], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=10)
        tools["ffmpeg"] = {"available": completed.returncode == 0}
    except (OSError, subprocess.TimeoutExpired):
        tools["ffmpeg"] = {"available": False}
    for distribution, module in (("numpy", "numpy"), ("faster-whisper", "faster_whisper"),
                                  ("ctranslate2", "ctranslate2"), ("av", "av"),
                                  ("onnxruntime", "onnxruntime")):
        try:
            imported = importlib.import_module(module)
            tools[distribution] = {"available": True, "version": version(distribution)}
            if module == "ctranslate2":
                supported = imported.get_supported_compute_types("cpu")
                tools[distribution]["cpu_int8"] = "int8" in supported
        except Exception:
            tools[distribution] = {"available": False}
    directory = resolve_model(options.model)
    tools["model"] = {"name": directory.name,
                      "available": all((directory / name).is_file() for name in MODEL_FILES),
                      "loadable": False}
    if tools["model"]["available"] and tools["faster-whisper"]["available"]:
        try:
            from faster_whisper import WhisperModel
            loaded = WhisperModel(str(directory), device="cpu", compute_type="int8",
                                  cpu_threads=getattr(options, "cpu_threads", 0), local_files_only=True)
            tools["model"]["loadable"] = True
            del loaded
        except Exception:
            tools["model"]["error"] = {"code": "model_load_failed", "message":
                "The local model is incomplete, incompatible or could not be loaded by the packaged CPU runtime"}
    return tools


def environment_ready(tools):
    names = ("ffmpeg", "numpy", "faster-whisper", "ctranslate2", "av", "onnxruntime", "model")
    return (all(tools[name]["available"] for name in names)
            and tools["ctranslate2"].get("cpu_int8", False)
            and tools["model"].get("loadable", False))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", nargs="?", help="Local audio file (also accepted as --input)")
    parser.add_argument("--input", help="Local audio file")
    parser.add_argument("--output", help="New transcript output directory")
    parser.add_argument("--check", action="store_true")
    add_asr_arguments(parser)
    options = parser.parse_args(argv)
    validate_options(parser, options)
    if options.check:
        tools = check_environment(options)
        print(json.dumps(tools, ensure_ascii=False))
        return 0 if environment_ready(tools) else 2
    if bool(options.audio) == bool(options.input):
        parser.error("Provide exactly one local audio file, as --input or the positional argument")
    output = options.output or str(Path("outputs") / ("transcription-" + uuid.uuid4().hex))
    try:
        result = Transcriber(options).transcribe(options.input or options.audio, output)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result["status"] == "partial" else 0
    except TranscriptionError as error:
        print(json.dumps({"status": "failed", "error": error.record()}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print(json.dumps({"status": "failed", "error": {"code": "io_error",
              "message": "Local input or output could not be processed"}}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
