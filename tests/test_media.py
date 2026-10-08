"""Real FFmpeg integration and HTTP contract tests; no platform credentials."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "douyin-media" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import fetch_media as media
from dtk_client import DtkClient, MediaError


class UrlTests(unittest.TestCase):
    def test_share_text_and_tracking(self):
        self.assertEqual(media.extract_url("分享 https://v.douyin.com/AbCd/?token=secret。"),
                         "https://v.douyin.com/AbCd/")

    def test_reject_wrong_resource_and_host(self):
        for url in ("https://localhost/video/123", "https://www.douyin.com/user/123",
                    "https://www.douyin.com@evil.example/video/123", "https://www.douyin.com:789/video/123",
                    "https://v.douyin.com/", "https://www.douyin.com/video/1 https://v.douyin.com/abc/"):
            with self.subTest(url=url), self.assertRaises(MediaError):
                media.extract_url(url)

    def test_deadline(self):
        with self.assertRaises(MediaError) as caught:
            media.Deadline(-1).remaining()
        self.assertEqual(caught.exception.code, "timeout")

    def test_remote_plaintext_key_refused(self):
        with self.assertRaises(MediaError):
            DtkClient("http://example.com", "secret", media.Deadline(1))


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = os.environ.get("MEDIA_FFMPEG_DIR")
        if not cls.tools:
            cls.tools = str(Path(media.shutil.which("ffmpeg") or "missing").parent)
        suffix = ".exe" if os.name == "nt" else ""
        cls.ffmpeg = str(Path(cls.tools) / ("ffmpeg" + suffix))
        cls.ffprobe = str(Path(cls.tools) / ("ffprobe" + suffix))
        if not Path(cls.ffmpeg).is_file() or not Path(cls.ffprobe).is_file():
            raise unittest.SkipTest("Install FFmpeg or set MEDIA_FFMPEG_DIR")
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        cls.fixture = cls.root / "source 视频.mp4"
        cls.silent = cls.root / "silent.mp4"
        cls.short_audio = cls.root / "short-audio.mp4"
        base = [cls.ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=c=blue:s=160x120:r=10:d=2"]
        subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                               "-shortest", str(cls.fixture)], check=True, timeout=20)
        subprocess.run(base + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.silent)],
                       check=True, timeout=20)
        subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                               str(cls.short_audio)], check=True, timeout=20)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def invoke(self, *args, env=None, output=None):
        folder = output or self.root / uuid.uuid4().hex
        command = [sys.executable, str(SCRIPTS / "fetch_media.py"), "--ffmpeg-dir", self.tools,
                   "--output", str(folder)] + list(args)
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", env=env, timeout=25)
        manifests = list(folder.glob("run-*/result.json"))
        data = json.loads(manifests[0].read_text(encoding="utf-8")) if manifests else None
        return completed, data, folder

    def verify(self, entry, kind):
        path = Path(entry["path"])
        self.assertTrue(path.is_file())
        self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        streams, duration = media.probe(path, self.ffprobe, media.Deadline(5))
        self.assertTrue(any(stream["codec_type"] == kind for stream in streams))
        self.assertGreater(duration, 0)

    def test_mp3_both_and_preserve_source(self):
        before = self.fixture.read_bytes()
        completed, data, _ = self.invoke("--input", str(self.fixture))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(data["results"][0]["status"], "success")
        files = data["results"][0]["files"]
        self.assertEqual([item["kind"] for item in files], ["video", "audio"])
        for entry in files:
            self.verify(entry, entry["kind"])
        self.assertEqual(before, self.fixture.read_bytes())

    def test_wav_audio_only(self):
        completed, data, folder = self.invoke("--input", str(self.fixture), "--mode", "audio",
                                               "--audio-format", "wav")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(data["results"][0]["files"]), 1)
        self.verify(data["results"][0]["files"][0], "audio")
        self.assertFalse(list(folder.rglob("*.mp4")))

    def test_video_only_silent(self):
        completed, data, _ = self.invoke("--input", str(self.silent), "--mode", "video")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.verify(data["results"][0]["files"][0], "video")

    def test_batch_continues_after_no_audio(self):
        completed, data, _ = self.invoke("--input", str(self.silent), "--input", str(self.fixture))
        self.assertEqual(completed.returncode, 1)
        self.assertEqual([item["status"] for item in data["results"]], ["partial", "success"])
        self.assertEqual(data["results"][0]["error"]["code"], "no_audio")
        self.verify(data["results"][0]["files"][0], "video")

    def test_missing_input(self):
        completed, data, _ = self.invoke("--input", str(self.root / "absent.mp4"))
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "invalid_input")

    def test_corrupt_media(self):
        bad = self.root / "bad.mp4"
        bad.write_bytes(b"not a media file")
        completed, data, folder = self.invoke("--input", str(bad))
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "invalid_media")
        self.assertEqual(len(list(folder.rglob("*partial*"))), 0)

    def test_size_limit(self):
        completed, data, _ = self.invoke("--input", str(self.fixture), "--max-bytes", "10")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "size_limit")

    def test_shorter_audio_track(self):
        completed, data, _ = self.invoke("--input", str(self.short_audio))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.verify(data["results"][0]["files"][1], "audio")

    def test_repeat_runs_are_separate(self):
        output = self.root / uuid.uuid4().hex
        args = ["--input", str(self.fixture)]
        first, data, _ = self.invoke(*args, output=output)
        before = Path(data["results"][0]["files"][0]["path"]).read_bytes()
        second, _, _ = self.invoke(*args, output=output)
        self.assertEqual((first.returncode, second.returncode), (0, 0))
        self.assertEqual(len(list(output.glob("run-*"))), 2)
        self.assertEqual(before, Path(data["results"][0]["files"][0]["path"]).read_bytes())

    def test_invalid_timeout(self):
        completed, data, _ = self.invoke("--input", str(self.fixture), "--timeout", "nan")
        self.assertEqual(completed.returncode, 2)
        self.assertIsNone(data)

    def test_expired_item(self):
        completed, data, _ = self.invoke("--input", str(self.fixture), "--timeout", "0.000001")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "timeout")

    def service(self, case="ok"):
        payload = self.fixture.read_bytes()
        task_id, download_id = str(uuid.uuid4()), str(uuid.uuid4())
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, body, status=200):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def response(self, data, status=200):
                self.send({"success": True, "data": data, "error": None, "meta": {}}, status)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.path, body, self.headers.get("X-API-Key")))
                if case == "auth":
                    return self.send({"success": False, "data": None, "error": {}}, 401)
                if case == "malformed":
                    return self.send({"success": False, "data": None, "error": "unavailable"})
                if self.path == "/api/v1/parse":
                    return self.response({"task_id": task_id, "state": "queued"}, 202)
                if self.path == "/api/v1/downloads":
                    return self.response({"download_id": download_id, "state": "queued"}, 202)
                self.send({}, 404)

            def do_GET(self):
                calls.append((self.path, None, self.headers.get("X-API-Key")))
                if self.path == "/api/v1/tasks/" + task_id:
                    if case == "timeout":
                        return self.response({"task_id": task_id, "state": "running"})
                    return self.response({"task_id": task_id, "state": "done", "data":
                        {"platform": "douyin", "content_id": "6961737553342991651", "description": "fixture"}})
                if self.path == "/api/v1/downloads/" + download_id:
                    checksum = "0" * 64 if case == "checksum" else hashlib.sha256(payload).hexdigest()
                    return self.response({"state": "done", "files": [{"kind": "video", "state": "done",
                        "name": "video.mp4", "sha256": checksum}]})
                if self.path.endswith("/files/video.mp4"):
                    if case == "incomplete":
                        self.send_response(200)
                        self.send_header("Transfer-Encoding", "chunked")
                        self.end_headers()
                        self.wfile.write(b"10\r\nabc")
                        self.wfile.flush()
                        self.close_connection = True
                        return
                    if case == "redirect":
                        self.send_response(302)
                        self.send_header("Location", "https://example.com/")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send({}, 404)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:" + str(server.server_port), calls

    def invoke_service(self, case="ok", *extra):
        origin, calls = self.service(case)
        env = dict(os.environ, DTK_API_KEY="test-secret-do-not-log")
        completed, data, folder = self.invoke("--backend", "dtk", "--dtk-base-url", origin,
            "--url", "https://v.douyin.com/Example/?token=private", *extra, env=env)
        self.assertNotIn("test-secret-do-not-log", json.dumps(data))
        self.assertNotIn("token=private", json.dumps(data))
        return completed, data, folder, calls

    def test_dtk_http_download_and_audio(self):
        completed, data, _, calls = self.invoke_service()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for item in data["results"][0]["files"]:
            self.verify(item, item["kind"])
        self.assertTrue(all(call[2] == "test-secret-do-not-log" for call in calls))
        self.assertTrue(any(call[0] == "/api/v1/downloads" and call[1]["skip_existing"] for call in calls))

    def test_dtk_auth_failure(self):
        completed, data, _, _ = self.invoke_service("auth")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "service_auth")

    def test_dtk_checksum_failure_cleanup(self):
        completed, data, folder, _ = self.invoke_service("checksum")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "checksum_mismatch")
        self.assertFalse(list(folder.rglob("*.mp4")))

    def test_dtk_poll_timeout(self):
        completed, data, _, _ = self.invoke_service("timeout", "--timeout", "0.1")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "timeout")

    def test_dtk_redirect_refused(self):
        completed, data, _, _ = self.invoke_service("redirect")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "service_redirect")

    def test_dtk_stream_size_limit(self):
        completed, data, _, _ = self.invoke_service("ok", "--max-bytes", "10")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "size_limit")

    def test_dtk_malformed_error_is_recorded(self):
        completed, data, _, _ = self.invoke_service("malformed")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["results"][0]["error"]["code"], "backend_response")

    def test_dtk_incomplete_transfer_keeps_batch_running(self):
        completed, data, _, _ = self.invoke_service("incomplete", "--input", str(self.fixture))
        self.assertEqual(completed.returncode, 1)
        self.assertEqual([item["status"] for item in data["results"]], ["failed", "success"])
        self.assertEqual(data["results"][0]["error"]["code"], "incomplete_download")


if __name__ == "__main__":
    unittest.main()
