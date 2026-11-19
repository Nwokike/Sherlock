"""Regression tests for Fix Batch 18 (P3 mechanical).

Covers the verified-open items; the rest of the P3 list was verified
already-done by earlier batches (stat_card typing, targets_card Callable,
geo LRU, storage fsync/_last_write, controller noops, http_client timeout,
actions widen, notify actions, report CSV/TXT, email regex tail) or
declined (ad mapping per owner freeze; storage schema migration; watchdog
and rich-CLI are friction-gated; notify instance reuse rejected — per-call
bgcolor/duration/action vary).
"""

from __future__ import annotations

import asyncio
import logging


def test_format_count_matrix():
    from core.format import format_count

    assert format_count(0) == "0"
    assert format_count(509) == "509"
    assert format_count(5203) == "5,203"
    assert format_count(1234567) == "1,234,567"
    assert format_count(True) == "True"  # bools are not counts
    assert format_count(4.5) == "4.5"
    assert format_count(5203.0) == "5,203"
    assert format_count(None) == "None"
    assert format_count("5,200+") == "5,200+"  # passthrough, never crash


def test_section_header_uppercases():
    from components.section_header import SectionHeader

    hdr = SectionHeader("mixed Case Input")
    text = hdr.content
    assert text.value == "MIXED CASE INPUT"


def test_empty_state_handlerless_label_warns(caplog):
    from components.empty_state import EmptyState

    with caplog.at_level(logging.WARNING, logger="EmptyState"):
        ctl = EmptyState("No history", action_label="Retry")
    assert "no handler" in caplog.text
    assert ctl is not None  # still renders, button omitted


def test_empty_state_with_handler_no_warning(caplog):
    from components.empty_state import EmptyState

    with caplog.at_level(logging.WARNING, logger="EmptyState"):
        EmptyState("No history", action_label="Retry", on_action=lambda: None)
    assert "no handler" not in caplog.text


def test_tokens_all_complete():
    import core.tokens as tokens

    names = [n for n in dir(tokens) if n.isupper()]
    assert set(tokens.__all__) == set(names), set(names) ^ set(tokens.__all__)
    assert tokens.__all__ == sorted(tokens.__all__)


def test_targets_card_uses_grouped_counts():
    from components.targets_card import TargetsCard
    from core import tokens as _t  # noqa: F401  (ensures tokens import intact)

    card = TargetsCard(selected_count=5203, total_count=0)
    row = card.content
    title = row.controls[1].controls[0]
    assert "5,203" in title.value

    card_all = TargetsCard(selected_count=0, total_count=5203)
    row_all = card_all.content
    subtitle = row_all.controls[1].controls[1]
    assert "5,203" in subtitle.value


def test_debounce_uses_spawn():
    """The missed create_task now routes through the tracked helper."""
    import inspect

    import hooks.use_debounce as ud

    src = inspect.getsource(ud)
    assert "spawn(" in src
    assert "asyncio.create_task" not in src


def test_graph_export_path_types():
    """out_path accepts str or Path (annotation honesty check)."""
    import inspect

    from services import graph_service as gs

    sig = inspect.signature(gs.export_graphml_gexf)
    assert "str" in str(sig.parameters["out_path"].annotation)
    sig2 = inspect.signature(gs.export_pyvis_html)
    assert "str" in str(sig2.parameters["out_path"].annotation)


def test_update_dialog_no_exception_logs():
    """Close-failure paths log at debug, not exception (noisy tracebacks)."""
    import inspect

    import components.update_dialog as upd

    src = inspect.getsource(upd)
    assert "logger.exception" not in src


def test_no_bare_create_task_in_src():
    """Every fire-and-forget site routes through spawn() (RUF006 clean)."""
    import re
    from pathlib import Path

    offenders = []
    for path in (Path("src")).rglob("*.py"):
        if path.name == "tasks.py":
            continue  # the helper itself; its docstring names the pattern
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'")):
                continue
            if re.search(
                r"(?<!\w)(asyncio\.create_task|loop\.create_task|asyncio\.ensure_future)\(",
                line,
            ):
                offenders.append(f"{path}:{i}: {stripped}")
    assert not offenders, "\n".join(offenders)


def test_email_regex_long_tail_intact():
    """Batch 8/13 tail still matches code-less throttle messages."""
    from services.email_service import _is_rate_limited

    assert _is_rate_limited("Rate limited")
    assert _is_rate_limited("Slow down — too many requests from your IP")
    assert _is_rate_limited("Please try again later")
    assert _is_rate_limited("HTTP Error: 404") is False
    assert _is_rate_limited(None) is False


def test_spawn_debounce_timer_cancel_safe():
    """spawn() tasks expose .done()/.cancel() like raw tasks (hook use)."""

    async def scenario():
        from core.tasks import spawn

        async def sleepy():
            await asyncio.sleep(60)

        t = spawn(sleepy(), name="test-timer")
        assert not t.done()
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        assert t.done()

    asyncio.run(scenario())
