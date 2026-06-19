"""
Main orchestrator service for workflow state transitions.
Product Owner uses this to coordinate requirement -> design -> tasks -> completion.
"""
from django.db import transaction
from django.utils import timezone
from apps.workflow.models import (
    Product, Requirement, ArchitectureArtifact, Task, TaskDependency,
    TaskStatus, RequirementStatus, ArchitectureStatus, WorkflowEvent, EventType
)
import logging

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Orchestrates the full workflow: requirements -> architecture -> tasks -> completion."""

    @staticmethod
    @transaction.atomic
    def create_requirement(product_id: int, title: str, summary: str, source_document: str = "", priority: str = "MEDIUM", created_by: str = "system") -> Requirement:
        """Create a new requirement for a product."""
        product = Product.objects.get(id=product_id)
        requirement = Requirement.objects.create(
            product=product,
            title=title,
            summary=summary,
            source_document=source_document,
            priority=priority,
            created_by=created_by,
            status=RequirementStatus.RECEIVED
        )

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.REQUIREMENT_CREATED,
            entity_type="REQUIREMENT",
            entity_id=requirement.id,
            payload_json={"title": title, "priority": priority}
        )

        logger.info(f"Requirement created: {requirement.id} - {title}")
        return requirement

    @staticmethod
    @transaction.atomic
    def submit_architecture(requirement_id: int, design_json: dict, rationale: str) -> ArchitectureArtifact:
        """Submit an architecture artifact for a requirement (from Solution Architect)."""
        requirement = Requirement.objects.get(id=requirement_id)

        # Get or create architecture
        architecture, created = ArchitectureArtifact.objects.get_or_create(
            requirement=requirement,
            defaults={"design_json": design_json, "rationale": rationale, "status": ArchitectureStatus.SUBMITTED}
        )

        if not created:
            # Update existing architecture
            architecture.design_json = design_json
            architecture.rationale = rationale
            architecture.status = ArchitectureStatus.SUBMITTED
            architecture.save()

        # Update requirement status
        requirement.status = RequirementStatus.UNDER_REVIEW
        requirement.save()

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.ARCHITECTURE_SUBMITTED,
            entity_type="ARCHITECTURE",
            entity_id=architecture.id,
            payload_json={"requirement_id": requirement_id}
        )

        logger.info(f"Architecture submitted for requirement: {requirement_id}")
        return architecture

    @staticmethod
    @transaction.atomic
    def approve_architecture(architecture_id: int, approved_by: str) -> ArchitectureArtifact:
        """Human approval of architecture design."""
        architecture = ArchitectureArtifact.objects.get(id=architecture_id)
        architecture.status = ArchitectureStatus.APPROVED
        architecture.approved_by = approved_by
        architecture.approved_at = timezone.now()
        architecture.save()

        # Update requirement status
        requirement = architecture.requirement
        requirement.status = RequirementStatus.APPROVED
        requirement.save()

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.ARCHITECTURE_APPROVED,
            entity_type="ARCHITECTURE",
            entity_id=architecture.id,
            payload_json={"approved_by": approved_by}
        )

        logger.info(f"Architecture approved: {architecture_id} by {approved_by}")
        return architecture

    @staticmethod
    @transaction.atomic
    def reject_architecture(requirement_id: int, reason: str = "") -> Requirement:
        """Reject architecture and require resubmission."""
        requirement = Requirement.objects.get(id=requirement_id)
        requirement.status = RequirementStatus.REJECTED
        requirement.save()

        # Reset architecture to draft if exists
        if hasattr(requirement, 'architecture'):
            architecture = requirement.architecture
            architecture.status = ArchitectureStatus.DRAFT
            architecture.save()

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.ARCHITECTURE_CHANGES_REQUESTED,
            entity_type="REQUIREMENT",
            entity_id=requirement.id,
            payload_json={"reason": reason}
        )

        logger.info(f"Architecture rejected for requirement: {requirement_id}")
        return requirement

    @staticmethod
    @transaction.atomic
    def create_task(product_id: int, requirement_id: int, title: str, description: str, owner_role: str, estimate: str = "") -> Task:
        """Create a task from approved architecture (usually called by PO)."""
        product = Product.objects.get(id=product_id)
        requirement = Requirement.objects.get(id=requirement_id)

        # Get the next order index
        max_order = Task.objects.filter(product=product).aggregate(models.Max('order_index'))['order_index__max'] or 0

        task = Task.objects.create(
            product=product,
            requirement=requirement,
            architecture=requirement.architecture if hasattr(requirement, 'architecture') else None,
            title=title,
            description=description,
            owner_role=owner_role,
            status=TaskStatus.BLOCKED,  # Start blocked until dependencies are resolved
            estimate=estimate,
            order_index=max_order + 1
        )

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.TASK_CREATED,
            entity_type="TASK",
            entity_id=task.id,
            payload_json={"title": title, "owner_role": owner_role}
        )

        logger.info(f"Task created: {task.id} - {title} (role: {owner_role})")
        return task

    @staticmethod
    @transaction.atomic
    def add_task_dependency(task_id: int, depends_on_task_id: int) -> TaskDependency:
        """Mark one task as depending on another."""
        task = Task.objects.get(id=task_id)
        depends_on_task = Task.objects.get(id=depends_on_task_id)

        dependency, created = TaskDependency.objects.get_or_create(
            task=task,
            depends_on_task=depends_on_task
        )

        # Ensure dependent task is blocked
        if task.status != TaskStatus.BLOCKED:
            task.status = TaskStatus.BLOCKED
            task.save()

        if created:
            logger.info(f"Dependency added: {task.title} depends on {depends_on_task.title}")

        return dependency

    @staticmethod
    def get_ready_tasks(product_id: int) -> list[Task]:
        """Get all tasks in a product that have no unmet dependencies."""
        product = Product.objects.get(id=product_id)
        all_tasks = Task.objects.filter(product=product, status=TaskStatus.BLOCKED)

        ready_tasks = []
        for task in all_tasks:
            # Check if all dependencies are completed
            pending_deps = task.dependencies.filter(
                depends_on_task__status__in=[TaskStatus.BLOCKED, TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW, TaskStatus.CHANGES_REQUESTED]
            ).count()

            if pending_deps == 0:
                ready_tasks.append(task)

        return ready_tasks

    @staticmethod
    @transaction.atomic
    def dispatch_ready_tasks(product_id: int) -> list[Task]:
        """Move all ready tasks from BLOCKED to READY state."""
        ready_tasks = WorkflowOrchestrator.get_ready_tasks(product_id)
        dispatched = []

        for task in ready_tasks:
            task.status = TaskStatus.READY
            task.save()

            # Record event
            WorkflowEvent.objects.create(
                event_type=EventType.TASK_READY,
                entity_type="TASK",
                entity_id=task.id,
                payload_json={"title": task.title}
            )

            dispatched.append(task)
            logger.info(f"Task dispatched to READY: {task.id} - {task.title}")

        return dispatched

    @staticmethod
    @transaction.atomic
    def complete_task(task_id: int) -> Task:
        """Mark task as completed, triggering downstream unlocks."""
        from apps.workflow.services.lock_manager import LockManager

        task = Task.objects.get(id=task_id)
        task.status = TaskStatus.MERGED
        task.save()

        # Release all locks held by this task
        LockManager.release_locks_for_task(task.id)

        # Record event
        WorkflowEvent.objects.create(
            event_type=EventType.TASK_MERGED,
            entity_type="TASK",
            entity_id=task.id,
            payload_json={"title": task.title}
        )

        logger.info(f"Task completed: {task.id} - {task.title}")
        return task


from django.db import models
