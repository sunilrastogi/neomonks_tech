"""
Autonomous Planning Phase
=========================
1. Architect agent reads the requirement document and produces a structured JSON design.
2. Product Owner parses the artifact and creates Tasks + TaskDependencies in the DB.
3. Dispatcher moves dependency-free tasks to READY immediately.

Design notes:
- Only ONE LLM call (the architect). The separate PO-brief step is skipped to halve wait time.
- Granular WorkflowEvents are emitted at every step so the dashboard stays live.
- On any failure the requirement is reset to RECEIVED so the loop can retry next tick.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.workflow.models import (
    ArchitectureArtifact, ArchitectureStatus,
    Requirement, RequirementStatus,
    Task, TaskDependency, TaskStatus,
    WorkflowEvent,
)

logger = logging.getLogger(__name__)


# ── Architect prompt ───────────────────────────────────────────────────────────

ARCHITECT_PROMPT = """You are the Solution Architect at NeoMonks. Analyse the requirement below and produce a complete system design.

PRODUCT: {product_name}
REQUIREMENT: {title}

{document}

Return ONLY a valid JSON object — no markdown fences, no explanation — exactly in this shape:

{{
  "rationale": "Why this design was chosen (one paragraph)",
  "components": [
    {{"name": "ComponentName", "type": "frontend|backend|database|api|service|infra", "description": "what it does"}}
  ],
  "tasks": [
    {{
      "title": "Concise task title",
      "description": "Detailed description of exactly what to build",
      "owner_role": "FRONTEND_DEVELOPER|BACKEND_DEVELOPER|QA_ENGINEER|DEVOPS_ENGINEER|DATA_ENGINEER|MLOPS_ENGINEER|DATA_SCIENTIST|BI_DEVELOPER|INFRA_ADMIN",
      "estimate": "XS|S|M|L|XL",
      "files": ["relative/path/to/file.ext"],
      "depends_on": []
    }}
  ]
}}

Rules:
- Every task must have at least one file.
- depends_on contains task TITLES from this same list (empty array if none).
- Use realistic file paths under frontend/src/ or backend/apps/.
- Return ONLY the JSON, nothing else.
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _emit(event_type: str, entity_type: str, entity_id: int, payload: dict) -> None:
    try:
        WorkflowEvent.objects.create(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload,
        )
    except Exception:
        logger.exception("Failed to emit %s", event_type)


def _emit_log(req_id: int, step: str, detail: str = "") -> None:
    """Emit a REQUIREMENT_REVIEWED event repurposed as a planning progress ping."""
    _emit("PLANNING_STEP", "REQUIREMENT", req_id, {"step": step, "detail": detail})
    logger.info("Planning [req %d] %s %s", req_id, step, detail)


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of free-form LLM output."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _run_architect_llm(req: Requirement) -> str:
    """Run the architect LLM call. Returns raw text output."""
    doc = (req.source_document or req.summary or req.title)[:5000]
    prompt = ARCHITECT_PROMPT.format(
        product_name=req.product.name,
        title=req.title,
        document=doc,
    )
    llm = getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b")
    try:
        from crewai import Agent, Crew
        from crewai import Task as CTask

        agent = Agent(
            role="Solution Architect",
            goal="Produce a complete, buildable system architecture as a JSON object",
            backstory="You are an expert software architect. You always return clean, valid JSON.",
            llm=llm,
            verbose=False,
        )
        task = CTask(
            description=prompt,
            agent=agent,
            expected_output="Valid JSON architecture document",
        )
        crew = Crew(agents=[agent], tasks=[task], verbose=False)
        result = crew.kickoff()
        return str(result)
    except Exception as exc:
        logger.warning("Architect LLM failed: %s", exc)
        return ""


# ── Main planner ──────────────────────────────────────────────────────────────

