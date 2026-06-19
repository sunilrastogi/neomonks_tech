"""
PR Sync Service
===============
Polls GitHub (or falls back to local record checks) for PR review status.
Runs on a configurable interval (default: every 60 minutes).

On APPROVED  → task.complete() → file locks released → downstream tasks dispatched
On CHANGES_REQUESTED → task back to CHANGES_REQUESTED → review comments stored
                      → executor re-runs the task with comments as context
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.workflow.models import (
    PRMergeState, PRStatus,
    PullRequestRecord,
    Task, TaskStatus,
    WorkflowEvent, EventType,
)

logger = logging.getLogger(__name__)


def _emit(event_type: str, entity_type: str, entity_id: int, payload: dict) -> None:
    try:
        WorkflowEvent.objects.create(
            event_type=event_type, entity_type=entity_type,
            entity_id=entity_id, payload_json=payload,
        )
    except Exception:
        logger.exception("Failed to emit %s", event_type)


class PRSyncService:
    """Syncs all open PRs and propagates results into the workflow."""

    def sync_all(self) -> dict:
        """Sync every open PR. Returns a summary dict."""
        open_prs = PullRequestRecord.objects.filter(
            status__in=[PRStatus.OPEN, PRStatus.IN_REVIEW, PRStatus.DRAFT]
        ).select_related("task", "task__product")

        results = {"synced": 0, "approved": 0, "changes_requested": 0, "errors": 0}

        for pr in open_prs:
            try:
                self._sync_one(pr)
                results["synced"] += 1
                if pr.status == PRStatus.APPROVED:
                    results["approved"] += 1
                elif pr.status == PRStatus.CHANGES_REQUESTED:
                    results["changes_requested"] += 1
            except Exception:
                logger.exception("PR sync failed for PR %d", pr.id)
                results["errors"] += 1

        logger.info("PR sync complete: %s", results)
        return results

    def sync_for_task(self, task_id: int) -> PullRequestRecord | None:
        """Sync a single task's PR. Returns the updated record."""
        try:
            pr = PullRequestRecord.objects.get(task_id=task_id)
            self._sync_one(pr)
            return pr
        except PullRequestRecord.DoesNotExist:
            return None

    def _sync_one(self, pr: PullRequestRecord) -> None:  # noqa: C901
        """Fetch GitHub status and apply transitions."""
        github_status = self._fetch_github_status(pr)

        if github_status is None:
            # No GitHub connection — leave PR as-is; human approves via dashboard
            return

        old_status = pr.status
        pr.review_comments = github_status.get("comments", [])
        pr.merge_state = github_status.get("merge_state", PRMergeState.UNKNOWN)

        new_status = github_status.get("status")
        if new_status and new_status != old_status:
            pr.status = new_status
        pr.last_synced_at = timezone.now()
        pr.save()

        if pr.status == PRStatus.APPROVED and old_status != PRStatus.APPROVED:
            logger.info("PR %d approved — completing task %d", pr.id, pr.task_id)
            self._on_approved(pr)

        elif pr.status == PRStatus.CHANGES_REQUESTED and old_status != PRStatus.CHANGES_REQUESTED:
            logger.info("PR %d has changes requested — task %d", pr.id, pr.task_id)
            self._on_changes_requested(pr)

        elif pr.status == PRStatus.MERGED and old_status != PRStatus.MERGED:
            logger.info("PR %d merged — completing task %d", pr.id, pr.task_id)
            self._on_merged(pr)

    # ── transition handlers ────────────────────────────────────────────────

    @staticmethod
    def _on_approved(pr: PullRequestRecord) -> None:
        """Human approved the PR — mark task APPROVED, emit event."""
        with transaction.atomic():
            task = Task.objects.select_for_update().get(id=pr.task_id)
            task.status = TaskStatus.APPROVED
            task.save(update_fields=["status", "updated_at"])
        _emit(EventType.PR_APPROVED, "PR", pr.id,
              {"task_id": pr.task_id, "pr_url": pr.pr_url})
        _emit(EventType.TASK_APPROVED, "TASK", pr.task_id,
              {"title": task.title, "status": "APPROVED", "product_id": task.product_id})

    @staticmethod
    def _on_merged(pr: PullRequestRecord) -> None:
        """PR was merged — complete task, release locks, dispatch downstream."""
        from apps.workflow.services.orchestrator import WorkflowOrchestrator
        from apps.workflow.services.lock_manager import LockManager

        with transaction.atomic():
            task = Task.objects.select_for_update().get(id=pr.task_id)
            task.status = TaskStatus.MERGED
            task.save(update_fields=["status", "updated_at"])
            LockManager.release_locks_for_task(task.id)

        _emit(EventType.PR_MERGED, "PR", pr.id, {"task_id": pr.task_id})
        _emit(EventType.TASK_MERGED, "TASK", pr.task_id,
              {"title": task.title, "status": "MERGED", "product_id": task.product_id})

        # Unblock downstream tasks
        WorkflowOrchestrator.dispatch_ready_tasks(task.product_id)

    @staticmethod
    def _on_changes_requested(pr: PullRequestRecord) -> None:
        """Reviewer requested changes — send task back for rework."""
        with transaction.atomic():
            task = Task.objects.select_for_update().get(id=pr.task_id)
            task.status = TaskStatus.CHANGES_REQUESTED
            task.save(update_fields=["status", "updated_at"])

        comments_summary = "; ".join(
            c.get("body", "")[:100] for c in (pr.review_comments or [])
        )
        _emit(EventType.PR_CHANGES_REQUESTED, "PR", pr.id,
              {"task_id": pr.task_id, "comments": pr.review_comments})
        _emit(EventType.TASK_CHANGES_REQUESTED, "TASK", pr.task_id,
              {"title": task.title, "reason": comments_summary,
               "status": "CHANGES_REQUESTED", "product_id": task.product_id})

    # ── GitHub API ─────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_github_status(pr: PullRequestRecord) -> dict | None:
        """
        Query the GitHub API for this PR's review status.
        Returns None if GitHub is not configured or the PR URL is local.
        """
        github_token = getattr(settings, "GITHUB_TOKEN", "")
        github_repo = getattr(settings, "GITHUB_REPO", "")

        if not github_token or not github_repo:
            return None
        if not pr.pr_number:
            # Try extracting PR number from URL
            import re
            m = re.search(r"/pull/(\d+)", pr.pr_url or "")
            if m:
                pr.pr_number = int(m.group(1))
                pr.save(update_fields=["pr_number"])
            else:
                return None

        try:
            import requests as req_lib

            base = f"https://api.github.com/repos/{github_repo}"
            headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github+json"}

            # Get PR details
            pr_resp = req_lib.get(f"{base}/pulls/{pr.pr_number}", headers=headers, timeout=10)
            if not pr_resp.ok:
                return None
            pr_data = pr_resp.json()

            # Get reviews
            rev_resp = req_lib.get(f"{base}/pulls/{pr.pr_number}/reviews", headers=headers, timeout=10)
            reviews = rev_resp.json() if rev_resp.ok else []

            # Determine status from latest review per user
            latest: dict[str, str] = {}
            for rev in reviews:
                user = rev.get("user", {}).get("login", "unknown")
                state = rev.get("state", "PENDING")
                latest[user] = state

            all_states = list(latest.values())
            if "APPROVED" in all_states and "CHANGES_REQUESTED" not in all_states:
                status = PRStatus.APPROVED
            elif "CHANGES_REQUESTED" in all_states:
                status = PRStatus.CHANGES_REQUESTED
            elif pr_data.get("merged"):
                status = PRStatus.MERGED
            elif pr_data.get("state") == "closed":
                status = PRStatus.CLOSED
            else:
                status = PRStatus.OPEN

            merge_state_raw = pr_data.get("mergeable_state", "unknown").upper()
            merge_state = merge_state_raw if merge_state_raw in ("CLEAN", "BLOCKED", "UNKNOWN") else "UNKNOWN"

            # Collect review comments
            comments = [
                {"user": r.get("user", {}).get("login"), "body": r.get("body", ""), "state": r.get("state")}
                for r in reviews
            ]

            return {"status": status, "merge_state": merge_state, "comments": comments}

        except Exception as exc:
            logger.warning("GitHub API error for PR %d: %s", pr.id, exc)
            return None
