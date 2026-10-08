"""Acquire explicitly selected Douyin videos and deliver verified audio."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dtk_client import DtkClient, MediaError


class Deadline:
    def __init__(self, seconds):
        self.end = time.monotonic() + seconds

    def remaining(self):
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise MediaError("timeout", "Item exceeded its total time limit")
        return remaining


def extract_url(value):
    matches = re.findall(r"https?://[^\s<>\"']+", value)
    if len(matches) != 1:
        raise MediaError("invalid_input", "Provide exactly one URL per --url")
    url = matches[0].rstrip(".,;!，。；！）)")
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in {"www.douyin.com", "douyin.com", "v.douyin.com"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError
        pattern = r"/[A-Za-z0-9_-]+/?" if parsed.hostname == "v.douyin.com" else r"/video/\d+/?"
        if not re.fullmatch(pattern, parsed.path):
            raise ValueError
    except ValueError:
        raise MediaError("invalid_input", "Expected one HTTPS Douyin video or share link") from None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def run(command, deadline, category="tool_error"):
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=deadline.remaining())
    except subprocess.TimeoutExpired:
        raise MediaError("timeout", "Item exceeded its total time limit") from None
    except OSError:
        raise MediaError("tool_missing", "Could not launch a required tool") from None
    if result.returncode:
        detail = result.stderr.lower()
        if category == "download_failed":
            if "could not copy" in detail and "cookie database" in detail:
                raise MediaError("browser_cookie_access", "Browser cookie database is locked or unreadable; close browser background processes or use a normally exported cookie file")
            if "dpapi" in detail or "app-bound" in detail:
                raise MediaError("browser_decryption", "Windows could not decrypt the browser session; use a normally exported cookie file or another supported browser")
            if "could not find" in detail and "cookies database" in detail:
                raise MediaError("browser_profile", "The selected browser profile could not be found in this execution environment")
            if any(word in detail for word in ("cookies", "login", "sign in", "captcha")):
                raise MediaError("session_required", "The platform requires a usable authorized session")
            if any(word in detail for word in ("404", "not available", "private", "deleted")):
                raise MediaError("unavailable", "The requested video is not available")
        raise MediaError(category, "Tool failed; check source availability and tool versions")
    return result.stdout


def probe(path, tool, deadline):
    if not path.is_file() or path.stat().st_size == 0:
        raise MediaError("invalid_media", "Media is empty or missing")
    try:
        data = json.loads(run([tool, "-v", "error", "-show_streams", "-show_format",
                               "-of", "json", str(path)], deadline, "invalid_media"))
        duration = float(data.get("format", {}).get("duration", 0))
        streams = data["streams"]
        if not streams or not math.isfinite(duration) or duration <= 0:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise MediaError("invalid_media", "Media has no valid streams or duration") from None
    return streams, duration


def copy_file(source, target, deadline):
    with source.open("rb") as reader, target.open("xb") as writer:
        while True:
            deadline.remaining()
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            writer.write(chunk)


def record(path, kind, duration, deadline):
    digest = hashlib.sha256()
    with path.open("rb") as reader:
        while True:
            deadline.remaining()
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return {"kind": kind, "path": str(path), "bytes": path.stat().st_size,
            "duration": duration, "sha256": digest.hexdigest()}


def ytdlp_download(url, folder, options, deadline):
    command = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
               "--no-simulate", "--no-overwrites", "--retries", "2", "--fragment-retries", "2",
               "--socket-timeout", "20", "--max-filesize", str(options.max_bytes),
               "--write-info-json", "--ffmpeg-location", str(Path(options.ffmpeg).parent),
               "-o", str(folder / "media.%(ext)s"), "--print", "after_move:filepath"]
    if options.proxy:
        command += ["--proxy", options.proxy]
    if options.cookies_browser:
        command += ["--cookies-from-browser", options.cookies_browser]
    if options.cookies_file:
        cookie_copy = folder / "session.cookies.txt"
        copy_file(Path(options.cookies_file), cookie_copy, deadline)
        command += ["--cookies", str(cookie_copy)]
    stdout = run(command + ["--", url], deadline, "download_failed")
    candidates = []
    for line in stdout.splitlines():
        try:
            path = Path(line).resolve()
            if path.is_file() and path.is_relative_to(folder.resolve()):
                candidates.append(path)
        except OSError:
            continue
    if len(candidates) != 1:
        raise MediaError("backend_response", "Backend did not return exactly one media file")
    metadata = {}
    for info in folder.glob("*.info.json"):
        try:
            raw = json.loads(info.read_text(encoding="utf-8"))
            metadata = {key: raw.get(key) for key in ("id", "title", "uploader")}
        except (ValueError, OSError):
            pass
    return candidates[0], metadata


def process(source, local, folder, options):
    deadline = Deadline(options.timeout)
    result = {"source": "local" if local else "douyin", "backend": "local" if local else options.backend,
              "status": "failed", "files": []}
    try:
        if local:
            try:
                media = Path(source).expanduser().resolve()
            except OSError:
                raise MediaError("invalid_input", "Local input file does not exist") from None
            if not media.is_file():
                raise MediaError("invalid_input", "Local input must be a file")
        else:
            url = extract_url(source)
            result["source_page"] = url
            if options.backend == "dtk":
                client = DtkClient(options.dtk_base_url, os.environ.get("DTK_API_KEY", ""), deadline)
                media, metadata = client.download(url, folder, options.max_bytes)
            else:
                media, metadata = ytdlp_download(url, folder, options, deadline)
            result.update(metadata)
        if media.stat().st_size > options.max_bytes:
            raise MediaError("size_limit", "Media exceeds configured byte limit")
        streams, duration = probe(media, options.ffprobe, deadline)
        if not any(s.get("codec_type") == "video" for s in streams):
            raise MediaError("no_video", "Source is not a video")
        if options.mode in ("video", "both"):
            video = media
            if local:
                video = folder / ("video" + media.suffix)
                temporary = folder / ("video.partial" + media.suffix)
                copy_file(media, temporary, deadline)
                video_record = record(temporary, "video", duration, deadline)
                temporary.rename(video)
                video_record["path"] = str(video)
            else:
                video_record = record(video, "video", duration, deadline)
            result["files"].append(video_record)
        if options.mode in ("audio", "both"):
            tracks = [s for s in streams if s.get("codec_type") == "audio"]
            if not tracks:
                raise MediaError("no_audio", "Source has no audio stream")
            audio = folder / ("audio." + options.audio_format)
            temporary = folder / ("audio.partial." + options.audio_format)
            codec = (["-c:a", "libmp3lame", "-q:a", "2"] if options.audio_format == "mp3"
                     else ["-c:a", "pcm_s16le"])
            run([options.ffmpeg, "-n", "-v", "error", "-i", str(media), "-map", "0:a:0", "-vn"]
                + codec + [str(temporary)], deadline, "conversion_failed")
            audio_streams, audio_duration = probe(temporary, options.ffprobe, deadline)
            expected = float(tracks[0].get("duration") or duration)
            if (not any(s.get("codec_type") == "audio" for s in audio_streams)
                    or abs(audio_duration - expected) > max(1.0, expected * 0.01)):
                raise MediaError("invalid_audio", "Extracted audio duration is inconsistent")
            audio_record = record(temporary, "audio", audio_duration, deadline)
            temporary.rename(audio)
            audio_record["path"] = str(audio)
            result["files"].append(audio_record)
        result["status"] = "success"
    except MediaError as error:
        result["status"] = "partial" if result["files"] else "failed"
        result["error"] = {"code": error.code, "message": str(error)}
    except (OSError, ValueError, KeyError, TypeError):
        result["status"] = "partial" if result["files"] else "failed"
        result["error"] = {"code": "io_error", "message": "Input, output or backend data could not be processed"}
    finally:
        delivered = {item["path"] for item in result["files"]}
        # Only this new item directory is cleaned; source files are never removed.
        for path in folder.iterdir():
            if path.is_file() and str(path) not in delivered:
                path.unlink(missing_ok=True)
    return result


def check_environment(options):
    from importlib.metadata import version
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        try:
            value = run([getattr(options, name), "-version"], Deadline(10)).splitlines()[0]
            tools[name] = {"available": True, "version": value}
        except (MediaError, IndexError):
            tools[name] = {"available": False}
    present = importlib.util.find_spec("yt_dlp") is not None
    tools["yt-dlp"] = {"available": present, "version": version("yt-dlp") if present else None}
    tools["dtk"] = {"configured": bool(options.dtk_base_url), "key_present": bool(os.environ.get("DTK_API_KEY"))}
    return tools


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--mode", choices=["video", "audio", "both"], default="both")
    parser.add_argument("--audio-format", choices=["mp3", "wav"], default="mp3")
    parser.add_argument("--output", default="outputs")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024 * 1024)
    parser.add_argument("--backend", choices=["ytdlp", "dtk"], default="ytdlp")
    parser.add_argument("--dtk-base-url", default=os.environ.get("DTK_BASE_URL", ""))
    parser.add_argument("--proxy", help="yt-dlp proxy; not applied to DTK")
    cookies = parser.add_mutually_exclusive_group()
    cookies.add_argument("--cookies-browser", choices=["chrome", "edge", "firefox"])
    cookies.add_argument("--cookies-file", help="Authorized Netscape-format cookie file")
    parser.add_argument("--ffmpeg-dir", help="Directory containing ffmpeg and ffprobe")
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args(argv)
    for name in ("ffmpeg", "ffprobe"):
        executable = name + (".exe" if os.name == "nt" else "")
        value = str(Path(options.ffmpeg_dir).resolve() / executable) if options.ffmpeg_dir else shutil.which(name)
        setattr(options, name, value or name)
    if options.check:
        tools = check_environment(options)
        print(json.dumps(tools, ensure_ascii=False))
        required = ["ffmpeg", "ffprobe"] + (["yt-dlp"] if options.backend == "ytdlp" else [])
        ok = all(tools[name]["available"] for name in required)
        return 0 if ok and (options.backend != "dtk" or tools["dtk"]["configured"]) else 2
    if not (options.url or options.input):
        parser.error("Provide --url or --input")
    if not math.isfinite(options.timeout) or options.timeout <= 0 or options.max_bytes <= 0:
        parser.error("--timeout and --max-bytes must be positive and finite")
    needed = ["ffprobe"] + (["ffmpeg"] if options.mode != "video" or options.url else [])
    if any(not shutil.which(getattr(options, name)) for name in needed):
        parser.error("FFmpeg tools are missing; install them or pass --ffmpeg-dir")
    if options.url and options.backend == "ytdlp" and importlib.util.find_spec("yt_dlp") is None:
        parser.error("Install the Python yt-dlp dependency")
    if options.url and options.backend == "dtk" and not options.dtk_base_url:
        parser.error("DTK requires --dtk-base-url or DTK_BASE_URL")
    if options.backend == "dtk" and (options.cookies_browser or options.cookies_file or options.proxy):
        parser.error("Configure sessions and network on DTK; client Cookie/proxy options are for yt-dlp")
    root = Path(options.output).expanduser().resolve() / ("run-" + uuid.uuid4().hex)
    results = []
    try:
        root.mkdir(parents=True, exist_ok=False)
        sources = [(source, False) for source in options.url] + [(source, True) for source in options.input]
        for index, (source, local) in enumerate(sources, 1):
            folder = root / str(index)
            folder.mkdir()
            results.append(process(source, local, folder, options))
            manifest = root / "result.json"
            temporary = root / "result.partial.json"
            temporary.write_text(json.dumps({"schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(), "results": results},
                ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(manifest)
        print(str(manifest))
    except OSError:
        print("Cannot write the output directory or manifest", file=sys.stderr)
        return 2
    return 0 if all(item["status"] == "success" for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
