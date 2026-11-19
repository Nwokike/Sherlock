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

from core.tasks import spawn

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_client_proxy: str | None = None
_client_retries: int | None = None


def _get_retries() -> int:
    from core.state import state

    try:
        retries = int(getattr(state, "retries", 0) or 0)
    except TypeError, ValueError:
        retries = 0
    return max(0, min(3, retries))


def get_client() -> httpx.AsyncClient:
    """Return the shared client, rebuilding when proxy/retries change."""
    global _client, _client_proxy, _client_retries
    from core.state import state

    proxy = (getattr(state, "proxy_url", "") or "").strip() or None
    retries = _get_retries()
    if _client is not None and proxy == _client_proxy and retries == _client_retries:
        return _client
    if _client is not None:
        _drain(_client)
    limits = httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    )
    timeout = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)
    # NOTE: do NOT wire as transport=+proxy= combo — when transport= is
    # given, httpx builds proxy mounts internally WITHOUT retries, so the
    # proxy leg would silently lose retry behavior. Both legs explicit.
    direct = httpx.AsyncHTTPTransport(retries=retries, limits=limits, http2=True)
    if proxy:
        proxy_transport = httpx.AsyncHTTPTransport(
            retries=retries, limits=limits, http2=True, proxy=proxy
        )
        _client = httpx.AsyncClient(
            transport=direct,
            mounts={"all://": proxy_transport},
            timeout=timeout,
            http2=True,
            follow_redirects=True,
        )
    else:
        _client = httpx.AsyncClient(
            transport=direct,
            timeout=timeout,
            http2=True,
            limits=limits,
            follow_redirects=True,
        )
    _client_proxy = proxy
    _client_retries = retries
    logger.info(
        "Shared httpx client (re)built (proxy=%s, retries=%d)",
        proxy or "direct",
        retries,
    )
    return _client


def _drain(old: httpx.AsyncClient) -> None:
    """Close a replaced client without blocking; visible on failure."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "Shared httpx client swapped with no running loop — relying on GC"
        )
        return
    spawn(_aclose(old), name="httpx-aclose")


async def _aclose(client: httpx.AsyncClient) -> None:
    try:
        await client.aclose()
    except Exception as exc:
        logger.warning("Shared httpx client close failed: %s", exc)


async def close_client() -> None:
    """Close the pooled client (wired into page on_close)."""
    global _client, _client_proxy, _client_retries
    old, _client, _client_proxy, _client_retries = _client, None, None, None
    if old is not None:
        await _aclose(old)
