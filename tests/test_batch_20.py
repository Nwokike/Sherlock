"""Regression tests for the final completion sweep (Batch 20).

- human_date matrix (ISO, month, year, unix, garbage -> None).
- permute_username: separator swaps, cap, invalid inputs.
- paste-URL normalization: URL -> handle, plain names untouched.
- Jinja dossier env: human_date filter registered and used.
- email 429 backoff: rate-limited stub retried once, eventual Taken wins.
- gravatar fallback avatar in the email dossier.
- test_id automation hook honors SHERLOCK_TEST_IDS.
"""

from __future__ import annotations


def test_human_date_matrix():
    from core.format import human_date as h

    assert h("2019-04-01T12:34:56Z") == "Apr 1, 2019"
    assert h("2019-04-01") == "Apr 1, 2019"
    assert h("2019-04") == "Apr 2019"
    assert h("March 2019") == "Mar 2019"
    assert h("2019") == "2019"
    assert h("1546300800") == "Jan 2019"  # unix seconds as string
    assert h(1546300800) == "Jan 2019"  # and as int
    assert h("not a date") is None
    assert h("") is None
    assert h(None) is None
    assert h({"a": 1}) is None
    assert h(True) is None
    assert h("x" * 50) is None
    assert h(9999) is None  # out of unix range


def test_permute_username_matrix():
    from core.permute import MAX_VARIANTS
    from core.permute import permute_username as p

    parts = p("john.doe")
    assert "john_doe" in parts and "john-doe" in parts and "johndoe" in parts
    assert "john.doe" not in parts
    assert len(parts) <= MAX_VARIANTS
    # no separator -> no variants
    assert p("johndoe") == []
    assert p("j") == []
    # invalid input -> no variants (never crash the scan builder)
    assert p("") == []
    assert p("bad name!") == []
    assert p("a" * 70) == []
    assert p("x_y.z-w") and len(p("x_y.z-w")) <= MAX_VARIANTS
    # dedupe + original excluded
    for v in p("john.doe"):
        assert v != "john.doe"


def test_normalize_pasted_query_matrix():
    from screens.home_screen import _normalize_pasted_query as n

    assert n("https://github.com/torvalds") == "torvalds"
    assert n("https://x.com/jack?x=1") == "jack"
    assert n("www.reddit.com/user/alice/") == "alice"
    assert n("plain_user") == "plain_user"
    assert n("https://github.com/") == "https://github.com/"
    assert n("@alice") == "alice"
    assert n("") == ""
    assert n("https://site.com/a%20b") == "a b"


def test_jinja_human_date_filter_registered():
    from services import report_service as rs

    assert rs._JINJA_AVAILABLE
    env = rs._jinja_env()
    assert "human_date" in env.filters
    tmpl = env.from_string("{{ v|human_date }}")
    assert tmpl.render(v="2019-04-01T00:00:00Z") == "Apr 1, 2019"
    # pass-through for junk (no render crash)
    assert tmpl.render(v="whatever") == "whatever"


def test_html_dossier_humanizes_dates():
    from services import report_service as rs

    class _R:
        site_name = "GitHub"
        url_user = "https://github.com/alice"
        url_main = "https://github.com"
        status = "Claimed"

    enrich = {
        "https://github.com/alice": {
            "name": "Alice",
            "bio": "dev",
            "joined": "2019-04-01T12:00:00Z",
        }
    }
    out = rs.generate_html_report("alice", [_R()], [], [], enrich, 1, 1)
    assert out is not None
    assert b"Apr 1, 2019" in out


def test_rate_limit_backoff_retries_once():
    """A rate-limited stub is retried; a later Taken result wins."""
    import asyncio

    from services import email_service as es

    calls = []

    async def flaky(email):
        from holehe_v2 import Result

        calls.append(1)
        if len(calls) == 1:
            return Result.error("Rate limited (429)")
        return Result.taken(url="https://a.com")

    async def scenario():
        original = es._holehe_modules
        es._holehe_modules = {"flaky": flaky}
        try:
            svc = es.EmailService()
            return await svc.search("u@e.com", on_progress=lambda p: None, timeout=10)
        finally:
            es._holehe_modules = original

    progress = asyncio.run(scenario())
    assert len(calls) == 2  # initial + exactly one retry
    assert len(progress.found) == 1
    assert not progress.rate_limited


def test_rate_limit_backoff_cancel_skips_retry():
    """A cancel during the backoff wait produces no retry and no mark loss."""
    import asyncio

    from services import email_service as es

    calls = []

    async def slow_rl(email):
        from holehe_v2 import Result

        calls.append(1)
        return Result.error("Rate limited (429)")

    async def scenario():
        original = es._holehe_modules
        es._holehe_modules = {"s": slow_rl}
        svc = es.EmailService()
        try:
            task = asyncio.create_task(
                svc.search("u@e.com", on_progress=lambda p: None, timeout=10)
            )
            await asyncio.sleep(0.6)  # first attempt lands, backoff starts
            svc.cancel()
            try:
                res = await asyncio.wait_for(task, timeout=20)
            except asyncio.CancelledError:
                return "outer-cancel", len(calls)
            return res.is_cancelled, len(calls)
        finally:
            es._holehe_modules = original

    marked, n_calls = asyncio.run(scenario())
    assert marked is True  # the live-scan mark still lands
    assert n_calls == 1  # retry suppressed by the cancel


def test_gravatar_fallback_avatar():
    from services import report_service as rs

    rows = [{"name": "GitHub", "domain": "github.com", "exists": True, "others": {}}]
    out = rs.generate_email_html_report("User@Example.com", rows)
    assert out is not None
    import hashlib

    digest = hashlib.md5(  # noqa: S324 — asserting the Gravatar contract
        b"user@example.com"
    ).hexdigest()
    assert digest.encode() in out


def test_use_test_ids_hook(monkeypatch):
    """Both branches: ids off by default, on with USE_TEST_IDS true."""
    from core import constants

    monkeypatch.setattr(constants, "USE_TEST_IDS", False, raising=True)
    assert constants.test_id("home-search-button") is None

    monkeypatch.setattr(constants, "USE_TEST_IDS", True, raising=True)
    assert constants.test_id("home-search-button") == "home-search-button"
