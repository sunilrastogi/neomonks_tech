"""
File lock management to prevent concurrent edits.
Two agents cannot hold locks on the same file simultaneously.
"""
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from apps.workflow.models import FileLock, FileLockStatus, WorkflowEvent, EventType
import logging

logger = logging.getLogger(__name__)


class LockManager:
    """Manages file locks to coordinate concurrent agent work."""

    LOCK_DURATION_HOURS = 24  # Default lock duration

    @staticmethod
    @transaction.atomic
    def acquire_lock(product_id: int, task_id: int, file_path: str, agent_name: str) -> FileLock:
        """
        Acquire a lock on a file for an agent.
        Raises exception if file is already locked by another agent.
        """
        # Check if file is already locked by someone else
        existing_lock = FileLock.objects.filter(
            product_id=product_id,
            file_path=file_path,
            status=FileLockStatus.ACTIVE
        ).first()

        if existing_lock and existing_lock.locked_by_agent != agent_name:
            raise LockConflictError(
                f"File {file_path} is already locked by {existing_lock.locked_by_agent}"
            )

        # Release old lock if this agent held one on the same file
        if existing_lock and existing_lock.locked_by_agent == agent_name:
            logger.info(f"Renewing lock for {agent_name} on {file_path}")
            existing_lock.expires_at = timezone.now() + timedelta(hours=LockManager.LOCK_DURATION_HOURS)
            existing_lock.save()
            return existing_lock

        # Create new lock
        lock = FileLock.objects.create(
            product_id=product_id,
            task_id=task_id,
            file_path=file_path,
            locked_by_agent=agent_name,
            status=FileLockStatus.ACTIVE,
            expires_at=timezone.now() + timedelta(hours=LockManager.LOCK_DURATION_HOURS)
        )

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.LOCK_ACQUIRED,
            entity_type="LOCK",
            entity_id=lock.id,
            payload_json={"file_path": file_path, "agent": agent_name}
        )

        logger.info(f"Lock acquired: {file_path} by {agent_name}")
        return lock

    @staticmethod
    @transaction.atomic
    def release_lock(lock_id: int) -> FileLock:
        """Release a file lock."""
        lock = FileLock.objects.get(id=lock_id)
        lock.status = FileLockStatus.RELEASED
        lock.released_at = timezone.now()
        lock.save()

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.LOCK_RELEASED,
            entity_type="LOCK",
            entity_id=lock.id,
            payload_json={"file_path": lock.file_path, "agent": lock.locked_by_agent}
        )

        logger.info(f"Lock released: {lock.file_path}")
        return lock

    @staticmethod
    @transaction.atomic
    def release_locks_for_task(task_id: int) -> int:
        """Release all locks held by a task."""
        locks = FileLock.objects.filter(
            task_id=task_id,
            status=FileLockStatus.ACTIVE
        )

        count = 0
        for lock in locks:
            LockManager.release_lock(lock.id)
            count += 1

        logger.info(f"Released {count} locks for task {task_id}")
        return count

    @staticmethod
    @transaction.atomic
    def release_locks_for_agent(product_id: int, agent_name: str) -> int:
        """Release all active locks held by an agent in a product."""
        locks = FileLock.objects.filter(
            product_id=product_id,
            locked_by_agent=agent_name,
            status=FileLockStatus.ACTIVE
        )

        count = 0
        for lock in locks:
            LockManager.release_lock(lock.id)
            count += 1

        logger.info(f"Released {count} locks for agent {agent_name}")
        return count

    @staticmethod
    @transaction.atomic
    def expire_stale_locks() -> int:
        """Find and expire locks that have exceeded their duration."""
        expired = 0
        stale_locks = FileLock.objects.filter(
            status=FileLockStatus.ACTIVE,
            expires_at__lt=timezone.now()
        )

        for lock in stale_locks:
            lock.status = FileLockStatus.EXPIRED
            lock.released_at = timezone.now()
            lock.save()

            # Record event
            WorkflowEvent.objects.create(
                event_type=EventType.LOCK_EXPIRED,
                entity_type="LOCK",
                entity_id=lock.id,
                payload_json={"file_path": lock.file_path, "agent": lock.locked_by_agent}
            )

            expired += 1

        if expired > 0:
            logger.info(f"Expired {expired} stale locks")

        return expired

    @staticmethod
    def get_active_locks(product_id: int) -> list[FileLock]:
        """Get all active locks for a product."""
        return FileLock.objects.filter(
            product_id=product_id,
            status=FileLockStatus.ACTIVE
        ).order_by("-locked_at")

    @staticmethod
    def is_file_locked(product_id: int, file_path: str, agent_name: str = None) -> bool:
        """Check if a file is locked (optionally by a specific agent)."""
        locks = FileLock.objects.filter(
            product_id=product_id,
            file_path=file_path,
            status=FileLockStatus.ACTIVE
        )

        if agent_name:
            locks = locks.filter(locked_by_agent=agent_name)
            return locks.exists()

        # Any agent has it locked
        return locks.exists()


class LockConflictError(Exception):
    """Raised when a lock cannot be acquired due to conflict."""
    pass
