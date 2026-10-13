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
    """Maigret's per-check chatter must not bury the rest of the terminal.

    It logs on every site-check of a 5,200-site scan, so the console and the
    in-app terminal become unreadable and real warnings are missed. The mute
    has to be scoped to that logger — silencing everything would hide errors.
    """
    from core.logger_handler import MemoryLogHandler, set_engine_logs

    handler = MemoryLogHandler(level=logging.DEBUG)
    root = logging.getLogger()
    restore = root.level
    root.addHandler(handler)
    last = set_engine_logs(True)
    saved_mig = logging.getLogger("maigret").level
    root.setLevel(logging.DEBUG)
    try:
        set_engine_logs(False)
        logging.getLogger("maigret").info("per-check chatter")
        logging.getLogger("maigret").debug("more chatter")
        assert handler.get_logs() == [], "maigret log lines reached the terminal"

        logging.getLogger("services.sherlock_service").warning("a real warning")
        logs = handler.get_logs()
        assert any("a real warning" in line for line in logs), (
            "the mute swallowed non-engine warnings too"
        )

        set_engine_logs(True)
        logging.getLogger("maigret").info("verbose detail on purpose")
        assert any(
            "verbose detail on purpose" in line for line in handler.get_logs()
        ), "restoring verbosity did not let engine logs back through"
    finally:
        set_engine_logs(last)
        logging.getLogger("maigret").setLevel(saved_mig)
        root.removeHandler(handler)
        root.setLevel(restore)
        handler.clear_logs()
