"""
Shared thread pool for all autonomous background work.

One global ThreadPoolExecutor caps total OS threads at MAX_WORKERS.
All agent execution, planning, and dispatch go through this pool — no more
unbounded Thread() spawning that exhausts the system.
"""
from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor

from django.conf import settings

logger = logging.getLogger(__name__)

MAX_WORKERS: int = int(getattr(settings, "AUTONOMOUS_MAX_WORKERS", 4))

_pool: ThreadPoolExecutor | None = None


def get_pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None or _pool._shutdown:
        _pool = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="neomonks")
        logger.info("Thread pool created (max_workers=%d)", MAX_WORKERS)
    return _pool


def submit(fn, *args, **kwargs) -> Future:
    """Submit work to the shared pool. Returns a Future (fire-and-forget is fine)."""
    return get_pool().submit(fn, *args, **kwargs)
