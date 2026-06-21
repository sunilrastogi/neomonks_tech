"""REST API views for workflow control plane."""
import threading

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Q

from apps.workflow.models import (
    Product, Requirement, ArchitectureArtifact, Task, TaskDependency,
    FileLock, AgentProfile, PullRequestRecord, WorkflowEvent, TaskStatus
)
from apps.workflow.api.serializers import (
    ProductSerializer, RequirementSerializer, ArchitectureArtifactSerializer,
    TaskSerializer, TaskDependencySerializer, FileLockSerializer,
    AgentProfileSerializer, PullRequestRecordSerializer, WorkflowEventSerializer,
    TaskGraphSerializer
)
from apps.workflow.services.orchestrator import WorkflowOrchestrator
from apps.workflow.services.task_dispatcher import TaskDispatcher
from apps.workflow.services.lock_manager import LockManager, LockConflictError


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 1000


class ProductViewSet(viewsets.ModelViewSet):
    """Product management endpoints."""
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = StandardResultsSetPagination

    def perform_create(self, serializer):
        """Create the Product record, then scaffold the product folder in the background."""
        product = serializer.save()
        self._scaffold_async(product.name, product.slug)

    def perform_update(self, serializer):
        serializer.save()

    @staticmethod
    def _scaffold_async(product_name: str, product_slug: str) -> None:
        from apps.workflow.autonomous.thread_pool import submit

        def _run():
            from django.db import close_old_connections
            close_old_connections()
            from apps.workflow.autonomous.scaffolder import ProductScaffolder
            try:
                ProductScaffolder().scaffold(product_name, product_slug)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Scaffolding failed for product '%s'", product_slug
                )
        submit(_run)

    @action(detail=True, methods=['get'])
    def state(self, request, pk=None):
        """GET /api/v1/workflow/products/{id}/state
        Return product state with task graph and active locks."""
        product = self.get_object()

        tasks = Task.objects.filter(product=product)
        dependencies = TaskDependency.objects.filter(task__product=product)
        locks = FileLock.objects.filter(product=product, status="ACTIVE")
        ready_tasks = tasks.filter(status=TaskStatus.READY)
        in_progress_tasks = tasks.filter(status=TaskStatus.IN_PROGRESS)

        data = {
            'product_id': product.id,
            'tasks': TaskSerializer(tasks, many=True).data,
            'dependencies': TaskDependencySerializer(dependencies, many=True).data,
            'locks': FileLockSerializer(locks, many=True).data,
            'ready_tasks': TaskSerializer(ready_tasks, many=True).data,
            'in_progress_tasks': TaskSerializer(in_progress_tasks, many=True).data,
        }
        return Response(data)

    @action(detail=True, methods=['post'])
    def dispatch_ready(self, request, pk=None):
        """POST /api/v1/workflow/products/{id}/dispatch_ready"""
        product = self.get_object()
        dispatched = WorkflowOrchestrator.dispatch_ready_tasks(product.id)
        return Response({
            'message': f'Dispatched {len(dispatched)} tasks to READY',
            'tasks': TaskSerializer(dispatched, many=True).data
        })

    @action(detail=True, methods=['post'])
    def run_loop(self, request, pk=None):
        """POST /api/v1/workflow/products/{id}/run_loop
        Run one autonomous loop iteration for this product (async)."""
        product = self.get_object()

        from apps.workflow.autonomous.thread_pool import submit

        def _run():
            from django.db import close_old_connections
            close_old_connections()
            from apps.workflow.autonomous.loop import AutonomousLoop
            AutonomousLoop().run_once(product_id=product.id)

        submit(_run)
        return Response({'message': f'Autonomous loop iteration started for product {product.id}'})

    @action(detail=True, methods=['post'])
    def sync_prs(self, request, pk=None):
        """POST /api/v1/workflow/products/{id}/sync_prs
        Sync all PR statuses for tasks in this product."""
        product = self.get_object()
        from apps.workflow.autonomous.pr_sync import PRSyncService
        result = PRSyncService().sync_all()
        return Response(result)


