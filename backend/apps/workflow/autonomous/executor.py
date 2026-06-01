"""
Autonomous Execution Phase
==========================
For every READY, unassigned task:
  1. Find the best available agent for the task's role.
  2. Acquire file locks (no two agents edit the same file).
  3. Run the appropriate CrewAI agent with the task description.
  4. Write code output to the workspace directory.
  5. Commit to a git branch and push (or simulate if no real repo).
  6. Open a GitHub PR (or create a local PullRequestRecord).
  7. Move task → IN_REVIEW.

Downstream tasks are dispatched automatically via signals when a task reaches MERGED.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.workflow.models import (
    AgentProfile, AgentRole,
    FileLock, FileLockStatus,
    PullRequestRecord, PRStatus,
    Task, TaskStatus,
    WorkflowEvent, EventType,
)
from apps.workflow.services.lock_manager import LockConflictError, LockManager
from apps.workflow.services.task_dispatcher import TaskDispatcher

logger = logging.getLogger(__name__)

# One semaphore per task to prevent double-execution
_task_locks: dict[int, threading.Lock] = {}
_task_locks_mutex = threading.Lock()


def _task_semaphore(task_id: int) -> threading.Lock:
    with _task_locks_mutex:
        if task_id not in _task_locks:
            _task_locks[task_id] = threading.Lock()
        return _task_locks[task_id]


# ── Agent prompt template ─────────────────────────────────────────────────────

DEVELOPER_PROMPT = """
You are {agent_name}, a {role_label} at NeoMonks.

YOUR TASK: {title}

DESCRIPTION:
{description}

FILES YOU MUST PRODUCE:
{files_list}

Write the COMPLETE, production-quality implementation for each file.
Output each file using EXACTLY this format:

=== FILE: path/to/file.ext ===
<complete file content here>
=== END FILE ===

