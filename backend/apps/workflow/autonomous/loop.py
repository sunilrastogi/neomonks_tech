"""
Autonomous Loop
===============
Runs continuously as a background thread.

Each tick:
  1. PLANNING   — spawn a background thread per RECEIVED requirement (non-blocking).
  2. DISPATCH   — move dependency-free BLOCKED tasks → READY.
  3. EXECUTION  — spawn executor threads for READY, unassigned tasks.
  4. REWORK     — re-queue CHANGES_REQUESTED tasks.
  5. PR SYNC    — poll GitHub every SYNC_INTERVAL seconds.
  6. LOCK GC    — expire stale file locks.

Key design decisions:
  - Planning runs in its own thread so the loop NEVER blocks on an LLM call.
  - If a requirement is stuck at UNDER_REVIEW for > PLANNING_TIMEOUT seconds,
    it is reset to RECEIVED so the loop retries it.
  - A shared _loop_status dict is exposed via the /loop-status/ API so the
    dashboard can show exactly what is happening.
"""
from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Shared status dict — written by the loop, read by the API view
_loop_status: dict = {
    "running": False,
    "last_tick": None,
    "last_summary": {},
    "active_planners": [],   # list of req ids currently being planned
    "active_executors": [],  # list of task ids currently being executed
    "errors": [],            # last 10 errors
}
_status_lock = threading.Lock()

# Maximum time (seconds) a requirement may spend in UNDER_REVIEW before being reset
PLANNING_TIMEOUT = int(getattr(settings, "PLANNING_TIMEOUT", 600))  # 10 min default


def get_loop_status() -> dict:
    with _status_lock:
        return dict(_loop_status)


