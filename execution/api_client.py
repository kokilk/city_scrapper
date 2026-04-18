"""
Shared async HTTP client for the stakeholder intelligence pipeline.

Provides:
- Rate-limited aiohttp session with per-API semaphores
- Exponential backoff with jitter on 429/502/503
- Respects Retry-After response header
- Structured request logging to .tmp/api_calls.log
- Synchronous convenience wrapper for scripts that don't use asyncio

Usage:
    async with api_session() as session:
        data = await get_json(session, "https://api.example.com/endpoint",
                              headers={"X-API-Key": "..."}, sem=SHOVELS_SEM)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_PATH = Path(__file__).parent.parent / ".tmp" / "api_calls.log"


def _setup_logger() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("api_client")
    if not logger.handlers:
        handler = logging.FileHandler(LOG_PATH)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


_logger = _setup_logger()


def _log(method: str, url: str, status: int, latency_ms: float, note: str = "") -> None:
    _logger.info(f"{method} {url} → {status} ({latency_ms:.0f}ms) {note}".strip())


# ── Per-API semaphores (max concurrent requests) ──────────────────────────────

SHOVELS_SEM = asyncio.Semaphore(10)
ATTOM_SEM = asyncio.Semaphore(5)
OPENCORP_SEM = asyncio.Semaphore(3)       # free tier is strict
APOLLO_SEM = asyncio.Semaphore(3)
HUNTER_SEM = asyncio.Semaphore(5)
SMARTY_SEM = asyncio.Semaphore(10)
ASSESSOR_SEM = asyncio.Semaphore(5)

# ── Retry config ──────────────────────────────────────────────────────────────

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BASE_BACKOFF_S = 1.0
MAX_BACKOFF_S = 60.0


@asynccontextmanager
async def api_session():
    """Async context manager yielding a shared aiohttp.ClientSession."""
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        yield session


async def get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    sem: asyncio.Semaphore | None = None,
) -> dict[str, Any] | list[Any]:
    """
    Perform a GET request with retry/backoff. Returns parsed JSON.
    Raises aiohttp.ClientResponseError for permanent errors (4xx except 429).
    """
    _sem = sem or asyncio.Semaphore(10)
    async with _sem:
        for attempt in range(MAX_RETRIES):
            t0 = time.monotonic()
            try:
                async with session.get(url, headers=headers, params=params) as resp:
                    latency = (time.monotonic() - t0) * 1000
                    _log("GET", url, resp.status, latency)

                    if resp.status == 200:
                        return await resp.json(content_type=None)

                    if resp.status in RETRYABLE_STATUSES:
                        wait = _retry_wait(resp, attempt)
                        _logger.warning(f"Retryable {resp.status} on {url}, waiting {wait:.1f}s (attempt {attempt+1})")
                        await asyncio.sleep(wait)
                        continue

                    # Non-retryable 4xx — raise immediately
                    resp.raise_for_status()

            except aiohttp.ClientResponseError:
                raise
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as exc:
                wait = _retry_wait(None, attempt)
                _logger.warning(f"Network error on {url}: {exc}, retrying in {wait:.1f}s")
                await asyncio.sleep(wait)

        raise RuntimeError(f"Exhausted {MAX_RETRIES} retries for GET {url}")


async def post_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    sem: asyncio.Semaphore | None = None,
) -> dict[str, Any] | list[Any]:
    """
    Perform a POST request with retry/backoff. Returns parsed JSON.
    """
    _sem = sem or asyncio.Semaphore(10)
    async with _sem:
        for attempt in range(MAX_RETRIES):
            t0 = time.monotonic()
            try:
                async with session.post(url, headers=headers, json=payload) as resp:
                    latency = (time.monotonic() - t0) * 1000
                    _log("POST", url, resp.status, latency)

                    if resp.status in (200, 201):
                        return await resp.json(content_type=None)

                    if resp.status in RETRYABLE_STATUSES:
                        wait = _retry_wait(resp, attempt)
                        _logger.warning(f"Retryable {resp.status} on {url}, waiting {wait:.1f}s (attempt {attempt+1})")
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()

            except aiohttp.ClientResponseError:
                raise
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as exc:
                wait = _retry_wait(None, attempt)
                _logger.warning(f"Network error on {url}: {exc}, retrying in {wait:.1f}s")
                await asyncio.sleep(wait)

        raise RuntimeError(f"Exhausted {MAX_RETRIES} retries for POST {url}")


def _retry_wait(resp: aiohttp.ClientResponse | None, attempt: int) -> float:
    """Exponential backoff with jitter. Respects Retry-After header."""
    import random
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    backoff = min(BASE_BACKOFF_S * (2 ** attempt), MAX_BACKOFF_S)
    jitter = random.uniform(0, backoff * 0.25)
    return backoff + jitter


# ── Synchronous convenience wrapper ──────────────────────────────────────────

def sync_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    """
    Blocking wrapper around get_json for scripts that don't manage their own event loop.
    Creates a fresh event loop (safe in subprocess / CLI context).
    """
    import requests as _requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=BASE_BACKOFF_S,
        status_forcelist=list(RETRYABLE_STATUSES),
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = _requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    t0 = time.monotonic()
    resp = session.get(url, headers=headers, params=params, timeout=30)
    latency = (time.monotonic() - t0) * 1000
    _log("GET(sync)", url, resp.status_code, latency)
    resp.raise_for_status()
    return resp.json()


def sync_post_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    """Blocking wrapper around post_json."""
    import requests as _requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=BASE_BACKOFF_S,
        status_forcelist=list(RETRYABLE_STATUSES),
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = _requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    t0 = time.monotonic()
    resp = session.post(url, headers=headers, json=payload, timeout=30)
    latency = (time.monotonic() - t0) * 1000
    _log("POST(sync)", url, resp.status_code, latency)
    resp.raise_for_status()
    return resp.json()
