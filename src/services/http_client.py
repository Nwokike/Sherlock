"""Shared pooled httpx client — proxy-aware HTTP for app callers.

Replaces throwaway per-call clients (update check, avatar downloads):
one pooled client with keepalive, rebuilt automatically when the
Settings proxy changes (proxy is read live from core.state on access,
so socks5/http proxies apply to every httpx path — socks requires the
installed httpx[socks]/socksio extra).

No silent failures: swap/close problems are logged at WARNING.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_client_proxy: str | None = None


def get_client() -> httpx.AsyncClient:
    """Return the shared client, rebuilding it when state.proxy_url changes."""
    global _client, _client_proxy
    from core.state import state

    proxy = (getattr(state, "proxy_url", "") or "").strip() or None
    if _client is not None and proxy == _client_proxy:
        return _client
    if _client is not None:
        _drain(_client)
    limits = httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    )
    _client = httpx.AsyncClient(limits=limits, proxy=proxy, follow_redirects=True)
    _client_proxy = proxy
    logger.info("Shared httpx client (re)built (proxy=%s)", proxy or "direct")
    return _client


def _drain(old: httpx.AsyncClient) -> None:
    """Close a replaced client without blocking; visible on failure."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("Shared httpx client swapped with no running loop — relying on GC")
        return
    loop.create_task(_aclose(old))


async def _aclose(client: httpx.AsyncClient) -> None:
    try:
        await client.aclose()
    except Exception as exc:
        logger.warning("Shared httpx client close failed: %s", exc)


async def close_client() -> None:
    """Close the pooled client (wired into page on_close)."""
    global _client, _client_proxy
    old, _client, _client_proxy = _client, None, None
    if old is not None:
        await _aclose(old)