class AutonomousLoop:
    POLL_INTERVAL: float = float(getattr(settings, "LOOP_POLL_INTERVAL", 10))
    SYNC_INTERVAL: float = float(getattr(settings, "LOOP_PR_SYNC_INTERVAL", 3600))

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._last_sync: float = 0.0
        self._thread: threading.Thread | None = None
        self._planning_threads: dict[int, threading.Thread] = {}  # req_id → thread

    # ── public API ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("Autonomous loop already running")
            return
        self._stop_event.clear()
        with _status_lock:
            _loop_status["running"] = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="autonomous-loop")
        self._thread.start()
        logger.info("Autonomous loop started (poll=%ss)", self.POLL_INTERVAL)

    def stop(self) -> None:
        self._stop_event.set()
        with _status_lock:
            _loop_status["running"] = False
        if self._thread:
            self._thread.join(timeout=15)
        logger.info("Autonomous loop stopped")

    def run_once(self, product_id: int | None = None) -> dict:
        """Run one iteration synchronously (used by management command and API)."""
        with _status_lock:
            _loop_status["running"] = True
        try:
            return self._iterate(product_id=product_id, force_sync=False)
        finally:
            with _status_lock:
                _loop_status["running"] = False

    # ── internal ──────────────────────────────────────────────────────────

    def _run(self) -> None:
        from django.db import close_old_connections
        close_old_connections()
        while not self._stop_event.is_set():
            try:
                close_old_connections()
                self._iterate()
            except Exception as exc:
                logger.exception("Loop iteration failed: %s", exc)
                with _status_lock:
                    _loop_status["errors"].append(
                        {"ts": time.time(), "msg": str(exc)[:200]}
                    )
                    _loop_status["errors"] = _loop_status["errors"][-10:]
            self._stop_event.wait(self.POLL_INTERVAL)

    def _iterate(self, product_id: int | None = None, force_sync: bool = False) -> dict:  # noqa: C901
        from apps.workflow.autonomous.executor import AutonomousExecutor
        from apps.workflow.autonomous.planner import AutonomousPlanner
        from apps.workflow.autonomous.pr_sync import PRSyncService
        from apps.workflow.models import (
            Product, Requirement, RequirementStatus, Task, TaskStatus,
        )
        from apps.workflow.services.lock_manager import LockManager
        from apps.workflow.services.orchestrator import WorkflowOrchestrator

        summary: dict = {
            "planned": 0, "dispatched": 0,
            "executed": 0, "synced": 0, "locks_expired": 0,
        }

        product_filter = {"id": product_id} if product_id else {}
        active_products = list(Product.objects.filter(status="ACTIVE", **product_filter))
        product_ids = [p.id for p in active_products]

        if not product_ids:
            logger.warning("Loop: no active products found (product_id=%s)", product_id)

        # ── 0. STUCK RECOVERY ────────────────────────────────────────────
        # Reset requirements stuck in UNDER_REVIEW for too long back to RECEIVED
        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(seconds=PLANNING_TIMEOUT)
        stuck = Requirement.objects.filter(
            status=RequirementStatus.UNDER_REVIEW,
            updated_at__lt=cutoff,
            product_id__in=product_ids,
        )
        for s in stuck:
            logger.warning("Loop: requirement %d stuck in UNDER_REVIEW for >%ds — resetting", s.id, PLANNING_TIMEOUT)
            s.status = RequirementStatus.RECEIVED
            s.save(update_fields=["status", "updated_at"])

        # ── 1. PLANNING (non-blocking threads) ───────────────────────────
        pending_reqs = Requirement.objects.filter(
            status=RequirementStatus.RECEIVED,
            product_id__in=product_ids,
        )
        for req in pending_reqs:
            if req.id in self._planning_threads and self._planning_threads[req.id].is_alive():
                logger.debug("Loop: planner already running for req %d", req.id)
                continue
            logger.info("Loop: spawning planner for req %d — %s", req.id, req.title)
            t = threading.Thread(
                target=self._run_planner,
                args=(req.id, AutonomousPlanner()),
                daemon=True,
                name=f"planner-{req.id}",
            )
            self._planning_threads[req.id] = t
            t.start()
            summary["planned"] += 1

        # Update status
        with _status_lock:
            _loop_status["active_planners"] = [
                rid for rid, t in self._planning_threads.items() if t.is_alive()
            ]

        # ── 2. DISPATCH ──────────────────────────────────────────────────
        for pid in product_ids:
            dispatched = WorkflowOrchestrator.dispatch_ready_tasks(pid)
            summary["dispatched"] += len(dispatched)

        # ── 3. EXECUTION ─────────────────────────────────────────────────
        executor = AutonomousExecutor()
        ready_tasks = Task.objects.filter(
            status=TaskStatus.READY,
            assigned_agent__isnull=True,
            product_id__in=product_ids,
        ).order_by("order_index", "id")

        for task in ready_tasks:
            logger.info("Loop: executing task %d — %s", task.id, task.title)
            executor.execute_in_background(task.id)
            summary["executed"] += 1

        # ── 4. REWORK ────────────────────────────────────────────────────
        rework_tasks = Task.objects.filter(
            status=TaskStatus.CHANGES_REQUESTED,
            product_id__in=product_ids,
        ).order_by("id")
        for task in rework_tasks:
            logger.info("Loop: re-executing task %d (changes requested)", task.id)
            task.status = TaskStatus.READY
            task.assigned_agent = None
            task.save(update_fields=["status", "assigned_agent", "updated_at"])
            executor.execute_in_background(task.id)
            summary["executed"] += 1

        # ── 5. PR SYNC ───────────────────────────────────────────────────
        now = time.monotonic()
        if force_sync or (now - self._last_sync) >= self.SYNC_INTERVAL:
            sync_result = PRSyncService().sync_all()
            summary["synced"] = sync_result.get("synced", 0)
            self._last_sync = now

        # ── 6. LOCK GC ───────────────────────────────────────────────────
        summary["locks_expired"] = LockManager.expire_stale_locks()

        with _status_lock:
            _loop_status["last_tick"] = time.time()
            _loop_status["last_summary"] = summary

        logger.info("Loop tick done: %s", summary)
        return summary

    def _run_planner(self, req_id: int, planner) -> None:
        from django.db import close_old_connections
        close_old_connections()
        try:
            planner.run(req_id)
        except Exception as exc:
            logger.exception("Planner failed for req %d: %s", req_id, exc)
            with _status_lock:
                _loop_status["errors"].append(
                    {"ts": time.time(), "msg": f"Planner req {req_id}: {str(exc)[:150]}"}
                )
                _loop_status["errors"] = _loop_status["errors"][-10:]
