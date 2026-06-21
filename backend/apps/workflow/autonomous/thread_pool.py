"""
Shared thread pool for all autonomous background work.

One global ThreadPoolExecutor caps total OS threads at MAX_WORKERS.
All agent execution, planning, and dispatch go through this pool — no more
unbounded Thread() spawning that exhausts the system.

Tenancy: work is almost always submitted from within a tenant request or a
per-tenant loop tick. A pool worker runs on a *different* thread with a fresh
DB connection whose schema would default to ``public`` (which has none of the
business tables). So we capture the active schema at submit time and re-enter
it inside the worker via ``schema_context`` — otherwise background agents would
read/write the wrong (or an empty) schema.
"""
from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor

from django.conf import settings
from django.db import connection
from django_tenants.utils import schema_context

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
    """Submit work to the shared pool, preserving the caller's tenant schema.

    Returns a Future (fire-and-forget is fine).
    """
    schema = getattr(connection, "schema_name", None)

    def _runner():
        from django.db import close_old_connections
        close_old_connections()
        if schema:
            with schema_context(schema):
                return fn(*args, **kwargs)
        return fn(*args, **kwargs)

    return get_pool().submit(_runner)
