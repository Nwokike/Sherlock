"""Tests for the 6-layer regenerable cache architecture (cache_service).

Each layer is exercised against an isolated tmp cache dir via
FLET_APP_STORAGE_CACHE so no real cache state leaks between tests.
"""

from __future__ import annotations

import asyncio
import json
import pickle
import time
from types import SimpleNamespace

import pytest

from services import cache_service
from services.cache_service import (
    build_sites_indices,
    cached_report_path,
    clear_all_caches,
    ensure_cached_avatar,
    flush_dns_cache,
    get_dns_record,
    is_domain_dead,
    load_cached_report,
    load_geo_cache,
    results_fingerprint,
    save_cached_report,
    save_compiled_db,
    save_geo_cache,
    save_sites_indices,
    load_sites_indices,
    schedule_avatar_download,
    set_dns_record,
    try_load_compiled_db,
)


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Isolate every test's cache tier into a tmp directory."""
    d = tmp_path / "cache"
    d.mkdir()
    monkeypatch.setenv("FLET_APP_STORAGE_CACHE", str(d))
    # Reset the in-memory DNS store between tests.
    cache_service._dns_store = None
    cache_service._dns_dirty = False
    yield d
    cache_service._dns_store = None
    cache_service._dns_dirty = False


# ── Layer 1: Pre-Compiled Site Database ───────────────────────────────


class FakeDB:
    """Picklable stand-in for MaigretDatabase."""

    def __init__(self, n=5):
        self._sites = [SimpleNamespace(name=f"site{i}") for i in range(n)]

    @property
    def sites(self):
        return self._sites


def _write_manifest(path, content=b'{"sites": {}}'):
    path.write_bytes(content)
    return path


def test_db_cache_roundtrip(cache_dir, tmp_path):
    manifest = _write_manifest(tmp_path / "db.json", b'{"sites": {"a": 1}}')
    src = str(manifest)

    # Miss on first load (no cache yet).
    assert try_load_compiled_db(src) is None

    db = FakeDB(7)
    save_compiled_db(src, db)

    # Hit afterwards — same object content restored.
    loaded = try_load_compiled_db(src)
    assert loaded is not None
    assert len(loaded.sites) == 7
    assert loaded.sites[0].name == "site0"

    # Sidecar meta records the source + validation fields.
    meta = json.loads((cache_dir / "compiled_db.meta.json").read_text())
    assert meta["src"] == src
    assert "hash" in meta and "mtime" in meta and "size" in meta


def test_db_cache_invalidated_on_content_change(cache_dir, tmp_path):
    manifest = _write_manifest(tmp_path / "db.json", b'{"sites": {"a": 1}}')
    src = str(manifest)
    save_compiled_db(src, FakeDB())

    # Edit manifest content while preserving mtime — the SHA-256 fallback
    # must catch what the cheap mtime/size check misses.
    st = manifest.stat()
    _write_manifest(manifest, b'{"sites": {"DIFFERENT": 1}}')
    import os

    os.utime(manifest, ns=(st.st_atime_ns, st.st_mtime_ns))

    assert try_load_compiled_db(src) is None


def test_db_cache_invalidated_on_mtime_change(cache_dir, tmp_path):
    manifest = _write_manifest(tmp_path / "db.json")
    src = str(manifest)
    save_compiled_db(src, FakeDB())

    # Rewrite + back-date mtime so size matches but mtime differs.
    _write_manifest(manifest, b'{"sites": {"x": 1}}')
    old = time.time() - 3600
    import os

    os.utime(manifest, (old, old))

    assert try_load_compiled_db(src) is None


def test_db_cache_rejects_corrupt_pickle(cache_dir, tmp_path):
    manifest = _write_manifest(tmp_path / "db.json")
    src = str(manifest)
    save_compiled_db(src, FakeDB())

    # Corrupt the pickle bytes; meta still validates.
    (cache_dir / "compiled_db.pkl").write_bytes(b"NOT A PICKLE")

    assert try_load_compiled_db(src) is None


def test_db_cache_rejects_empty_db(cache_dir, tmp_path):
    manifest = _write_manifest(tmp_path / "db.json")
    src = str(manifest)
    save_compiled_db(src, FakeDB(0))  # zero sites — sanity guard rejects

    # The pickle loads but has no sites -> treated as unusable.
    assert try_load_compiled_db(src) is None


