"""Unit tests for MemoryLogHandler and streaming real-time enrichment."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from core.logger_handler import MemoryLogHandler
from core.state import state
from main import AppController
from services.sherlock_service import SearchProgress, SiteResult


def test_memory_log_handler_fifo():
    handler = MemoryLogHandler()
    handler.clear_logs()
    assert handler.get_logs() == []

    test_logger = logging.getLogger("test_fifo")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    for i in range(10):
        test_logger.info(f"msg_{i}")

    logs = handler.get_logs()
    assert len(logs) == 10
    assert "msg_0" in logs[0]
    assert "msg_9" in logs[9]

    handler.clear_logs()
    assert handler.get_logs() == []
    test_logger.removeHandler(handler)


def test_streaming_enrichment_queues_and_processes():
    page = MagicMock()
    page.dialog = None
    controller = AppController(page)
    controller._main_loop = asyncio.new_event_loop()

    # Mock enrich service
    mock_enrich = MagicMock()
    mock_enrich.is_available = True
    mock_enrich.enrich_url = AsyncMock(
        return_value={
            "name": "Enriched User",
            "avatar": "https://example.com/avatar.png",
        }
    )
    mock_enrich.enrich_url_with_mutations = AsyncMock(
        return_value={
            "name": "Enriched User",
            "avatar": "https://example.com/avatar.png",
        }
    )
    controller.enrich_service = mock_enrich

    # Initialize queue and worker
    controller._enriched_seen.clear()
    controller._enrich_queue = asyncio.Queue()

    async def run_test():
        # Start render-budget flusher (applies _pending_enrichments batches)
        flusher_task = asyncio.create_task(controller._render_flusher())
        # Start worker task
        worker_task = asyncio.create_task(controller._drain_enrich_queue())

        # Simulate the live scan this progress belongs to: identity must
        # match or _apply_progress drops the tick as superseded. Saved and
        # restored so suite order cannot pollute other tests.
        prev_username = state.current_username
        state.current_username = "testuser"

        progress = SearchProgress(
            username="testuser",
            found=[
                SiteResult(
                    site_name="GitHub",
                    url_main="https://github.com",
                    url_user="https://github.com/testuser",
                    status="Claimed",
                    http_status="200",
                )
            ],
        )

        state.is_searching = True
        await controller._apply_progress(progress)

        # Allow queue to process
        await asyncio.sleep(0.3)
        state.is_searching = False
        await asyncio.sleep(0.3)

        if not worker_task.done():
            worker_task.cancel()

        # Allow the flusher window to land the batched enrichment in state
        await asyncio.sleep(0.9)
        flusher_task.cancel()

        # Verify enrichment was applied to state
        assert "https://github.com/testuser" in state.enrichments
        enrichment_data = state.enrichments["https://github.com/testuser"]
        state.current_username = prev_username
        assert enrichment_data.get("name") == "Enriched User"

    asyncio.run(run_test())


# ── Engine log noise ───────────────────────────────────────────────────


def test_set_engine_logs_mutes_maigret_but_keeps_our_own():
    """The engine's per-check chatter must not bury the rest of the terminal.

    It logs on every site-check of a 5,200-site scan, so the console and the
    in-app terminal become unreadable and real warnings are missed. Two
    things have to hold:

    * the mute targets the logger maigret actually writes to. It reports
      through whatever logger it is handed, and we hand it the
      `sherlock.engine` child — NOT `maigret` by name, which is why the
      first attempt at this mute did nothing at all (the records arrived
      under `services.sherlock_service` and looked like our own messages).
    * our own logger keeps talking, or errors would vanish with the noise.
    """
    from core.logger_handler import MemoryLogHandler, set_engine_logs

    handler = MemoryLogHandler(level=logging.DEBUG)
    root = logging.getLogger()
    restore = root.level
    root.addHandler(handler)
    last = set_engine_logs(True)
    saved_engine = logging.getLogger("sherlock.engine").level
    root.setLevel(logging.DEBUG)
    try:
        set_engine_logs(False)
        logging.getLogger("sherlock.engine").info("per-check chatter")
        logging.getLogger("sherlock.engine").debug("more chatter")
        assert handler.get_logs() == [], "engine log lines reached the terminal"

        logging.getLogger("services.sherlock_service").warning("a real warning")
        logs = handler.get_logs()
        assert any("a real warning" in line for line in logs), (
            "the mute swallowed non-engine warnings too"
        )

        set_engine_logs(True)
        logging.getLogger("sherlock.engine").info("verbose detail on purpose")
        assert any(
            "verbose detail on purpose" in line for line in handler.get_logs()
        ), "restoring verbosity did not let engine logs back through"
    finally:
        set_engine_logs(last)
        logging.getLogger("sherlock.engine").setLevel(saved_engine)
        root.removeHandler(handler)
        root.setLevel(restore)
        handler.clear_logs()


def test_maigret_reports_through_the_dedicated_engine_logger():
    """The engine must be handed `sherlock.engine`, not our module logger.

    Passing `logger` (this module's) made every site-check line arrive as
    `services.sherlock_service`, indistinguishable from our own messages and
    impossible to mute by name.
    """
    import inspect

    import services.sherlock_service as svc

    assert svc.engine_logger.name == "sherlock.engine"
    src = inspect.getsource(svc)
    assert "logger=engine_logger," in src, "maigret is still handed the module logger"
    assert "logger=logger," not in src, (
        "an engine call still passes the shared module logger"
    )


def test_engine_logs_switch_receives_a_bool_not_the_event():
    """The Engine Logs switch must unwrap `e.control.value`.

    Passing the handler straight to `ft.Switch(on_change=...)` stores the
    ControlEvent object as the state value. An event is always truthy, so
    `set_engine_logs(event)` resolved to verbose every time and the toggle
    could never be turned off — the exact bug introduced in 1ea9815 and
    caught by the adversarial review. Every other switch in SettingsScreen
    unwraps; this one must too.
    """
    from flet.components.component import Component, Renderer

    from screens.settings_screen import SettingsScreen
    from state.app_state import AppStateCtx
    from state.controller_ctx import ControllerMethods, ControllerMethodsCtx

    prev = state.log_engine_logs
    try:
        state.log_engine_logs = True  # start verbose, then switch OFF
        from core.logger_handler import set_engine_logs

        set_engine_logs(prev)
        methods = ControllerMethods()
        renderer = Renderer()
        root = renderer.render(
            lambda: ControllerMethodsCtx(
                methods, lambda: AppStateCtx(state, SettingsScreen)
            )
        )

        def walk(node, out):
            out.append(node)
            if isinstance(node, Component):
                node.before_update()
                b = getattr(node, "_b", None)
                if b is not None:
                    walk(b, out)
            elif isinstance(node, list):
                for i in node:
                    walk(i, out)
            else:
                for ch in getattr(node, "controls", None) or []:
                    walk(ch, out)
                c = getattr(node, "content", None)
                if c is not None and not isinstance(c, str):
                    walk(c, out)

        nodes = []
        walk(root, nodes)
        switches = [n for n in nodes if type(n).__name__ == "Switch"]
        assert switches, "SettingsScreen rendered no switches"

        class _Event:
            class Control:
                value = False

            control = Control()

        # The handler persists via spawn(), which needs a running loop.
        async def _toggle(event):
            for sw in switches:
                if getattr(sw, "value", None) is True:
                    sw.on_change(event)

        asyncio.run(_toggle(_Event()))

        assert state.log_engine_logs is False, (
            "the switch stored the event object (always truthy) instead of "
            "the new value — Engine Logs can never be turned off"
        )
    finally:
        state.log_engine_logs = prev
        set_engine_logs(prev)


def test_mute_covers_every_engine_noise_source():
    """One toggle must silence all three kinds of engine chatter.

    A field log showed three separate floods surviving the mute:

    * `sherlock.engine` WARNINGs — per-site 403/bot-wall/rate-limit
      outcomes, thousands per scan. Each is already rendered as a badge on
      its result card, so logging it again only buries everything else.
    * `httpx` INFO — one line per HTTP request, i.e. the email engine's
      entire traffic.
    * bare `logging.info(...)` from `socid_extractor`, which lands on the
      ROOT logger and so has no name to quiet (a root filter is the only
      lever).
    """
    from core.logger_handler import MemoryLogHandler, set_engine_logs

    handler = MemoryLogHandler(level=logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    saved = {name: logging.getLogger(name).level for name, _lv in _quiet_targets()}
    root_level = root.level
    root.setLevel(logging.DEBUG)
    set_engine_logs(True)
    try:
        set_engine_logs(False)
        logging.getLogger("sherlock.engine").warning("Access denied error: 403")
        logging.getLogger("httpx").info("HTTP Request: GET https://example.com")
        # Mimic socid_extractor's bare root-logger call.
        record = logging.LogRecord(
            name="root",
            level=logging.INFO,
            pathname="C:/x/site-packages/socid_extractor/main.py",
            lineno=80,
            msg="Telegram has been detected",
            args=(),
            exc_info=None,
        )
        root.handle(record)
        assert handler.get_logs() == [], (
            "engine noise still reached the terminal: " + repr(handler.get_logs())
        )

        # Our own messages and real errors must survive.
        logging.getLogger("services.sherlock_service").info("our own line")
        logging.getLogger("sherlock.engine").error("a real engine error")
        logged = handler.get_logs()
        assert any("our own line" in line for line in logged)
        assert any("a real engine error" in line for line in logged)

        set_engine_logs(True)
        logging.getLogger("sherlock.engine").warning("verbose 403 detail")
        assert any("verbose 403 detail" in line for line in handler.get_logs())
    finally:
        set_engine_logs(True)
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)
        root.setLevel(root_level)
        root.removeHandler(handler)
        handler.clear_logs()


def _quiet_targets():
    from core.logger_handler import _QUIET_WHEN_MUTED

    return _QUIET_WHEN_MUTED