class AutonomousPlanner:
    """Runs the full planning pipeline for a single requirement."""

    def run(self, requirement_id: int) -> ArchitectureArtifact:
        """
        Pipeline:
          RECEIVED → UNDER_REVIEW
            → [LLM] architect designs
            → tasks + dependencies saved
          → APPROVED
          → READY tasks dispatched

        On any error: requirement is reset to RECEIVED so the loop retries.
        """
        req = Requirement.objects.select_related("product").get(id=requirement_id)

        # Mark in-review and announce start
        req.status = RequirementStatus.UNDER_REVIEW
        req.save(update_fields=["status", "updated_at"])
        _emit_log(req.id, "STARTED", f"Planning '{req.title}' for {req.product.name}")

        try:
            return self._run_pipeline(req)
        except Exception as exc:
            # Reset so the loop can retry on the next tick
            logger.exception("Planning failed for req %d — resetting to RECEIVED", req.id)
            req.refresh_from_db()
            req.status = RequirementStatus.RECEIVED
            req.save(update_fields=["status", "updated_at"])
            _emit_log(req.id, "FAILED", str(exc)[:200])
            raise

    def _run_pipeline(self, req: Requirement) -> ArchitectureArtifact:
        # ── Step 1: call the LLM ─────────────────────────────────────────
        _emit_log(req.id, "LLM_CALL", f"Calling {getattr(settings, 'DEFAULT_AGENT_MODEL', 'ollama/...')} — this may take 1-3 min")
        t0 = time.monotonic()
        raw_output = _run_architect_llm(req)
        elapsed = round(time.monotonic() - t0, 1)
        _emit_log(req.id, "LLM_DONE", f"LLM responded in {elapsed}s ({len(raw_output)} chars)")

        # ── Step 2: parse JSON ───────────────────────────────────────────
        design = _extract_json(raw_output)
        if not design.get("tasks"):
            logger.warning("Architect returned no tasks for req %d — using fallback", req.id)
            _emit_log(req.id, "FALLBACK", "LLM returned no parseable tasks — using fallback decomposition")
            design = self._fallback_design(req)
        else:
            _emit_log(req.id, "DESIGN_PARSED", f"{len(design['tasks'])} tasks in design")

        # ── Step 3: save architecture artifact ──────────────────────────
        artifact = self._save_artifact(req, design)
        _emit_log(req.id, "ARTIFACT_SAVED", f"Architecture artifact id={artifact.id}")

        # ── Step 4: create tasks + dependencies ─────────────────────────
        task_count = self._generate_tasks(req, artifact, design)
        _emit_log(req.id, "TASKS_CREATED", f"{task_count} tasks created in DB")

        # ── Step 5: approve requirement + architecture ───────────────────
        with transaction.atomic():
            req.status = RequirementStatus.APPROVED
            req.save(update_fields=["status", "updated_at"])
            artifact.status = ArchitectureStatus.APPROVED
            artifact.approved_by = "Architect (autonomous)"
            artifact.approved_at = timezone.now()
            artifact.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

        _emit("REQUIREMENT_APPROVED", "REQUIREMENT", req.id,
              {"title": req.title, "task_count": task_count, "status": "APPROVED"})
        _emit("ARCHITECTURE_APPROVED", "ARCHITECTURE", artifact.id,
              {"requirement_id": req.id, "task_count": task_count})

        # ── Step 6: dispatch dependency-free tasks ───────────────────────
        dispatched = self._dispatch_ready(req.product_id)
        _emit_log(req.id, "DISPATCHED", f"{dispatched} task(s) moved to READY")

        return artifact

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_design(req: Requirement) -> dict[str, Any]:
        """Minimal viable design when the LLM returns unparseable output."""
        return {
            "rationale": f"Fallback decomposition for: {req.title}",
            "components": [{"name": "Core", "type": "backend", "description": req.summary or req.title}],
            "tasks": [
                {
                    "title": f"Backend: implement {req.title}",
                    "description": req.source_document or req.summary or req.title,
                    "owner_role": "BACKEND_DEVELOPER",
                    "estimate": "M",
                    "files": ["backend/apps/core/views.py", "backend/apps/core/models.py"],
                    "depends_on": [],
                },
                {
                    "title": f"Frontend: implement {req.title} UI",
                    "description": f"Build the user interface for: {req.title}",
                    "owner_role": "FRONTEND_DEVELOPER",
                    "estimate": "M",
                    "files": [f"frontend/src/pages/{req.product.slug}.tsx"],
                    "depends_on": [f"Backend: implement {req.title}"],
                },
            ],
        }

    @staticmethod
    def _save_artifact(req: Requirement, design: dict) -> ArchitectureArtifact:
        artifact, _ = ArchitectureArtifact.objects.update_or_create(
            requirement=req,
            defaults={
                "design_json": design,
                "rationale": design.get("rationale", ""),
                "status": ArchitectureStatus.SUBMITTED,
            },
        )
        _emit("ARCHITECTURE_SUBMITTED", "ARCHITECTURE", artifact.id,
              {"requirement_id": req.id})
        return artifact

    @staticmethod
    @transaction.atomic
    def _generate_tasks(req: Requirement, artifact: ArchitectureArtifact, design: dict) -> int:
        from apps.workflow.models import AgentRole
        raw_tasks: list[dict] = design.get("tasks", [])
        created: dict[str, Task] = {}

        for i, raw in enumerate(raw_tasks):
            role = raw.get("owner_role", "BACKEND_DEVELOPER")
            if role not in AgentRole.values:
                role = "BACKEND_DEVELOPER"

            est = raw.get("estimate", "M")
            if est not in ("XS", "S", "M", "L", "XL"):
                est = "M"

            title = raw.get("title") or f"Task {i + 1}"
            desc = raw.get("description", "")

            # Embed planned files so the executor knows what to create
            files = raw.get("files", [])
            if files:
                desc += f"\n\n__PLANNED_FILES__: {json.dumps(files)}"

            task = Task.objects.create(
                product=req.product,
                requirement=req,
                architecture=artifact,
                title=title,
                description=desc,
                owner_role=role,
                estimate=est,
                order_index=i,
                status=TaskStatus.BLOCKED,
            )
            created[title] = task

        # Wire dependencies (second pass — all tasks exist now)
        for raw in raw_tasks:
            child = created.get(raw.get("title", ""))
            if not child:
                continue
            for dep_title in raw.get("depends_on", []):
                parent = created.get(dep_title)
                if parent and parent.id != child.id:
                    TaskDependency.objects.get_or_create(task=child, depends_on_task=parent)

        return len(created)

    @staticmethod
    def _dispatch_ready(product_id: int) -> int:
        from apps.workflow.services.orchestrator import WorkflowOrchestrator
        dispatched = WorkflowOrchestrator.dispatch_ready_tasks(product_id)
        return len(dispatched)
