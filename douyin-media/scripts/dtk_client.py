"""Adapter for Evil0ctal Douyin_TikTok_Download_API v5."""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class MediaError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MediaError("service_redirect", "DTK must serve files directly; redirects are refused")


class DtkClient:
    def __init__(self, base_url, api_key, deadline):
        parsed = urlsplit(base_url)
        try:
            valid = (parsed.scheme in ("http", "https") and parsed.hostname
                     and not parsed.username and not parsed.password
                     and parsed.path in ("", "/") and not parsed.query and not parsed.fragment)
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise MediaError("invalid_input", "DTK base URL must be an HTTP(S) origin")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise MediaError("invalid_input", "Remote DTK requires HTTPS to protect its API key")
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key} if api_key else {}
        self.deadline = deadline
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def open(self, path, body=None):
        headers = dict(self.headers)
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            return self.opener.open(request, timeout=min(20, self.deadline.remaining()))
        except HTTPError as error:
            codes = {401: "service_auth", 403: "service_permission", 404: "unavailable",
                     429: "rate_limited", 501: "service_not_configured"}
            raise MediaError(codes.get(error.code, "service_error"),
                             "DTK request failed with HTTP " + str(error.code)) from None
        except (URLError, TimeoutError, OSError, HTTPException):
            self.deadline.remaining()
            raise MediaError("network_error", "Cannot reach the configured DTK service") from None

    def read(self, response, size):
        self.deadline.remaining()
        try:
            chunk = response.read1(size)
        except (HTTPException, TimeoutError, OSError):
            self.deadline.remaining()
            raise MediaError("incomplete_download", "DTK response ended before the transfer completed") from None
        self.deadline.remaining()
        return chunk

    def request(self, path, body=None):
        limit = 2 * 1024 * 1024
        chunks = []
        total = 0
        with self.open(path, body) as response:
            while total <= limit:
                chunk = self.read(response, min(65536, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        raw = b"".join(chunks)
        try:
            envelope = json.loads(raw)
            if len(raw) > limit or not isinstance(envelope, dict):
                raise ValueError
            if envelope.get("success") is not True:
                error = envelope.get("error")
                if not isinstance(error, dict):
                    raise ValueError
                code = error.get("code", "service_error")
                safe = code if isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,64}", code) else "service_error"
                raise MediaError(safe, "DTK refused the request")
            data = envelope["data"]
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, TypeError, KeyError):
            raise MediaError("backend_response", "Unexpected DTK v5 response") from None

    @staticmethod
    def identifier(value):
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise MediaError("backend_response", "DTK returned an invalid task or download identifier") from None

    def wait(self):
        time.sleep(min(0.5, self.deadline.remaining()))

    def download(self, url, folder, max_bytes):
        parsed = self.request("/api/v1/parse", {"url": url})
        if "task_id" in parsed:
            task_id = self.identifier(parsed["task_id"])
            while True:
                task = self.request("/api/v1/tasks/" + task_id)
                state = task.get("state")
                if state == "done":
                    parsed = task.get("data", {})
                    break
                if state in ("failed", "cancelled"):
                    raise MediaError("parse_failed", "DTK could not parse this video")
                if state not in ("queued", "running"):
                    raise MediaError("backend_response", "Unexpected DTK task state")
                self.wait()
        if (not isinstance(parsed, dict) or parsed.get("platform") != "douyin"
                or not re.fullmatch(r"\d{1,24}", str(parsed.get("content_id", "")))):
            raise MediaError("unsupported_content", "DTK did not return a Douyin video identifier")
        content_id = str(parsed["content_id"])
        started = self.request("/api/v1/downloads",
                               {"platform": "douyin", "content_id": content_id, "skip_existing": True})
        download_id = self.identifier(started.get("download_id"))
        while True:
            download = self.request("/api/v1/downloads/" + download_id)
            state = download.get("state")
            if state in ("done", "partial"):
                break
            if state in ("failed", "cancelled"):
                raise MediaError("download_failed", "DTK could not store this video's media")
            if state not in ("queued", "running"):
                raise MediaError("backend_response", "Unexpected DTK download state")
            self.wait()
        videos = [item for item in download.get("files", []) if isinstance(item, dict)
                  and item.get("kind") == "video" and item.get("state") == "done"]
        if len(videos) != 1:
            raise MediaError("unsupported_content", "DTK has no single completed video file")
        entry = videos[0]
        name = entry.get("name", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
            raise MediaError("backend_response", "Invalid DTK media filename")
        media = folder / "media.mp4"
        temporary = folder / "media.partial.mp4"
        digest = hashlib.sha256()
        total = 0
        with self.open("/api/v1/downloads/" + download_id + "/files/" + quote(name, safe="")) as response:
            with temporary.open("xb") as output:
                while True:
                    chunk = self.read(response, 65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise MediaError("size_limit", "Media exceeds configured byte limit")
                    output.write(chunk)
                    digest.update(chunk)
            expected = response.headers.get("Content-Length")
        self.deadline.remaining()
        if not total or (expected is not None and total != int(expected)):
            raise MediaError("incomplete_download", "DTK media transfer was incomplete")
        if entry.get("sha256") and digest.hexdigest() != entry["sha256"]:
            raise MediaError("checksum_mismatch", "DTK media checksum did not match")
        temporary.rename(media)
        return media, {"id": content_id, "title": parsed.get("description"), "download_id": download_id}