Do not include any explanation outside the file blocks.
"""

ROLE_LABELS = {
    "FRONTEND_DEVELOPER": "Senior Frontend Developer",
    "BACKEND_DEVELOPER": "Senior Backend Developer",
    "QA_ENGINEER": "QA Engineer",
    "DEVOPS_ENGINEER": "DevOps Engineer",
    "DATA_ENGINEER": "Data Engineer",
    "MLOPS_ENGINEER": "MLOps Engineer",
    "DATA_SCIENTIST": "Data Scientist",
    "BI_DEVELOPER": "BI Developer",
    "INFRA_ADMIN": "Infrastructure Admin",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def product_workspace(product_slug: str) -> Path:
    """
    Root of the product's actual codebase: products/{slug}/
    This is where agents write code — same folder that runs in production.
    Falls back to workspace/{slug}/ if the products folder doesn't exist yet.
    """
    from apps.workflow.autonomous.scaffolder import PRODUCTS_DIR
    product_dir = PRODUCTS_DIR / product_slug
    if product_dir.exists():
        return product_dir
    # Fallback: legacy workspace location
    base: Path = getattr(settings, "WORKFLOW_WORKSPACE", Path(settings.BASE_DIR) / "workspace")
    fallback = Path(base) / product_slug
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _workspace(product_slug: str, branch: str) -> Path:
    """Return the product root. All git branches live inside this one repo."""
    return product_workspace(product_slug)


# Map owner_role → subdirectory within the product where code lives
ROLE_SUBDIR = {
    "FRONTEND_DEVELOPER": "frontend/src",
    "BACKEND_DEVELOPER":  "backend/apps",
    "QA_ENGINEER":        "tests",
    "DEVOPS_ENGINEER":    "docker",
    "INFRA_ADMIN":        "infra",
    "DATA_ENGINEER":      "backend/apps/data",
    "MLOPS_ENGINEER":     "backend/apps/ml",
    "DATA_SCIENTIST":     "backend/apps/ml",
    "BI_DEVELOPER":       "frontend/src/pages",
}


def _extract_files(text: str) -> dict[str, str]:
    """Parse agent output into {filepath: content} dict."""
    files: dict[str, str] = {}
    pattern = re.compile(r"=== FILE: (.+?) ===\n([\s\S]+?)\n=== END FILE ===", re.MULTILINE)
    for match in pattern.finditer(text):
        path = match.group(1).strip()
        content = match.group(2)
        files[path] = content
    return files


def _planned_files_from_description(description: str) -> list[str]:
    """Read __PLANNED_FILES__ list embedded by the planner."""
    match = re.search(r"__PLANNED_FILES__: (\[.*?\])", description)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return []


def _branch_name(product_slug: str, task_id: int, task_title: str) -> str:
    safe = re.sub(r"[^a-z0-9-]", "-", task_title.lower())[:40].strip("-")
    return f"task/{task_id}-{safe}"


def _emit(event_type: str, entity_type: str, entity_id: int, payload: dict) -> None:
    try:
        WorkflowEvent.objects.create(
            event_type=event_type, entity_type=entity_type,
            entity_id=entity_id, payload_json=payload,
        )
    except Exception:
        logger.exception("Failed to emit %s", event_type)


# ── Git helpers ───────────────────────────────────────────────────────────────

def _get_or_init_repo(workspace: Path):
    """Return a gitpython Repo rooted at workspace, creating one if needed."""
    from git import InvalidGitRepositoryError, Repo

    # Walk up to find an existing repo; if none, init at workspace root
    try:
        return Repo(workspace, search_parent_directories=True)
    except InvalidGitRepositoryError:
        repo = Repo.init(workspace)
        # Create an initial empty commit so branches can be checked out
        repo.index.commit("chore: init workspace [autonomous]")
        logger.info("Git: initialised new repo at %s", workspace)
        return repo


def _git_commit_local(workspace: Path, branch: str, task_title: str) -> bool:
    """
    Always commit locally — even in simulation mode (no GitHub token).
    Returns True on success.
    """
    try:
        repo = _get_or_init_repo(workspace)

        # Checkout or create the branch
        branch_names = [b.name for b in repo.branches]
        if branch in branch_names:
            repo.git.checkout(branch)
        else:
            repo.git.checkout("-b", branch)

        repo.git.add(".")
        if repo.is_dirty(index=True) or repo.untracked_files:
            repo.git.add(".")
            repo.index.commit(f"feat: {task_title} [autonomous]")
            logger.info("Git: committed to branch '%s'", branch)
        else:
            logger.info("Git: nothing to commit on branch '%s'", branch)
        return True
    except Exception as exc:
        logger.warning("Git local commit failed: %s", exc)
        return False


def _git_push_remote(workspace: Path, branch: str) -> bool:
    """Push to remote only if GITHUB_TOKEN + GITHUB_REPO are set."""
    github_token = getattr(settings, "GITHUB_TOKEN", "")
    github_repo = getattr(settings, "GITHUB_REPO", "")
    if not github_token or not github_repo:
        return False
    try:
        repo = _get_or_init_repo(workspace)
        if not repo.remotes:
            origin_url = f"https://{github_token}@github.com/{github_repo}.git"
            repo.create_remote("origin", origin_url)
        origin = repo.remote("origin")
        origin.push(f"{branch}:{branch}", force=True)
        logger.info("Git: pushed branch '%s' to remote", branch)
        return True
    except Exception as exc:
        logger.warning("Git push failed: %s", exc)
        return False


def _git_commit_and_push(workspace: Path, branch: str, task_title: str) -> bool:
    """Commit locally always; push to remote when configured."""
    committed = _git_commit_local(workspace, branch, task_title)
    if committed:
        _git_push_remote(workspace, branch)
    return committed


def _create_github_pr(branch: str, task_title: str, task_description: str) -> str | None:
    """Create a GitHub PR and return its URL, or None if not configured."""
    github_token = getattr(settings, "GITHUB_TOKEN", "")
    github_repo = getattr(settings, "GITHUB_REPO", "")
    github_base_branch = getattr(settings, "GITHUB_BASE_BRANCH", "main")
    if not github_token or not github_repo:
        return None
    try:
        import requests as req_lib
        resp = req_lib.post(
            f"https://api.github.com/repos/{github_repo}/pulls",
            headers={"Authorization": f"token {github_token}", "Accept": "application/vnd.github+json"},
            json={
                "title": task_title,
                "body": task_description[:2000],
                "head": branch,
                "base": github_base_branch,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            pr_data = resp.json()
            logger.info("GitHub PR created: %s", pr_data.get("html_url"))
            return pr_data.get("html_url")
        logger.warning("GitHub PR creation failed: %d %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("GitHub PR creation error: %s", exc)
    return None


# ── Main executor ─────────────────────────────────────────────────────────────

class AutonomousExecutor:
    """Executes a single READY task autonomously in a background thread."""

    def execute_in_background(self, task_id: int) -> None:
        """Spawn a thread to execute the task; returns immediately."""
        t = threading.Thread(target=self._run, args=(task_id,), daemon=True, name=f"task-{task_id}")
        t.start()

    def _run(self, task_id: int) -> None:
        sem = _task_semaphore(task_id)
        if not sem.acquire(blocking=False):
            logger.info("Executor: task %d already running in another thread, skipping", task_id)
            return
        try:
            self._execute(task_id)
        except Exception:
            logger.exception("Executor: unhandled error for task %d", task_id)
            # Mark task as changes-requested so it can be retried
            try:
                task = Task.objects.get(id=task_id)
                task.status = TaskStatus.CHANGES_REQUESTED
                task.save(update_fields=["status", "updated_at"])
            except Exception:
                pass
        finally:
            sem.release()

    def _execute(self, task_id: int) -> None:  # noqa: C901
        task = Task.objects.select_related("product", "requirement").get(id=task_id)
        if task.status != TaskStatus.READY:
            logger.info("Executor: task %d is %s, skipping", task_id, task.status)
            return

        # 1. Find an available agent for this role
        agent_profile = self._pick_agent(task)
        if not agent_profile:
            logger.warning("Executor: no available agent for role %s (task %d)", task.owner_role, task_id)
            return

        # 2. Determine files to lock
        planned_files = _planned_files_from_description(task.description)

        # 3. Acquire file locks
        locked: list[FileLock] = []
        try:
            for fp in planned_files:
                lock = LockManager.acquire_lock(
                    product_id=task.product_id,
                    task_id=task.id,
                    file_path=fp,
                    agent_name=agent_profile.display_name,
                )
                locked.append(lock)
        except LockConflictError as exc:
            logger.warning("Executor: lock conflict for task %d — %s", task_id, exc)
            return

        # 4. Assign task → IN_PROGRESS
        with transaction.atomic():
            task.assigned_agent = agent_profile.display_name
            task.status = TaskStatus.IN_PROGRESS
            branch = _branch_name(task.product.slug, task.id, task.title)
            task.branch_name = branch
            task.save(update_fields=["assigned_agent", "status", "branch_name", "updated_at"])
        _emit(EventType.TASK_IN_PROGRESS, "TASK", task.id, {
            "title": task.title,
            "assigned_agent": agent_profile.display_name,
            "status": "IN_PROGRESS",
            "product_id": task.product_id,
        })
        logger.info("Executor: task %d assigned to %s → IN_PROGRESS", task_id, agent_profile.display_name)

        # 5. Run the CrewAI agent
        code_output = self._run_agent(task, agent_profile, planned_files)

        # 6. Write output files into products/{slug}/
        workspace = _workspace(task.product.slug, branch)
        written_files = _extract_files(code_output)
        if written_files:
            for rel_path, content in written_files.items():
                # If the agent gave a bare filename with no directory, place it in
                # the role-appropriate subdirectory (e.g. frontend/src/ for FE tasks)
                p = Path(rel_path)
                if len(p.parts) == 1:
                    subdir = ROLE_SUBDIR.get(task.owner_role, "")
                    full_path = workspace / subdir / rel_path if subdir else workspace / rel_path
                else:
                    full_path = workspace / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
            logger.info("Executor: wrote %d files to %s for task %d",
                        len(written_files), workspace, task_id)
        else:
            # Write a placeholder so the branch has something to commit
            subdir = ROLE_SUBDIR.get(task.owner_role, "")
            placeholder_dir = workspace / subdir if subdir else workspace
            placeholder_dir.mkdir(parents=True, exist_ok=True)
            placeholder = placeholder_dir / f"task_{task.id}_stub.md"
            clean = re.sub(r"\n*__PLANNED_FILES__: \[.*?\]", "", task.description).strip()
            placeholder.write_text(
                f"# {task.title}\n\nAssigned to: {agent_profile.display_name}\n\n{clean}\n\n"
                f"> This is a stub. Implement the code above.\n",
                encoding="utf-8",
            )
            logger.info("Executor: wrote stub placeholder for task %d", task_id)

        # 7. Git commit + push
        _git_commit_and_push(workspace, branch, task.title)

        # 8. Create PR
        pr_url = _create_github_pr(branch, task.title, task.description) or \
                 f"http://localhost:8000/api/v1/workflow/tasks/{task.id}/"  # local fallback

        # 9. Create PullRequestRecord
        with transaction.atomic():
            pr_record, _ = PullRequestRecord.objects.update_or_create(
                task=task,
                defaults={
                    "branch_name": branch,
                    "pr_url": pr_url,
                    "status": PRStatus.OPEN,
                },
            )
            task.status = TaskStatus.IN_REVIEW
            task.pr_url = pr_url
            task.save(update_fields=["status", "pr_url", "updated_at"])

        _emit(EventType.PR_CREATED, "PR", pr_record.id, {
            "task_id": task.id,
            "branch_name": branch,
            "pr_url": pr_url,
            "agent": agent_profile.display_name,
        })
        _emit(EventType.TASK_IN_REVIEW, "TASK", task.id, {
            "title": task.title,
            "pr_url": pr_url,
            "assigned_agent": agent_profile.display_name,
            "status": "IN_REVIEW",
            "product_id": task.product_id,
        })
        logger.info("Executor: task %d → IN_REVIEW (PR: %s)", task_id, pr_url)

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _pick_agent(task: Task) -> AgentProfile | None:
        """Find an enabled agent for this role that isn't already busy."""
        busy_agents = set(
            Task.objects.filter(
                status__in=[TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW],
                owner_role=task.owner_role,
            ).values_list("assigned_agent", flat=True)
        )
        return (
            AgentProfile.objects.filter(role=task.owner_role, enabled=True)
            .exclude(display_name__in=busy_agents)
            .first()
        )

    @staticmethod
    def _run_agent(task: Task, agent_profile: AgentProfile, planned_files: list[str]) -> str:
        """Run the appropriate CrewAI agent and return its raw output."""
        # Strip the __PLANNED_FILES__ marker from description shown to agent
        clean_desc = re.sub(r"\n*__PLANNED_FILES__: \[.*?\]", "", task.description).strip()
        files_list = "\n".join(f"  - {f}" for f in planned_files) if planned_files else "  (derive appropriate files)"

        prompt = DEVELOPER_PROMPT.format(
            agent_name=agent_profile.display_name,
            role_label=ROLE_LABELS.get(task.owner_role, task.owner_role.replace("_", " ").title()),
            title=task.title,
            description=clean_desc[:3000],
            files_list=files_list,
        )
        try:
            from crewai import Agent as CAgent, Task as CTask, Crew

            llm = agent_profile.model_name or getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b")
            agent = CAgent(
                role=ROLE_LABELS.get(task.owner_role, task.owner_role),
                goal=f"Complete the task: {task.title}",
                backstory=f"You are {agent_profile.display_name}, an expert {ROLE_LABELS.get(task.owner_role, 'developer')}.",
                llm=llm,
                verbose=False,
            )
            ctask = CTask(description=prompt, agent=agent, expected_output="implementation files")
            crew = Crew(agents=[agent], tasks=[ctask], verbose=False)
            result = crew.kickoff()
            return str(result)
        except Exception as exc:
            logger.warning("Executor: CrewAI failed for task %d: %s", task.id, exc)
            # Return a stub so the executor still produces a file
            clean_desc2 = re.sub(r"\n*__PLANNED_FILES__: \[.*?\]", "", task.description).strip()
            stubs = ""
            for fp in (planned_files or ["output/stub.py"]):
                stubs += f"=== FILE: {fp} ===\n# TODO: implement {task.title}\n# {clean_desc2[:200]}\n=== END FILE ===\n\n"
            return stubs