def test_db_cache_bypasses_remote_manifests(cache_dir, tmp_path, monkeypatch):
    # A remote manifest must never read/write the pickle cache.
    url = "https://example.com/data.json"
    save_compiled_db(url, FakeDB())
    assert not (cache_dir / "compiled_db.pkl").exists()
    assert try_load_compiled_db(url) is None


# ── Layer 2: Avatar Image Cache ──────────────────────────────────────


def test_avatar_path_is_deterministic(cache_dir):
    p1 = cache_service.avatar_cache_path("https://cdn.example.com/a.png")
    p2 = cache_service.avatar_cache_path("https://cdn.example.com/a.png")
    p3 = cache_service.avatar_cache_path("https://cdn.example.com/b.png")
    assert p1 == p2
    assert p1 != p3
    assert p1.parent == cache_dir / "avatars"
    assert p1.name.endswith(".img")


def test_ensure_cached_avatar_returns_url_when_uncached(cache_dir):
    url = "https://cdn.example.com/me.png"
    assert ensure_cached_avatar(url) == url
    assert ensure_cached_avatar("") == ""
    assert ensure_cached_avatar("not-a-url") == "not-a-url"


def test_ensure_cached_avatar_returns_local_path_when_cached(cache_dir):
    url = "https://cdn.example.com/me.png"
    local = cache_service.avatar_cache_path(url)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(b"\x89PNG-fake-bytes")

    result = ensure_cached_avatar(url)
    assert result == str(local)
    assert result != url


def test_avatar_download_populates_cache(cache_dir, monkeypatch):
    url = "https://cdn.example.com/me.png"
    dest = cache_service.avatar_cache_path(url)

    class FakeResp:
        status_code = 200
        content = b"\x89PNG-fake"

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, u):
            assert u == url
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    asyncio.run(schedule_avatar_download(url))
    assert dest.is_file()
    assert dest.read_bytes() == b"\x89PNG-fake"
    # Second call is a no-op (already cached).
    asyncio.run(schedule_avatar_download(url))
    assert dest.read_bytes() == b"\x89PNG-fake"


def test_avatar_download_silent_on_failure(cache_dir, monkeypatch):
    url = "https://dead.example.com/me.png"

    class BoomClient:
        def __init__(self, *a, **k):
            raise OSError("no network")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", BoomClient)

    # Must not raise.
    asyncio.run(schedule_avatar_download(url))
    assert not cache_service.avatar_cache_path(url).exists()


# ── Layer 3: Pre-Rendered Report Cache ───────────────────────────────


def _fake_found(urls):
    return [
        SimpleNamespace(url_user=u, url_main=f"https://{u.split('/')[2]}/")
        for u in urls
    ]


def test_results_fingerprint_stable_and_order_insensitive():
    a = _fake_found(["https://x.com/u1", "https://y.com/u2"])
    b = _fake_found(["https://y.com/u2", "https://x.com/u1"])  # reordered
    c = _fake_found(["https://x.com/u1"])  # different set

    assert results_fingerprint(a) == results_fingerprint(b)
    assert results_fingerprint(a) != results_fingerprint(c)
    assert len(results_fingerprint(a)) == 16


def test_report_cache_roundtrip(cache_dir):
    found = _fake_found(["https://x.com/u1", "https://y.com/u2"])

    # Miss before saving.
    assert load_cached_report("pdf", "johndoe", found, "pdf") is None

    save_cached_report("pdf", "johndoe", found, "pdf", b"%PDF-1.4 fake")

    # Hit with the same found-set (even reordered).
    reordered = list(reversed(found))
    assert load_cached_report("pdf", "johndoe", reordered, "pdf") == b"%PDF-1.4 fake"

    # Different found-set is a different key.
    other = _fake_found(["https://z.com/u9"])
    assert load_cached_report("pdf", "johndoe", other, "pdf") is None

    # Query is sanitized into the filename.
    p = cached_report_path("pdf", "John Doe!@#", found, "pdf")
    assert " " not in p.name and "!" not in p.name
    assert p.parent == cache_dir / "reports"


def test_report_cache_xmind_ext(cache_dir):
    found = _fake_found(["https://x.com/u1"])
    save_cached_report("xmind", "jane", found, "xmind", b"PK-xmind-zip")
    assert load_cached_report("xmind", "jane", found, "xmind") == b"PK-xmind-zip"
    assert (cache_dir / "reports").is_dir()


def test_report_cache_never_writes_empty(cache_dir):
    found = _fake_found(["https://x.com/u1"])
    save_cached_report("pdf", "jane", found, "pdf", b"")
    assert load_cached_report("pdf", "jane", found, "pdf") is None


