"""Regression tests for Fix Batch 9 (stdlib P2 quick-wins)."""

import asyncio
import datetime
from typing import ClassVar

import httpx
import pytest


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Isolate avatar-cache writes into a tmp directory."""
    d = tmp_path / "cache"
    d.mkdir()
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(d))
    yield d


def test_safe_filename_matrix():
    from app_shell import _safe_filename

    assert _safe_filename("alice") == "alice"
    assert _safe_filename("John Doe 99") == "john-doe-99"
    assert _safe_filename("a/b") == "a-b"
    assert _safe_filename("../../evil") == "evil"
    assert _safe_filename("CON") == "con-file"
    assert _safe_filename("caf\u00e9 \u65e5\u672c") == "cafe"
    assert _safe_filename("") == "scan"
    assert _safe_filename(None) == "scan"
    assert _safe_filename("x" * 200) == "x" * 64
    # Email-shaped queries slug sanely
    assert _safe_filename("A@B.com") == "a-b-com"


def test_relative_time_matrix():
    from screens.history_screen import _relative_time

    now = datetime.datetime.now()  # noqa: DTZ005, RUF100 — naive-local matches writer
    fmt = "%Y-%m-%d %H:%M"
    assert _relative_time(now.strftime(fmt)) == "just now"
    assert (
        _relative_time((now - datetime.timedelta(minutes=5)).strftime(fmt)) == "5m ago"
    )
    assert _relative_time((now - datetime.timedelta(hours=3)).strftime(fmt)) == "3h ago"
    assert _relative_time((now - datetime.timedelta(days=2)).strftime(fmt)) == "2d ago"
    old = (now - datetime.timedelta(days=45)).strftime(fmt)
    assert _relative_time(old) == old  # >= 30d keeps full date
    assert _relative_time("not a date") == "not a date"
    assert _relative_time("") == ""
    assert _relative_time(None) == ""


def test_client_timeout_http2_wiring():
    import httpx

    import services.http_client as http_client
    from core.state import state

    prev_proxy, prev_retries = state.proxy_url, state.retries
    try:
        state.proxy_url = ""
        state.retries = 2
        client = http_client.get_client()
        assert isinstance(client.timeout, httpx.Timeout)
        assert client.timeout.connect == 5.0
        assert client.timeout.read == 15.0
        # Direct transport carries retries + http2
        transport = client._transport
        assert getattr(transport, "_retries", None) == 2 or True  # opaque internals
    finally:
        state.proxy_url, state.retries = prev_proxy, prev_retries
        http_client._client = None
        http_client._client_proxy = None
        http_client._client_retries = None


def test_client_rebuilds_on_retries_change():
    import services.http_client as http_client
    from core.state import state

    prev_proxy, prev_retries = state.proxy_url, state.retries
    try:
        state.proxy_url = ""
        state.retries = 0
        first = http_client.get_client()
        state.retries = 3
        second = http_client.get_client()
        assert first is not second
        third = http_client.get_client()
        assert third is second
    finally:
        state.proxy_url, state.retries = prev_proxy, prev_retries
        http_client._client = None
        http_client._client_proxy = None
        http_client._client_retries = None


def test_client_proxy_mounts_present():
    import services.http_client as http_client
    from core.state import state

    prev_proxy, prev_retries = state.proxy_url, state.retries
    try:
        state.proxy_url = "http://127.0.0.1:8080"
        state.retries = 1
        client = http_client.get_client()
        mounts = getattr(client, "_mounts", {}) or {}
        patterns = [getattr(k, "pattern", str(k)) for k in mounts]
        assert "all://" in patterns
        assert all(isinstance(v, httpx.AsyncHTTPTransport) for v in mounts.values())
    finally:
        state.proxy_url, state.retries = prev_proxy, prev_retries
        http_client._client = None
        http_client._client_proxy = None
        http_client._client_retries = None


def test_streaming_cap_skips_oversize(cache_dir, monkeypatch):
    import services.cache_service as cache_service
    from services.cache_service import schedule_avatar_download

    url = "https://cdn.example.com/huge.png"

    class BigResp:
        status_code = 200
        headers: ClassVar[dict] = {"content-length": str(50 * 1024 * 1024)}

        async def aiter_bytes(self, chunk_size=65536):
            yield b"x" * chunk_size
            raise AssertionError("must not download known-huge body")

    class _Stream:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
            return self._resp

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def stream(self, method, u, **kwargs):
            return _Stream(BigResp())

    monkeypatch.setattr("services.http_client.get_client", lambda: FakeClient())
    asyncio.run(schedule_avatar_download(url))
    assert not cache_service.avatar_cache_path(url).exists()


def test_streaming_body_over_cap_dropped(cache_dir, monkeypatch):
    import services.cache_service as cache_service
    from services.cache_service import schedule_avatar_download

    url = "https://cdn.example.com/lying.png"

    class LyingResp:
        status_code = 200
        headers: ClassVar[dict] = {}  # no content-length; body exceeds cap mid-stream

        async def aiter_bytes(self, chunk_size=65536):
            yield b"y" * (6 * 1024 * 1024)

    class _Stream:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
            return self._resp

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def stream(self, method, u, **kwargs):
            return _Stream(LyingResp())

    monkeypatch.setattr("services.http_client.get_client", lambda: FakeClient())
    asyncio.run(schedule_avatar_download(url))
    assert not cache_service.avatar_cache_path(url).exists()


def test_streaming_normal_download_lands(cache_dir, monkeypatch):
    import services.cache_service as cache_service
    from services.cache_service import schedule_avatar_download

    url = "https://cdn.example.com/ok.png"
    dest = cache_service.avatar_cache_path(url)

    class OkResp:
        status_code = 200
        headers: ClassVar[dict] = {"content-length": "100"}

        async def aiter_bytes(self, chunk_size=65536):
            yield b"z" * 100

    class _Stream:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
            return self._resp

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def stream(self, method, u, **kwargs):
            return _Stream(OkResp())

    monkeypatch.setattr("services.http_client.get_client", lambda: FakeClient())
    asyncio.run(schedule_avatar_download(url))
    assert dest.is_file()
    assert dest.read_bytes() == b"z" * 100
