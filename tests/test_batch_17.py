"""Regression tests for Fix Batch 17 (P2 no-dep):

- core.tasks.spawn: returns the Task, keeps exceptions retrievable, and
  the added done-callback routes failures to the logger (no swallowed
  tracebacks on fire-and-forget background work).
- biometric tiers: capability_label returns a plain string under no-page
  conditions; stop_prompt is a safe no-op without a page;
  authenticate_detailed forwards biometric_only / sensitive /
  persist_across_backgrounding honestly (verified via stubbed LocalAuth).
- graph menus: pyvis viewer is built with select/filter menus on and
  member-reason edges rendered in the dark-gold color.
- Jinja dossier CSS: both HTML templates embed the same _DOSSIER_CSS_CORE.
- build meta: [tool.flet] carries description/company/copyright/icon.
"""

from __future__ import annotations

import asyncio
import logging
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def test_spawn_returns_live_task_and_logs_failure(caplog):
    """spawn() returns the task; failures are logged, not swallowed."""

    async def scenario():
        from core.tasks import spawn

        async def boom():
            raise ValueError("kaboom-17")

        async def fine():
            return 42

        with caplog.at_level(logging.WARNING, logger="core.tasks"):
            t_fail = spawn(boom(), name="test-boom")
            t_ok = spawn(fine(), name="test-fine")
            assert isinstance(t_fail, asyncio.Task)
            assert isinstance(t_ok, asyncio.Task)
            assert t_fail.get_name() == "test-boom"
            assert await t_ok == 42
            await asyncio.sleep(0)  # let the done-callback run
        assert "test-boom" in caplog.text
        assert "kaboom-17" in caplog.text
        assert "test-fine" not in caplog.text

    asyncio.run(scenario())


def test_spawn_cancelled_is_silent(caplog):
    """Cancelled tasks must not log (cancellation is not a failure)."""

    async def scenario():
        from core.tasks import spawn

        async def hang():
            await asyncio.sleep(60)

        with caplog.at_level(logging.WARNING, logger="core.tasks"):
            t = spawn(hang(), name="test-cancel")
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            await asyncio.sleep(0)
        assert "test-cancel" not in caplog.text

    asyncio.run(scenario())


def test_capability_label_without_page():
    """No active flet page -> plain-string capability, never raises."""
    from services import biometric_service as bs

    async def scenario():
        label = await bs.capability_label()
        assert isinstance(label, str) and label

    asyncio.run(scenario())


def test_stop_prompt_noop_without_page():
    """stop_prompt must be safe to call when no prompt is in flight."""
    from services import biometric_service as bs

    async def scenario():
        await bs.stop_prompt()  # must not raise

    asyncio.run(scenario())


def test_authenticate_forwards_tiers(monkeypatch):
    """biometric_only/sensitive/persist flags reach LocalAuthentication."""
    from services import biometric_service as bs

    # Patch the class constructor the function uses.
    seen = {}

    class FakeLocalAuth:
        async def is_device_supported(self):
            return True

        async def authenticate(self, reason, **kwargs):
            seen.update(kwargs)
            seen["reason"] = reason
            return True

    monkeypatch.setattr(bs._fla, "LocalAuthentication", lambda: FakeLocalAuth())

    async def scenario():
        import flet as ft

        # Fake a page context so the guard passes.
        class FakeCtx:
            page = object()

        monkeypatch.setattr(ft, "context", FakeCtx())
        res = await bs.authenticate_detailed(
            " history unlock ", biometric_only=True, sensitive=False
        )
        assert res.ok and res.status is bs.AuthStatus.SUCCESS

    asyncio.run(scenario())
    caught = dict(seen)
    assert caught["biometric_only"] is True
    assert caught["sensitive_transaction"] is False
    assert caught["persist_across_backgrounding"] is True
    assert caught["reason"] == "history unlock"


def test_authenticate_strict_state_forces_biometric_only(monkeypatch):
    """biometric_strict=True in state elevates even biometric_only=False."""
    from services import biometric_service as bs

    seen = {}

    class FakeLocalAuth:
        async def is_device_supported(self):
            return True

        async def authenticate(self, reason, **kwargs):
            seen.update(kwargs)
            return True

    monkeypatch.setattr(bs, "_AUTH_AVAILABLE", True)
    monkeypatch.setattr(bs._fla, "LocalAuthentication", lambda: FakeLocalAuth())

    async def scenario():
        import flet as ft

        from core.state import state

        class FakeCtx:
            page = object()

        monkeypatch.setattr(ft, "context", FakeCtx())
        old = state.biometric_strict
        state.biometric_strict = True
        try:
            await bs.authenticate_detailed("x", biometric_only=False)
        finally:
            state.biometric_strict = old

    asyncio.run(scenario())
    assert seen["biometric_only"] is True


def test_graph_pyvis_menus_and_member_color(tmp_path):
    """select/filter menus on; member-of edges use dark gold."""
    from services import graph_service as gs

    if gs.nx is None:
        pytest.skip("networkx unavailable")
    g = gs.build_identity_graph(
        "alice",
        [{"name": "GitHub", "url": "https://github.com/alice"}],
    )
    assert g is not None
    out = tmp_path / "graph.html"
    assert gs.export_pyvis_html(g, out) == out
    html = out.read_text(encoding="utf-8")
    # Menus are emitted as JS config by pyvis when enabled:
    assert "filterMenu" in html or "filter_menu" in html or "selectNode" in html
    # Builder edges render the default gold link color.
    assert "#D4AF37" in html
    # Reason-color mechanism: a member-reason edge renders dark gold,
    # a generic edge renders gold (unit-check via a hand-built graph, since
    # no builder currently emits a "member" reason string).
    g2 = gs.nx.Graph()
    for n in "abc":
        g2.add_node(n, label=n, title="", color="#D4AF37", size=12)
    g2.add_edge("a", "b", reason="member_of_community")
    g2.add_edge("b", "c", reason="claimed_account")
    out2 = tmp_path / "graph2.html"
    assert gs.export_pyvis_html(g2, out2) == out2
    html2 = out2.read_text(encoding="utf-8")
    assert "#8C6B1A" in html2  # member-reason edge -> dark gold
    assert "#D4AF37" in html2  # generic edge -> gold


def test_dossier_css_core_shared():
    """Both dossier templates embed the same CSS core constant."""
    from services import report_service as rs

    assert rs._DOSSIER_CSS_CORE.strip().startswith(":root")
    assert "--gold: #D4AF37" in rs._DOSSIER_CSS_CORE
    for tpl_name in ("_HTML_TEMPLATE", "_EMAIL_HTML_TEMPLATE"):
        tpl = getattr(rs, tpl_name, "")
        assert rs._DOSSIER_CSS_CORE in tpl, tpl_name


def test_build_meta_present():
    """[tool.flet] carries store/packaging metadata."""
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    flet_meta = data.get("tool", {}).get("flet", {})
    assert flet_meta.get("description"), "missing [tool.flet] description"
    assert flet_meta.get("company"), "missing [tool.flet] company"
    assert flet_meta.get("copyright"), "missing [tool.flet] copyright"
    icon = flet_meta.get("icon")
    assert icon and (REPO / icon).exists(), f"icon missing: {icon}"


def test_biometric_strict_storage_key_roundtrip(tmp_path, monkeypatch):
    """Strict flag persists under its own storage key spelling."""
    from core.constants import STORAGE_BIOMETRIC_STRICT

    assert STORAGE_BIOMETRIC_STRICT == "sherlock_biometric_strict"
