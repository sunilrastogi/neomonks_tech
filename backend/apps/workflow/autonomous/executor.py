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
from django.db import models, transaction
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
YOUR TASK: {title}

DESCRIPTION:
{description}
{acceptance_block}
FILES YOU MUST PRODUCE:
{files_list}

Write the COMPLETE, production-quality implementation for each file.
Output each file using EXACTLY this format:

=== FILE: path/to/file.ext ===
<complete file content here>
=== END FILE ===

Do not include any explanation outside the file blocks.
"""

OUTPUT_FORMAT_INSTRUCTIONS = """Output ONLY file blocks in this exact format:
=== FILE: path/to/file.ext ===
<complete file content>
=== END FILE ===
No explanations. No markdown. Only file blocks."""

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
    "FLUTTER_DEVELOPER": "Senior Flutter Developer",
    "ANDROID_DEVELOPER": "Senior Android Developer",
    "IOS_DEVELOPER": "Senior iOS Developer",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def product_workspace(product_slug: str) -> Path:
    """
    Root of the product's actual codebase: products/{slug}/
    Tries multiple slug normalisations (hyphen vs underscore) so that a product
    created with slug 'expense-tracker' finds the folder 'products/expense_tracker'.
    Falls back to workspace/{slug}/ if no products/ folder is found.
    """
    try:
        from apps.workflow.autonomous.scaffolder import PRODUCTS_DIR
    except Exception as exc:
        logger.warning("Could not import PRODUCTS_DIR from scaffolder: %s", exc)
        base = Path(getattr(settings, "WORKFLOW_WORKSPACE", Path(settings.BASE_DIR) / "workspace"))
        p = base / product_slug
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Try the slug as-is, then with hyphens→underscores, then underscores→hyphens
    candidates = [
        product_slug,
        product_slug.replace("-", "_"),
        product_slug.replace("_", "-"),
    ]
    for candidate in candidates:
        p = PRODUCTS_DIR / candidate
        if p.exists():
            logger.info("Workspace: resolved '%s' → products/%s", product_slug, candidate)
            return p

    # Nothing found — create a workspace fallback (do NOT write into products/ silently)
    base = Path(getattr(settings, "WORKFLOW_WORKSPACE", Path(settings.BASE_DIR) / "workspace"))
    fallback = base / product_slug
    fallback.mkdir(parents=True, exist_ok=True)
    logger.warning("Workspace: products/%s not found — writing to workspace/%s", product_slug, product_slug)
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
    "FLUTTER_DEVELOPER":  "mobile/lib",
    "ANDROID_DEVELOPER":  "android/app/src/main",
    "IOS_DEVELOPER":      "ios",
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

    try:
        return Repo(workspace, search_parent_directories=True)
    except InvalidGitRepositoryError:
        repo = Repo.init(workspace)
        logger.info("Git: initialised new repo at %s", workspace)
        # Create an initial commit so branches can be checked out later
        readme = workspace / ".neomonks"
        readme.write_text("NeoMonks autonomous workspace\n")
        repo.index.add([".neomonks"])
        repo.index.commit("chore: init workspace [autonomous]")
        return repo


def _git_commit_local(workspace: Path, branch: str, task_title: str) -> bool:
    """
    Stage all changes and commit on the current branch, then create/switch to
    the task branch.  We commit FIRST (while files are staged) because
    `git checkout -b` fails on a dirty working tree.
    """
    try:
        repo = _get_or_init_repo(workspace)

        # 1. Stage and commit whatever was just written
        repo.git.add(".")
        has_changes = repo.is_dirty(index=True) or bool(repo.untracked_files)
        if has_changes:
            # git requires user identity — set it locally if not configured
            with repo.config_writer() as cfg:
                if not cfg.has_option("user", "email"):
                    cfg.set_value("user", "email", "neomonks@autonomous.local")
                    cfg.set_value("user", "name", "NeoMonks Agent")
            repo.git.add(".")
            repo.index.commit(f"feat: {task_title} [autonomous]")
            logger.info("Git: committed '%s'", task_title)

        # 2. Now switch to / create the task branch (tree is clean)
        branch_names = [b.name for b in repo.branches]
        if branch not in branch_names:
            repo.git.branch(branch)       # create branch pointing to this commit
            logger.info("Git: created branch '%s'", branch)
        # (stay on current branch — branch is just a pointer for PR purposes)
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


# Git's well-known SHA for the empty tree — committing it removes every file
# while preserving history.
_EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def empty_github_repo(product_slug: str, github_repo: str = "") -> dict:
    """Make the product's repository empty.

    ``github_repo`` (e.g. "org/repo") overrides the global GITHUB_REPO setting,
    letting each product target its own repository.

    1. Clears all files from the local product workspace (keeps .git history).
    2. If GITHUB_TOKEN + GITHUB_REPO are configured, pushes an empty-tree commit
       to the default branch so the GitHub repo is emptied too.

    Returns a dict describing what happened.
    """
    result: dict = {"emptied": False, "local_cleared": False, "github": None}

    # ── 1. Clear local workspace files ───────────────────────────────────────
    try:
        ws = product_workspace(product_slug)
        if ws.exists():
            import shutil
            keep = {".git"}
            for child in ws.iterdir():
                if child.name in keep:
                    continue
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except OSError:
                        pass
            result["local_cleared"] = True
            result["emptied"] = True
    except Exception as exc:
        logger.warning("empty_github_repo: local clear failed: %s", exc)
        result["local_error"] = str(exc)

    # ── 2. Empty the GitHub repo via the API (empty-tree commit) ─────────────
    github_token = getattr(settings, "GITHUB_TOKEN", "")
    github_repo = github_repo or getattr(settings, "GITHUB_REPO", "")
    github_base_branch = getattr(settings, "GITHUB_BASE_BRANCH", "main")
    if not github_token or not github_repo:
        result["github"] = "not configured"
        return result

    try:
        import requests as req_lib
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github+json",
        }
        base_url = f"https://api.github.com/repos/{github_repo}"

        # Current head of the default branch
        ref_resp = req_lib.get(
            f"{base_url}/git/ref/heads/{github_base_branch}", headers=headers, timeout=15
        )
        if ref_resp.status_code != 200:
            result["github"] = f"ref lookup failed: {ref_resp.status_code}"
            return result
        parent_sha = ref_resp.json()["object"]["sha"]

        # Commit pointing at the empty tree
        commit_resp = req_lib.post(
            f"{base_url}/git/commits", headers=headers, timeout=15,
            json={
                "message": "chore: empty repository [neomonks]",
                "tree": _EMPTY_TREE_SHA,
                "parents": [parent_sha],
            },
        )
        if commit_resp.status_code not in (200, 201):
            result["github"] = f"commit failed: {commit_resp.status_code} {commit_resp.text[:200]}"
            return result
        new_sha = commit_resp.json()["sha"]

        # Move the branch to the new (empty) commit
        update_resp = req_lib.patch(
            f"{base_url}/git/refs/heads/{github_base_branch}", headers=headers, timeout=15,
            json={"sha": new_sha, "force": True},
        )
        if update_resp.status_code in (200, 201):
            result["github"] = "emptied"
            result["emptied"] = True
            logger.info("GitHub repo %s emptied (commit %s)", github_repo, new_sha[:7])
        else:
            result["github"] = f"ref update failed: {update_resp.status_code} {update_resp.text[:200]}"
    except Exception as exc:
        logger.warning("empty_github_repo: GitHub API error: %s", exc)
        result["github"] = f"error: {exc}"

    return result


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
        """Submit task execution to the shared thread pool."""
        from apps.workflow.autonomous.thread_pool import submit
        submit(self._run, task_id)

    def _run(self, task_id: int) -> None:
        from django.db import close_old_connections
        close_old_connections()

        sem = _task_semaphore(task_id)
        if not sem.acquire(blocking=False):
            logger.info("Executor: task %d already running in another thread, skipping", task_id)
            return
        try:
            self._execute(task_id)
        except Exception as exc:
            logger.exception("Executor: unhandled error for task %d: %s", task_id, exc)
            try:
                close_old_connections()
                task = Task.objects.get(id=task_id)
                err_msg = str(exc)
                is_resource_error = any(
                    kw in err_msg.lower()
                    for kw in ("not running", "unavailable", "connection", "timed out", "empty response")
                )
                if is_resource_error:
                    # Don't mark as CHANGES_REQUESTED — the code isn't wrong,
                    # the model is just unavailable. Keep as READY so the loop
                    # retries automatically when Ollama comes back up.
                    task.status = TaskStatus.READY
                    task.assigned_agent = None
                    self._emit_agent_log(task_id, task.assigned_agent or "Agent",
                                        "RESOURCE_UNAVAILABLE", err_msg[:200])
                else:
                    task.status = TaskStatus.CHANGES_REQUESTED
                task.save(update_fields=["status", "assigned_agent", "updated_at"])
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

        # 2. Determine files to lock (from the __PLANNED_FILES__ marker in the description)
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
        self._emit_agent_log(task.id, agent_profile.display_name,
                             "ASSIGNED", f"Picked up task: {task.title}")
        logger.info("Executor: task %d assigned to %s → IN_PROGRESS", task_id, agent_profile.display_name)

        # 5. Run agent (direct Ollama call)
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
            self._emit_agent_log(task_id, agent_profile.display_name,
                                 "FILES_WRITTEN", f"Wrote {len(written_files)} file(s) to {workspace.name}")
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
                 f"http://localhost:8000/api/v1/realtime/pr-review/{task.id}/"  # local review page

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
        """
        Find the least-loaded enabled agent for this role.
        AI agents can run multiple tasks concurrently — no hard busy exclusion.
        Auto-creates a profile if the role has no agent registered.
        """
        # Get all enabled agents for this role
        role_agents = list(
            AgentProfile.objects.filter(role=task.owner_role, enabled=True)
        )

        if role_agents:
            # Pick the one with fewest active tasks
            def _active_count(agent):
                return Task.objects.filter(
                    assigned_agent=agent.display_name,
                    status__in=[TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW],
                ).count()

            role_agents.sort(key=_active_count)
            return role_agents[0]

        # No role-matched agent — auto-create so the workflow is never stuck
        logger.warning("No agent for role %s — auto-creating profile", task.owner_role)
        role_label = task.owner_role.replace("_", " ").title()
        agent, created = AgentProfile.objects.get_or_create(
            display_name=f"Auto {role_label}",
            defaults={
                "role": task.owner_role,
                "model_name": getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b"),
                "enabled": True,
                "allowed_paths": [],
            },
        )
        if created:
            logger.info("Auto-created agent: %s", agent.display_name)
        return agent

    @staticmethod
    def _emit_agent_log(task_id: int, agent_name: str, step: str, detail: str = "") -> None:
        """Emit an AGENT_LOG event visible on the dashboard."""
        try:
            WorkflowEvent.objects.create(
                event_type="AGENT_LOG",
                entity_type="TASK",
                entity_id=task_id,
                payload_json={"agent": agent_name, "step": step, "detail": detail},
            )
        except Exception:
            pass
        logger.info("Agent [%s / task %d] %s  %s", agent_name, task_id, step, detail)

    @staticmethod
    def _run_agent(task: Task, agent_profile: AgentProfile, planned_files: list[str]) -> str:
        """Call Ollama directly (no CrewAI) to generate implementation files."""
        from apps.workflow.autonomous.llm import call as llm_call

        clean_desc = re.sub(r"\n*__PLANNED_FILES__: \[.*?\]", "", task.description).strip()
        files_list = "\n".join(f"  - {f}" for f in planned_files) if planned_files else "  (choose appropriate files)"
        agent_name = agent_profile.display_name

        # Acceptance criteria drive the implementation — the deliverable must satisfy them.
        criteria_text = (task.acceptance_criteria or "").strip()
        if criteria_text:
            acceptance_block = (
                "\nACCEPTANCE CRITERIA (the implementation MUST satisfy all):\n"
                + criteria_text + "\n"
            )
        else:
            acceptance_block = ""

        def emit(step, detail=""):
            AutonomousExecutor._emit_agent_log(task.id, agent_name, step, detail)

        emit("STARTING", f"Beginning task: {task.title}")

        # Use the agent's composed identity/skills prompt, then append the strict
        # output-format instructions the parser depends on.
        system_prompt = agent_profile.build_system_prompt() + "\n\n" + OUTPUT_FORMAT_INSTRUCTIONS

        user_prompt = DEVELOPER_PROMPT.format(
            title=task.title,
            description=clean_desc[:3000],
            acceptance_block=acceptance_block,
            files_list=files_list,
        )

        emit("LLM_CALL", f"Sending task to {agent_profile.model_name or 'qwen2.5-coder:7b'}")
        raw, llm_error = llm_call(user_prompt, system=system_prompt, emit_log=emit)

        if llm_error:
            # Propagate the error so _execute can set the task to FAILED
            raise RuntimeError(llm_error)

        if raw:
            file_count = raw.count("=== FILE:")
            emit("LLM_DONE", f"Model responded ({len(raw)} chars, ~{file_count} file blocks)")
        else:
            emit("LLM_EMPTY", "Model returned empty response")
            raise RuntimeError("Model returned an empty response — nothing to write.")

        return raw
