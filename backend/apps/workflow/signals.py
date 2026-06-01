"""
Django signals — autonomous cascade triggers.

Every meaningful state change in the workflow emits a WorkflowEvent AND
automatically triggers the next step in the pipeline so no external polling
is required for state transitions.

Cascade rules:
  Requirement RECEIVED       → schedule planning (autonomous loop picks it up)
  ArchitectureArtifact APPROVED → dispatch ready tasks immediately
  Task MERGED                → dispatch downstream tasks immediately
  Task CHANGES_REQUESTED     → the loop re-queues it on next iteration
  FileLock save              → emit LOCK_ACQUIRED / LOCK_RELEASED / LOCK_EXPIRED
  PullRequestRecord save     → emit PR_CREATED / PR_* status events
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.workflow.models import (
    ArchitectureArtifact, ArchitectureStatus,
    FileLock, FileLockStatus,
    PullRequestRecord,
    Requirement, RequirementStatus,
    Task, TaskStatus,
    WorkflowEvent, EventType,
)

logger = logging.getLogger(__name__)


def _emit(event_type: str, entity_type: str, entity_id: int, payload: dict) -> None:
    try:
        WorkflowEvent.objects.create(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload,
        )
    except Exception:
        logger.exception("Failed to emit WorkflowEvent %s for %s %s",
                         event_type, entity_type, entity_id)


# ── Requirement ──────────────────────────────────────────────────────────────

_REQ_STATUS_EVENT = {
    RequirementStatus.UNDER_REVIEW: EventType.REQUIREMENT_REVIEWED,
    RequirementStatus.APPROVED:     EventType.REQUIREMENT_APPROVED,
    RequirementStatus.REJECTED:     EventType.REQUIREMENT_REJECTED,
}


@receiver(post_save, sender=Requirement)
def on_requirement_saved(sender, instance, created, **kwargs):
    if created:
        _emit(EventType.REQUIREMENT_CREATED, "REQUIREMENT", instance.id, {
            "title": instance.title,
            "product_id": instance.product_id,
            "priority": instance.priority,
            "status": instance.status,
        })
        logger.info("Requirement created: %d — %s", instance.id, instance.title)
    else:
        event_type = _REQ_STATUS_EVENT.get(instance.status)
        if event_type:
            _emit(event_type, "REQUIREMENT", instance.id, {
                "title": instance.title,
                "status": instance.status,
                "product_id": instance.product_id,
            })


# ── ArchitectureArtifact ─────────────────────────────────────────────────────

_ARCH_STATUS_EVENT = {
    ArchitectureStatus.SUBMITTED:         EventType.ARCHITECTURE_SUBMITTED,
    ArchitectureStatus.APPROVED:          EventType.ARCHITECTURE_APPROVED,
    ArchitectureStatus.CHANGES_REQUESTED: EventType.ARCHITECTURE_CHANGES_REQUESTED,
}


@receiver(post_save, sender=ArchitectureArtifact)
def on_architecture_saved(sender, instance, created, **kwargs):
    event_type = _ARCH_STATUS_EVENT.get(instance.status)
    if event_type:
        _emit(event_type, "ARCHITECTURE", instance.id, {
            "requirement_id": instance.requirement_id,
            "status": instance.status,
        })

    # Cascade: architecture approved → dispatch ready tasks immediately
    if instance.status == ArchitectureStatus.APPROVED:
        _dispatch_ready_async(instance.requirement.product_id)


def _dispatch_ready_async(product_id: int) -> None:
    """Dispatch in a background thread to avoid blocking the save."""
    import threading

    def _do():
        from django.db import close_old_connections
        close_old_connections()
        try:
            from apps.workflow.services.orchestrator import WorkflowOrchestrator
            dispatched = WorkflowOrchestrator.dispatch_ready_tasks(product_id)
            logger.info("Signal cascade: dispatched %d tasks for product %d",
                        len(dispatched), product_id)
        except Exception:
            logger.exception("Signal cascade dispatch failed for product %d", product_id)

    threading.Thread(target=_do, daemon=True, name=f"dispatch-{product_id}").start()


# ── Task ─────────────────────────────────────────────────────────────────────

_TASK_STATUS_EVENT = {
    TaskStatus.READY:             EventType.TASK_READY,
    TaskStatus.IN_PROGRESS:       EventType.TASK_IN_PROGRESS,
    TaskStatus.IN_REVIEW:         EventType.TASK_IN_REVIEW,
    TaskStatus.APPROVED:          EventType.TASK_APPROVED,
    TaskStatus.CHANGES_REQUESTED: EventType.TASK_CHANGES_REQUESTED,
    TaskStatus.MERGED:            EventType.TASK_MERGED,
}


@receiver(post_save, sender=Task)
def on_task_saved(sender, instance, created, **kwargs):
    if created:
        _emit(EventType.TASK_CREATED, "TASK", instance.id, {
            "title":        instance.title,
            "owner_role":   instance.owner_role,
            "status":       instance.status,
            "product_id":   instance.product_id,
        })
        logger.info("Task created: %d — %s", instance.id, instance.title)
    else:
        event_type = _TASK_STATUS_EVENT.get(instance.status)
        if event_type:
            _emit(event_type, "TASK", instance.id, {
                "title":          instance.title,
                "status":         instance.status,
                "assigned_agent": instance.assigned_agent,
                "product_id":     instance.product_id,
            })

    # Cascade: task MERGED → unblock downstream immediately
    if not created and instance.status == TaskStatus.MERGED:
        _dispatch_ready_async(instance.product_id)


# ── FileLock ─────────────────────────────────────────────────────────────────

@receiver(post_save, sender=FileLock)
def on_lock_saved(sender, instance, created, **kwargs):
    if created:
        _emit(EventType.LOCK_ACQUIRED, "LOCK", instance.id, {
            "file_path":       instance.file_path,
            "locked_by_agent": instance.locked_by_agent,
            "task_id":         instance.task_id,
            "product_id":      instance.product_id,
        })
        logger.info("Lock acquired: %s by %s", instance.file_path, instance.locked_by_agent)
    elif instance.status == FileLockStatus.RELEASED:
        _emit(EventType.LOCK_RELEASED, "LOCK", instance.id, {
            "file_path":       instance.file_path,
            "locked_by_agent": instance.locked_by_agent,
        })
    elif instance.status == FileLockStatus.EXPIRED:
        _emit(EventType.LOCK_EXPIRED, "LOCK", instance.id, {
            "file_path":       instance.file_path,
            "locked_by_agent": instance.locked_by_agent,
        })


# ── PullRequestRecord ─────────────────────────────────────────────────────────

_PR_STATUS_EVENT = {
    "OPEN":               EventType.PR_OPENED,
    "APPROVED":           EventType.PR_APPROVED,
    "CHANGES_REQUESTED":  EventType.PR_CHANGES_REQUESTED,
    "MERGED":             EventType.PR_MERGED,
    "CLOSED":             EventType.PR_CLOSED,
}


@receiver(post_save, sender=PullRequestRecord)
def on_pr_saved(sender, instance, created, **kwargs):
    if created:
        _emit(EventType.PR_CREATED, "PR", instance.id, {
            "task_id":     instance.task_id,
            "branch_name": instance.branch_name,
            "pr_url":      instance.pr_url,
        })
    else:
        event_type = _PR_STATUS_EVENT.get(instance.status)
        if event_type:
            _emit(event_type, "PR", instance.id, {
                "task_id": instance.task_id,
                "pr_url":  instance.pr_url,
                "status":  instance.status,
            })

    # Cascade: PR merged → complete task → dispatch downstream
    if instance.status == "MERGED":
        _on_pr_merged_async(instance.task_id)


def _on_pr_merged_async(task_id: int) -> None:
    import threading

    def _do():
        from django.db import close_old_connections
        close_old_connections()
        try:
            from apps.workflow.services.lock_manager import LockManager
            from apps.workflow.services.orchestrator import WorkflowOrchestrator
            task = Task.objects.get(id=task_id)
            if task.status != TaskStatus.MERGED:
                task.status = TaskStatus.MERGED
                task.save(update_fields=["status", "updated_at"])
            LockManager.release_locks_for_task(task_id)
            WorkflowOrchestrator.dispatch_ready_tasks(task.product_id)
        except Exception:
            logger.exception("PR merged cascade failed for task %d", task_id)

    threading.Thread(target=_do, daemon=True, name=f"pr-merge-{task_id}").start()
