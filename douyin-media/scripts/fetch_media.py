"""Download explicitly requested Douyin videos and extract verified audio."""
import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def run(args, timeout):
    completed = subprocess.run(args, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
    if completed.returncode:
        # Tool output can contain signed URLs or credentials; keep it local.
        raise RuntimeError(Path(args[0]).name + " failed; inspect dependencies, login and source availability")
    return completed.stdout


def probe(path, timeout):
    data = json.loads(run(["ffprobe", "-v", "error", "-show_streams",
                           "-show_format", "-of", "json", str(path)], timeout))
    if path.stat().st_size == 0 or not data.get("streams"):
        raise RuntimeError("Empty or unreadable media")
    duration = float(data.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise RuntimeError("Media duration is missing or invalid")
    return data, duration


def extract_url(value):
    match = re.search(r"https?://[^\s<>\"']+", value)
    if not match:
        raise ValueError("No HTTP(S) URL in input")
    url = match.group().rstrip(".,;!，。；！）)")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.douyin.com", "douyin.com", "v.douyin.com"}:
        raise ValueError("Expected an HTTPS Douyin URL")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Unexpected credentials or port in URL")
    if parsed.hostname != "v.douyin.com" and not re.fullmatch(r"/video/\d+/?", parsed.path):
        raise ValueError("Expected a single video URL")
    return url


def dependencies():
    return {"yt-dlp": importlib.util.find_spec("yt_dlp") is not None,
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None}


def process(source, local, folder, options):
    result = {"source": "local" if local else "douyin", "status": "failed", "files": []}
    try:
        if local:
            media = Path(source).expanduser().resolve(strict=True)
            if not media.is_file():
                raise ValueError("Input must be a file")
        else:
            url = extract_url(source)
            # Only retain public identifiers, never URL query credentials.
            result["source_page"] = url.split("?", 1)[0].split("#", 1)[0]
            command = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                       "--no-overwrites", "--retries", "2", "--fragment-retries", "2",
                       "--socket-timeout", "30", "--merge-output-format", "mp4",
                       "--write-info-json", "-o", str(folder / "%(id)s.%(ext)s"),
                       "--print", "after_move:filepath"]
            if options.cookies_browser:
                command += ["--cookies-from-browser", options.cookies_browser]
            stdout = run(command + ["--", url], options.timeout)
            candidates = [Path(line) for line in stdout.splitlines() if Path(line).is_file()]
            if len(candidates) != 1:
                raise RuntimeError("Backend did not return one media file")
            media = candidates[0].resolve()
            if not media.is_relative_to(folder.resolve()):
                raise RuntimeError("Unexpected backend output path")
            # Retain only useful metadata, then remove raw JSON with signed URLs.
            for info in folder.glob("*.info.json"):
                try:
                    metadata = json.loads(info.read_text(encoding="utf-8"))
                    result.update({key: metadata.get(key) for key in ("id", "title", "uploader")})
                finally:
                    info.unlink()
        data, duration = probe(media, options.timeout)
        has_video = any(s.get("codec_type") == "video" for s in data["streams"])
        if options.mode in ("video", "both"):
            if not has_video:
                raise RuntimeError("Source has no video stream")
            video = media
            if local:
                video = folder / ("video" + media.suffix)
                shutil.copy2(media, video)
            result["files"].append({"kind": "video", "path": str(video),
                                    "bytes": video.stat().st_size, "duration": duration})
        if options.mode in ("audio", "both"):
            if not any(s.get("codec_type") == "audio" for s in data["streams"]):
                raise RuntimeError("Source has no audio stream")
            audio = folder / ("audio." + options.audio_format)
            temporary = folder / ("audio.partial." + options.audio_format)
            codec = ["-c:a", "libmp3lame", "-q:a", "2"] if options.audio_format == "mp3" else ["-c:a", "pcm_s16le"]
            run(["ffmpeg", "-n", "-v", "error", "-i", str(media), "-map", "0:a:0", "-vn"]
                + codec + [str(temporary)], options.timeout)
            audio_data, audio_duration = probe(temporary, options.timeout)
            if not any(s.get("codec_type") == "audio" for s in audio_data["streams"]):
                raise RuntimeError("Output has no audio stream")
            if abs(audio_duration - duration) > max(1.0, duration * 0.01):
                raise RuntimeError("Audio duration differs from source")
            temporary.rename(audio)
            result["files"].append({"kind": "audio", "path": str(audio),
                                    "bytes": audio.stat().st_size, "duration": audio_duration})
        result["status"] = "success"
        if not local and options.mode == "audio":
            media.unlink()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        result["status"] = "partial" if result["files"] else "failed"
        result["error"] = "Operation timed out" if isinstance(error, subprocess.TimeoutExpired) else str(error)
    finally:
        for raw in folder.glob("*.info.json"):
            raw.unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--mode", choices=["video", "audio", "both"], default="both")
    parser.add_argument("--audio-format", choices=["mp3", "wav"], default="mp3")
    parser.add_argument("--output", default="outputs")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--cookies-browser", choices=["chrome", "edge", "firefox"])
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    available = dependencies()
    if options.check:
        print(json.dumps(available))
        return 0 if all(available.values()) else 2
    required = ["ffprobe"] + (["ffmpeg"] if options.mode != "video" else []) + (["yt-dlp"] if options.url else [])
    missing = [name for name in required if not available[name]]
    if missing:
        parser.error("Missing dependencies: " + ", ".join(missing))
    if not (options.url or options.input) or options.timeout <= 0:
        parser.error("Provide --url or --input and a positive --timeout")
    root = Path(options.output).resolve() / ("run-" + uuid.uuid4().hex[:12])
    root.mkdir(parents=True, exist_ok=False)
    results = []
    sources = [(s, False) for s in options.url] + [(s, True) for s in options.input]
    for index, (source, local) in enumerate(sources, 1):
        folder = root / str(index)
        folder.mkdir()
        results.append(process(source, local, folder, options))
    manifest = root / "result.json"
    manifest.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(),
                                   "backend": "yt-dlp", "results": results},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(manifest))
    return 0 if all(r["status"] == "success" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