# ── Layer 4: Persistent Geo Cache ────────────────────────────────────


def test_geo_cache_roundtrip_and_version_guard(cache_dir):
    lookup = {"Berlin, Germany": ["Germany", "🇩🇪", "DE", "DEU", "Germany", ""]}
    save_geo_cache(lookup)

    loaded = load_geo_cache()
    assert loaded["Berlin, Germany"][0] == "Germany"
    assert loaded["Berlin, Germany"][2] == "DE"

    # A version mismatch invalidates the whole cache.
    bad = {
        cache_service._GEO_MIN_TS_KEY: "0.0.0-old",
        "entries": lookup,
    }
    (cache_dir / "geo_cache.json").write_text(json.dumps(bad))
    assert load_geo_cache() == {}


def test_geo_cache_rejects_oversized_and_malformed(cache_dir):
    # Malformed JSON.
    (cache_dir / "geo_cache.json").write_text("{not json")
    assert load_geo_cache() == {}

    # Oversized entries dict is dropped (bounded memory).
    big = {f"loc{i}": ["x"] for i in range(cache_service._GEO_MAX_ENTRIES + 1)}
    payload = {
        cache_service._GEO_MIN_TS_KEY: __import__("pycountry").__version__,
        "entries": big,
    }
    (cache_dir / "geo_cache.json").write_text(json.dumps(payload))
    assert load_geo_cache() == {}


def test_resolve_location_uses_disk_cache(cache_dir, monkeypatch):
    from core import geo_utils

    # Simulate a previous launch's persisted lookup.
    monkeypatch.setattr(geo_utils, "_DISK_CACHE", None)
    row = ["Germany", "🇩🇪", "DE", "DEU", "Federal Republic of Germany", ""]
    (cache_dir / "geo_cache.json").write_text(
        json.dumps(
            {
                cache_service._GEO_MIN_TS_KEY: __import__("pycountry").__version__,
                "entries": {"Moon Base Alpha": row},
            }
        )
    )

    result = geo_utils.resolve_location("Moon Base Alpha")
    assert result is not None
    assert result.alpha_2 == "DE"
    assert result.flag == "🇩🇪"
    # The fake entry would never fuzzy-match a real country — proof the
    # disk cache served the lookup.


def test_resolve_location_persists_new_lookups(cache_dir, monkeypatch):
    from core import geo_utils

    monkeypatch.setattr(geo_utils, "_DISK_CACHE", None)
    geo_utils.resolve_location.cache_clear()

    res = geo_utils.resolve_location("Lagos, Nigeria")
    assert res is not None and res.alpha_2 == "NG"

    # The lookup was persisted for the next launch.
    persisted = load_geo_cache()
    assert "Lagos, Nigeria" in persisted
    assert persisted["Lagos, Nigeria"][2] == "NG"


# ── Layer 5: Inverted Site Tag Indices ───────────────────────────────


def _fake_sites_dict():
    def site(tags):
        return SimpleNamespace(tags=tags)

    return {
        "GitHub": site(["coding", "us"]),
        "VK": site(["social", "ru"]),
        "Chess": site(["gaming", "ru"]),
        "Habr": site(["coding", "ru"]),
    }


def test_build_sites_indices_buckets():
    idx = build_sites_indices(_fake_sites_dict())
    by_tag = idx["by_tag"]

    assert by_tag["coding"] == ["GitHub", "Habr"]  # sorted
    assert by_tag["ru"] == ["Chess", "Habr", "VK"]
    assert set(by_tag.keys()) == {"coding", "us", "social", "ru", "gaming"}
    assert idx["all_names"] == ["Chess", "GitHub", "Habr", "VK"]
    assert len(idx["db_hash"]) == 64


def test_sites_indices_roundtrip(cache_dir):
    idx = build_sites_indices(_fake_sites_dict())
    save_sites_indices(idx)
    loaded = load_sites_indices()
    assert loaded == idx
    assert loaded["by_tag"]["coding"] == ["GitHub", "Habr"]


def test_sites_indices_load_missing_returns_none(cache_dir):
    assert load_sites_indices() is None


def test_sites_screen_index_lookup_shape():
    """The SitesScreen contract: index maps lowercase tag -> set of names."""
    idx = build_sites_indices(_fake_sites_dict())
    bucket = set(idx["by_tag"]["ru"])
    assert bucket == {"Chess", "Habr", "VK"}