class RequirementViewSet(viewsets.ModelViewSet):
    """Requirement management endpoints."""
    queryset = Requirement.objects.all()
    serializer_class = RequirementSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['product', 'status', 'priority']

    def create(self, request, *args, **kwargs):
        """POST /api/v1/workflow/requirements/
        Upload a requirement document. Automatically triggers the autonomous
        planning pipeline (PO + Architect + task generation) in the background."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requirement = serializer.save()

        # Kick off autonomous planning in background
        auto = request.data.get('auto_plan', True)
        if auto:
            self._trigger_planning(requirement.id)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _trigger_planning(requirement_id: int) -> None:
        from apps.workflow.autonomous.thread_pool import submit

        def _run():
            from django.db import close_old_connections
            close_old_connections()
            from apps.workflow.autonomous.planner import AutonomousPlanner
            try:
                AutonomousPlanner().run(requirement_id)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception(
                    "Autonomous planner failed for requirement %d: %s", requirement_id, exc
                )
        submit(_run)

    def perform_create(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """DELETE /api/v1/workflow/requirements/{id}/

        Deletes the requirement and ALL of its tasks by default (tasks would
        otherwise be orphaned, since Task.requirement is SET_NULL).

        Pass ?delete_repo=true (or {"delete_repo": true} in the body) to ALSO
        empty the product's GitHub repository.
        """
        requirement = self.get_object()
        product = requirement.product

        delete_repo = str(
            request.query_params.get('delete_repo')
            or (request.data.get('delete_repo') if hasattr(request, 'data') else None)
            or ''
        ).lower() in ('1', 'true', 'yes', 'on')

        # Delete all tasks for this requirement (cascades PRs, locks, dependencies).
        task_count = Task.objects.filter(requirement=requirement).count()
        Task.objects.filter(requirement=requirement).delete()

        repo_result = None
        if delete_repo:
            from apps.workflow.autonomous.executor import empty_github_repo
            repo_result = empty_github_repo(product.slug, getattr(product, 'github_repo', ''))

        requirement.delete()

        return Response({
            'deleted': True,
            'tasks_deleted': task_count,
            'repo_emptied': bool(repo_result and repo_result.get('emptied')),
            'repo_detail': repo_result,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def plan(self, request, pk=None):
        """POST /api/v1/workflow/requirements/{id}/plan
        Manually (re-)trigger the autonomous planning pipeline."""
        req = self.get_object()
        from apps.workflow.models import RequirementStatus
        req.status = RequirementStatus.RECEIVED
        req.save(update_fields=['status', 'updated_at'])
        self._trigger_planning(req.id)
        return Response({'message': f'Planning triggered for requirement {req.id}'})


class ArchitectureArtifactViewSet(viewsets.ModelViewSet):
    """Architecture artifact management."""
    queryset = ArchitectureArtifact.objects.all()
    serializer_class = ArchitectureArtifactSerializer
    pagination_class = StandardResultsSetPagination

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """POST /api/v1/workflow/architectures/{id}/approve
        Human approval of architecture design."""
        artifact = self.get_object()
        approved_by = request.data.get('approved_by', 'system')

        artifact = WorkflowOrchestrator.approve_architecture(artifact.id, approved_by)
        return Response(
            self.get_serializer(artifact).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """POST /api/v1/workflow/architectures/{id}/reject
        Reject architecture and request changes."""
        artifact = self.get_object()
        reason = request.data.get('reason', '')

        requirement = artifact.requirement
        WorkflowOrchestrator.reject_architecture(requirement.id, reason)
        artifact.refresh_from_db()

        return Response(
            self.get_serializer(artifact).data,
            status=status.HTTP_200_OK
        )


class TaskViewSet(viewsets.ModelViewSet):
    """Task management endpoints."""
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['product', 'status', 'owner_role', 'assigned_agent']

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """POST /api/v1/workflow/tasks/{id}/assign
        Assign task to agent and acquire locks."""
        task = self.get_object()
        agent_name = request.data.get('agent_name')
        file_paths = request.data.get('file_paths', [])

        try:
            task = TaskDispatcher.assign_task(task.id, agent_name, file_paths)
            return Response(
                self.get_serializer(task).data,
                status=status.HTTP_200_OK
            )
        except (LockConflictError, ValueError) as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_409_CONFLICT
            )

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """POST /api/v1/workflow/tasks/{id}/complete
        Mark task as completed and unlock dependencies."""
        task = self.get_object()
        task = WorkflowOrchestrator.complete_task(task.id)
        return Response(
            self.get_serializer(task).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def in_review(self, request, pk=None):
        """POST /api/v1/workflow/tasks/{id}/in_review
        Move task to in-review status with PR."""
        task = self.get_object()
        pr_url = request.data.get('pr_url')
        task = TaskDispatcher.mark_task_in_review(task.id, pr_url)
        return Response(
            self.get_serializer(task).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def request_changes(self, request, pk=None):
        """POST /api/v1/workflow/tasks/{id}/request_changes"""
        task = self.get_object()
        reason = request.data.get('reason', '')
        task = TaskDispatcher.request_changes_on_task(task.id, reason)
        return Response(self.get_serializer(task).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def rerun(self, request, pk=None):
        """POST /api/v1/workflow/tasks/{id}/rerun/
        Force-reset a CHANGES_REQUESTED or failed task back to READY
        so the autonomous loop picks it up immediately."""
        from apps.workflow.autonomous.thread_pool import submit

        task = self.get_object()
        task.status = TaskStatus.READY
        task.assigned_agent = None
        task.save(update_fields=['status', 'assigned_agent', 'updated_at'])

        # Immediately execute in background
        def _run():
            from django.db import close_old_connections
            from apps.workflow.autonomous.executor import AutonomousExecutor
            close_old_connections()
            AutonomousExecutor().execute_in_background(task.id)

        submit(_run)
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['get'])
    def workspace(self, request, pk=None):
        """GET /api/v1/workflow/tasks/{id}/workspace/
        List or return files written by the agent for this task.
        ?file=relative/path.py  → return that file's content
        """
        from pathlib import Path
        from apps.workflow.autonomous.executor import product_workspace

        task = self.get_object()
        product = task.product
        ws_root = product_workspace(product.slug)
        branch = task.branch_name

        # Optional: return a specific file's content
        rel_file = request.query_params.get('file')
        if rel_file:
            target = (ws_root / rel_file).resolve()
            # Prevent path traversal (is_relative_to is case-insensitive on Windows)
            try:
                target.relative_to(ws_root.resolve())
            except ValueError:
                return Response({'error': 'Invalid path'}, status=400)
            if not target.exists():
                return Response({
                    'error': 'File not found',
                    'looked_for': str(target),
                    'workspace': str(ws_root),
                }, status=404)
            try:
                content = target.read_text(encoding='utf-8', errors='replace')
            except Exception as e:
                return Response({'error': f'Could not read file: {e}'}, status=500)
            return Response({'path': rel_file, 'content': content, 'size': target.stat().st_size})

        # List all files in workspace, skipping heavy/generated directories
        SKIP_DIRS = {
            'node_modules', 'venv', '.git', '__pycache__',
            'dist', 'build', '.mypy_cache', '.pytest_cache',
            '.venv', 'env', '.tox', 'coverage',
        }

        if not ws_root.exists():
            return Response({
                'workspace': str(ws_root),
                'branch': branch,
                'files': [],
                'message': f'Product folder not scaffolded yet — products/{product.slug}/ does not exist.',
            })

        files = []
        for f in sorted(ws_root.rglob('*')):
            # Skip anything inside an excluded directory
            if any(part in SKIP_DIRS for part in f.parts):
                continue
            if f.is_file():
                rel = str(f.relative_to(ws_root))
                files.append({
                    'path': rel,
                    'size': f.stat().st_size,
                    'modified': f.stat().st_mtime,
                })

        return Response({
            'workspace': str(ws_root),
            'branch': branch,
            'file_count': len(files),
            'files': files,
        })


class TaskDependencyViewSet(viewsets.ModelViewSet):
    """Task dependency management."""
    queryset = TaskDependency.objects.all()
    serializer_class = TaskDependencySerializer

    def create(self, request, *args, **kwargs):
        """Create a dependency between tasks."""
        task_id = request.data.get('task')
        depends_on_task_id = request.data.get('depends_on_task')

        dependency = WorkflowOrchestrator.add_task_dependency(task_id, depends_on_task_id)
        return Response(
            self.get_serializer(dependency).data,
            status=status.HTTP_201_CREATED
        )


class FileLockViewSet(viewsets.ReadOnlyModelViewSet):
    """File lock monitoring (read-only from API)."""
    queryset = FileLock.objects.all()
    serializer_class = FileLockSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['product', 'status', 'locked_by_agent']

    @action(detail=False, methods=['post'])
    def expire_stale(self, request):
        """POST /api/v1/workflow/locks/expire_stale
        Find and expire locks beyond their duration."""
        expired_count = LockManager.expire_stale_locks()
        return Response({
            'message': f'Expired {expired_count} stale locks',
            'count': expired_count
        })

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        """POST /api/v1/workflow/locks/{id}/release
        Manually release a lock."""
        lock = self.get_object()
        lock = LockManager.release_lock(lock.id)
        return Response(self.get_serializer(lock).data)


class AgentProfileViewSet(viewsets.ModelViewSet):
    """Agent registry management."""
    queryset = AgentProfile.objects.all()
    serializer_class = AgentProfileSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['role', 'enabled']

    @action(detail=False, methods=['get'])
    def by_role(self, request):
        """GET /api/v1/workflow/agents/by_role?role=FRONTEND_DEVELOPER
        Get all agents for a role."""
        role = request.query_params.get('role')
        if not role:
            return Response({'error': 'role parameter required'}, status=status.HTTP_400_BAD_REQUEST)

        agents = AgentProfile.objects.filter(role=role)
        return Response(self.get_serializer(agents, many=True).data)

    @action(detail=True, methods=['get'])
    def prompt(self, request, pk=None):
        """GET /api/v1/workflow/agents/{id}/prompt
        Return the final composed system prompt for this agent."""
        agent = self.get_object()
        return Response({
            'agent': agent.display_name,
            'role': agent.role,
            'system_prompt': agent.build_system_prompt(),
        })


class PullRequestRecordViewSet(viewsets.ModelViewSet):
    """Pull request tracking (synced from GitHub)."""
    queryset = PullRequestRecord.objects.all()
    serializer_class = PullRequestRecordSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['task', 'status', 'merge_state']

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """POST /api/v1/workflow/prs/{id}/sync
        Sync PR status from GitHub (stub - to be implemented)."""
        pr_record = self.get_object()
        # TODO: Implement GitHub sync
        return Response(self.get_serializer(pr_record).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """POST /api/v1/workflow/prs/{id}/approve
        Human approves the PR. Marks task APPROVED, releases locks,
        dispatches downstream tasks automatically."""
        pr_record = self.get_object()
        approved_by = request.data.get('approved_by', 'human')

        from apps.workflow.autonomous.pr_sync import PRSyncService
        pr_record.status = 'APPROVED'
        pr_record.save()
        PRSyncService._on_approved(pr_record)

        return Response(self.get_serializer(pr_record).data)

    @action(detail=True, methods=['post'])
    def request_changes(self, request, pk=None):
        """POST /api/v1/workflow/prs/{id}/request_changes
        Human requests changes. Returns task to agent for rework."""
        pr_record = self.get_object()
        comment = request.data.get('comment', 'Changes requested by reviewer.')

        from apps.workflow.autonomous.pr_sync import PRSyncService
        pr_record.status = 'CHANGES_REQUESTED'
        pr_record.review_comments = [{"user": "human", "body": comment, "state": "CHANGES_REQUESTED"}]
        pr_record.save()
        PRSyncService._on_changes_requested(pr_record)

        return Response(self.get_serializer(pr_record).data)

    @action(detail=True, methods=['post'])
    def merge(self, request, pk=None):
        """POST /api/v1/workflow/prs/{id}/merge
        Human confirms merge. Completes task and unblocks all dependents."""
        pr_record = self.get_object()
        from apps.workflow.autonomous.pr_sync import PRSyncService
        pr_record.status = 'MERGED'
        pr_record.save()
        PRSyncService._on_merged(pr_record)

        return Response(self.get_serializer(pr_record).data)


class WorkflowEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Audit trail and event stream."""
    queryset = WorkflowEvent.objects.all().order_by('-created_at')
    serializer_class = WorkflowEventSerializer
    pagination_class = StandardResultsSetPagination
    filterset_fields = ['event_type', 'entity_type', 'entity_id']

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """GET /api/v1/workflow/events/recent?limit=50
        Get recent workflow events for dashboard."""
        limit = int(request.query_params.get('limit', 50))
        events = WorkflowEvent.objects.all().order_by('-created_at')[:limit]
        return Response(self.get_serializer(events, many=True).data)
