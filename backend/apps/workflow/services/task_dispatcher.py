"""
Task dispatcher for assigning work to agents.
Validates lock ownership and prevents conflicts.
"""
from django.db import transaction
from django.utils import timezone
from apps.workflow.models import Task, TaskStatus, AgentProfile, WorkflowEvent, EventType
from apps.workflow.services.lock_manager import LockManager, LockConflictError
import logging

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """Coordinates task assignment and agent execution."""

    @staticmethod
    def get_agent_profile(agent_name: str) -> AgentProfile:
        """Get profile for an agent by display name."""
        return AgentProfile.objects.get(display_name=agent_name)

    @staticmethod
    @transaction.atomic
    def assign_task(task_id: int, agent_name: str, file_paths: list[str] = None) -> Task:
        """
        Assign a task to an agent and acquire locks on relevant files.

        Args:
            task_id: ID of the task
            agent_name: Display name of the agent (e.g., "Priya Nair")
            file_paths: List of files the task will modify

        Returns:
            Updated Task object

        Raises:
            LockConflictError if any file is already locked
        """
        task = Task.objects.get(id=task_id)

        # Verify agent exists and has correct role
        agent = TaskDispatcher.get_agent_profile(agent_name)
        if agent.role != task.owner_role:
            raise ValueError(
                f"Agent {agent_name} has role {agent.role}, but task requires {task.owner_role}"
            )

        # Task must be in READY or BLOCKED state to be assigned
        if task.status not in [TaskStatus.READY, TaskStatus.BLOCKED]:
            raise ValueError(f"Cannot assign task in {task.status} status")

        # Acquire locks on files if provided
        if file_paths:
            for file_path in file_paths:
                try:
                    LockManager.acquire_lock(
                        product_id=task.product_id,
                        task_id=task_id,
                        file_path=file_path,
                        agent_name=agent_name
                    )
                except LockConflictError as e:
                    logger.warning(f"Lock conflict when assigning task: {e}")
                    raise

        # Update task
        task.assigned_agent = agent_name
        task.status = TaskStatus.IN_PROGRESS
        task.save()

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.TASK_ASSIGNED,
            entity_type="TASK",
            entity_id=task.id,
            payload_json={
                "agent": agent_name,
                "role": agent.role,
                "files": file_paths or []
            }
        )

        logger.info(f"Task assigned: {task.id} to {agent_name}")
        return task

    @staticmethod
    @transaction.atomic
    def mark_task_in_progress(task_id: int) -> Task:
        """Move task to IN_PROGRESS status."""
        task = Task.objects.get(id=task_id)
        task.status = TaskStatus.IN_PROGRESS
        task.save()

        WorkflowEvent.objects.create(
            event_type=EventType.TASK_IN_PROGRESS,
            entity_type="TASK",
            entity_id=task.id,
            payload_json={"title": task.title}
        )

        logger.info(f"Task marked in progress: {task.id}")
        return task

    @staticmethod
    @transaction.atomic
    def mark_task_in_review(task_id: int, pr_url: str = None) -> Task:
        """Move task to IN_REVIEW status (work submitted for review)."""
        task = Task.objects.get(id=task_id)
        task.status = TaskStatus.IN_REVIEW
        if pr_url:
            task.pr_url = pr_url
        task.save()

        WorkflowEvent.objects.create(
            event_type=EventType.TASK_IN_REVIEW,
            entity_type="TASK",
            entity_id=task.id,
            payload_json={"pr_url": pr_url}
        )

        logger.info(f"Task moved to review: {task.id}")
        return task

    @staticmethod
    @transaction.atomic
    def request_changes_on_task(task_id: int, reason: str = "") -> Task:
        """Move task back to IN_PROGRESS with requested changes."""
        task = Task.objects.get(id=task_id)
        task.status = TaskStatus.CHANGES_REQUESTED
        task.save()

        WorkflowEvent.objects.create(
            event_type=EventType.TASK_CHANGES_REQUESTED,
            entity_type="TASK",
            entity_id=task.id,
            payload_json={"reason": reason}
        )

        logger.info(f"Changes requested on task: {task.id}")
        return task

    @staticmethod
    def get_tasks_for_agent(agent_name: str) -> list[Task]:
        """Get all tasks assigned to an agent."""
        return Task.objects.filter(assigned_agent=agent_name).order_by("-updated_at")

    @staticmethod
    def get_ready_tasks_for_role(role: str) -> list[Task]:
        """Get all READY tasks for a specific role."""
        return Task.objects.filter(
            owner_role=role,
            status=TaskStatus.READY,
            assigned_agent__isnull=True
        ).order_by("order_index")

    @staticmethod
    def get_task_locks(task_id: int) -> list:
        """Get all file locks held by a task."""
        from apps.workflow.models import FileLock, FileLockStatus
        return FileLock.objects.filter(
            task_id=task_id,
            status=FileLockStatus.ACTIVE
        )

    @staticmethod
    def get_agent_locks(product_id: int, agent_name: str) -> list:
        """Get all file locks held by an agent in a product."""
        return LockManager.get_active_locks(product_id) \
            .filter(locked_by_agent=agent_name)