# ── Layer 6: Persistent DNS Cache ────────────────────────────────────


def test_dns_record_roundtrip_and_flush(cache_dir):
    set_dns_record("github.com", ["140.82.121.4"])
    set_dns_record("dead.example.com", None, dead=True)

    # Not persisted until flushed.
    assert not (cache_dir / "dns_cache.json").exists()
    flush_dns_cache()

    rec = get_dns_record("github.com")
    assert rec is not None
    assert rec["ips"] == ["140.82.121.4"]
    assert not rec["dead"]

    assert is_domain_dead("dead.example.com")
    assert not is_domain_dead("github.com")
    assert not is_domain_dead("never-seen.example.com")


def test_dns_cache_reload_from_disk(cache_dir):
    set_dns_record("github.com", ["140.82.121.4"])
    flush_dns_cache()

    # Simulate a new process: reset the in-memory store.
    cache_service._dns_store = None
    rec = get_dns_record("github.com")
    assert rec is not None
    assert rec["ips"] == ["140.82.121.4"]


def test_dns_cache_ttl_expiry(cache_dir):
    # Pre-seed an expired record on disk.
    expired = {
        "entries": {
            "old.example.com": {
                "ips": ["1.2.3.4"],
                "ts": time.time() - (cache_service._DNS_TTL_SEC + 100),
                "dead": False,
            }
        }
    }
    (cache_dir / "dns_cache.json").write_text(json.dumps(expired))
    cache_service._dns_store = None

    assert get_dns_record("old.example.com") is None

    # Dead flags never expire (a dead domain stays dead until proven alive).
    expired_dead = {
        "entries": {
            "gone.example.com": {
                "ips": [],
                "ts": time.time() - (cache_service._DNS_TTL_SEC + 100),
                "dead": True,
            }
        }
    }
    (cache_dir / "dns_cache.json").write_text(json.dumps(expired_dead))
    cache_service._dns_store = None
    assert is_domain_dead("gone.example.com")


def test_dns_prewarm_resolves_and_skips_dead(cache_dir, monkeypatch):
    import socket as socket_mod

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "github.com":
            return [(2, 1, 6, "", ("140.82.121.4", 443))]
        raise OSError("no DNS in tests")

    monkeypatch.setattr(socket_mod, "getaddrinfo", fake_getaddrinfo)

    # Mark a domain dead first — pre-warm must skip it entirely.
    set_dns_record("dead.example.com", None, dead=True)

    async def run():
        return await cache_service.prewarm_dns(
            [
                ("SiteA", "https://github.com/profile"),
                ("SiteA-mirror", "https://github.com/other"),  # dedup host
                ("Dead", "https://dead.example.com/x"),  # skipped: known dead
                ("Blocked", "https://unresolvable.example/x"),  # fails silently
            ],
            max_hosts=10,
        )

    warmed = asyncio.run(run())
    assert warmed == 1  # only github.com resolved
    rec = get_dns_record("github.com")
    assert rec is not None and rec["ips"] == ["140.82.121.4"]
    assert not rec["dead"]

    # Dead domain untouched by pre-warm (still dead, nothing new recorded).
    assert is_domain_dead("dead.example.com")
    assert get_dns_record("unresolvable.example") is None

    # Flush persisted the warmed records.
    assert (cache_dir / "dns_cache.json").exists()


def test_dns_prewarm_empty_input(cache_dir):
    warmed = asyncio.run(cache_service.prewarm_dns([]))
    assert warmed == 0


def test_dns_prewarm_no_network_raises_nothing(cache_dir):
    async def run():
        return await cache_service.prewarm_dns(
            [("X", "https://nonexistent.invalid.host.example")], max_hosts=5
        )

    warmed = asyncio.run(run())
    assert warmed == 0  # resolution failed silently — recorded nothing dead


# ── Cross-layer helpers ──────────────────────────────────────────────


def test_clear_all_caches_wipes_every_layer(cache_dir):
    # Populate every layer.
    save_geo_cache({"x": ["y"]})
    save_sites_indices(build_sites_indices(_fake_sites_dict()))
    (cache_dir / "avatars").mkdir(parents=True)
    (cache_dir / "avatars" / "a.img").write_bytes(b"x")
    (cache_dir / "compiled_db.pkl").write_bytes(pickle.dumps(FakeDB()))

    removed = clear_all_caches()
    assert removed >= 3
    assert list(cache_dir.iterdir()) == []
    # In-memory DNS store reset too.
    assert cache_service._dns_store is None
