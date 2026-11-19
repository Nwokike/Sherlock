"""Regression tests for Fix Batch 13 (email/enrich tail)."""

import asyncio
import logging


def test_total_modules_failure_returns_zero(monkeypatch):
    from services.email_service import EmailService

    service = EmailService()
    monkeypatch.setattr(
        service,
        "_load_modules",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert service.total_modules == 0


def test_status_3xx_returns_empty(monkeypatch):
    """3xx is a redirect stub at the caller (socid follows redirects)."""
    import services.enrich_service as enrich_mod
    from services.enrich_service import EnrichService

    async def _redirect(url, timeout, headers=None, cookies_str=""):
        return ("<html>moved</html>", 302)

    async def _extract(text):
        return {"name": "N"}

    async def _fake_parse(url, timeout, headers=None, cookies_str=""):
        return await _redirect(url, timeout, headers, cookies_str)

    async def _fake_extract(text):
        return await _extract(text)

    monkeypatch.setattr(enrich_mod, "_parse_in_thread", _fake_parse)
    monkeypatch.setattr(enrich_mod, "_extract_in_thread", _fake_extract)
    service = EnrichService()
    assert asyncio.run(service.enrich_url("https://a.example/x")) == {}


def test_empty_extract_logs_login_wall(monkeypatch, caplog):
    """2xx + empty extract is logged distinctly (login-wall, not failure)."""
    import services.enrich_service as enrich_mod
    from services.enrich_service import EnrichService

    async def _ok(url, timeout, headers=None, cookies_str=""):
        return ("<html>challenge</html>", 200)

    async def _empty(text):
        return {}

    monkeypatch.setattr(enrich_mod, "_parse_in_thread", _ok)
    monkeypatch.setattr(enrich_mod, "_extract_in_thread", _empty)
    service = EnrichService()
    with caplog.at_level(logging.DEBUG, logger="services.enrich_service"):
        assert asyncio.run(service.enrich_url("https://a.example/x")) == {}
    assert any("login-wall" in r.message for r in caplog.records)


def test_proxy_doc_note_present():
    from pathlib import Path

    src = Path("src/services/email_service.py").read_text(encoding="utf-8")
    assert "Process-global by necessity" in src
    assert "do not parallelize" in src
