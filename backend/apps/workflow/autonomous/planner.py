"""
Autonomous Planning Phase
=========================
Product Owner → reads requirement
Architect     → designs system, produces JSON task list
PO            → creates Task + TaskDependency records, dispatches READY tasks

All LLM calls go through apps.workflow.autonomous.llm (direct Ollama REST API,
global semaphore, no CrewAI overhead that causes CUDA OOM).
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

LLM_TIMEOUT = int(getattr(settings, "LLM_TIMEOUT_SECONDS", 300))


# ── Event helpers ─────────────────────────────────────────────────────────────

def _emit(event_type: str, entity_type: str, entity_id: int, payload: dict) -> None:
    try:
        WorkflowEvent.objects.create(
            event_type=event_type, entity_type=entity_type,
            entity_id=entity_id, payload_json=payload,
        )
    except Exception:
        logger.exception("Failed to emit %s", event_type)


def _log(req_id: int, step: str, detail: str = "") -> None:
    _emit("PLANNING_STEP", "REQUIREMENT", req_id, {"step": step, "detail": detail})
    logger.info("Planning [req %d] %s  %s", req_id, step, detail)


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict[str, Any]:
    """Pull first JSON object from free-form text, stripping markdown fences."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Try full parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try largest {...} block
    for match in re.finditer(r"\{[\s\S]*\}", text):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue
    return {}


# ── LLM prompts ───────────────────────────────────────────────────────────────

ARCHITECT_SYSTEM = """You are an expert software architect.
Your ONLY job is to output a single valid JSON object.
Never output explanations, markdown, or any text outside the JSON object.
Always start your response with { and end with }."""

ARCHITECT_PROMPT = """Analyse this software requirement and return a detailed JSON architecture with implementation tasks.

PRODUCT: {product_name}
REQUIREMENT: {title}
DETAILS: {document}

Return ONLY this JSON structure (no other text):

{{
  "rationale": "one sentence explaining the architecture",
  "tasks": [
    {{
      "title": "short task title (max 80 chars)",
      "description": "Detailed implementation instructions. Specify exact class names, function signatures, API endpoints, DB columns, UI components, validation rules, error handling, and edge cases. Be concrete — the developer should not need to make design decisions.",
      "acceptance_criteria": ["Specific, testable condition the deliverable must satisfy", "Another concrete criterion"],
      "owner_role": "BACKEND_DEVELOPER",
      "estimate": "M",
      "files": ["backend/apps/expense_tracker/models.py"],
      "depends_on": []
    }}
  ]
}}

Rules:
- owner_role must be one of: FRONTEND_DEVELOPER, BACKEND_DEVELOPER, QA_ENGINEER, DEVOPS_ENGINEER, DATA_ENGINEER, INFRA_ADMIN, FLUTTER_DEVELOPER, ANDROID_DEVELOPER, IOS_DEVELOPER
- estimate must be one of: XS, S, M, L, XL
- depends_on lists task TITLES from this same list
- acceptance_criteria must list 2-5 specific, testable conditions for the task
- Create 4-8 tasks that together fully implement the requirement
- description must be at least 3 sentences, specific to this product — no generic placeholders
- Include exact model field names, API route paths, component prop names, test scenarios
- Include at least one BACKEND_DEVELOPER task and one FRONTEND_DEVELOPER task
- Start your response with {{ immediately"""


# ── Main planner ──────────────────────────────────────────────────────────────

class AutonomousPlanner:
    """Runs the full autonomous planning pipeline for a requirement."""

    def run(self, requirement_id: int) -> ArchitectureArtifact:
        req = Requirement.objects.select_related("product").get(id=requirement_id)

        # Mark in-review
        req.status = RequirementStatus.UNDER_REVIEW
        req.save(update_fields=["status", "updated_at"])
        _log(req.id, "STARTED", f"Planning '{req.title}' for {req.product.name}")

        try:
            return self._pipeline(req)
        except Exception as exc:
            logger.exception("Planning failed for req %d — resetting to RECEIVED", req.id)
            req.refresh_from_db()
            req.status = RequirementStatus.RECEIVED
            req.save(update_fields=["status", "updated_at"])
            _log(req.id, "FAILED", str(exc)[:200])
            raise

    def _pipeline(self, req: Requirement) -> ArchitectureArtifact:
        from apps.workflow.autonomous.llm import call as llm_call
        from apps.workflow.autonomous.executor import product_workspace

        def log(step, detail=""):
            _log(req.id, step, detail)

        # ── Step 0: Persist requirement to file ──────────────────────────
        try:
            ws = product_workspace(req.product.slug)
            req_dir = ws / "requirements"
            req_dir.mkdir(parents=True, exist_ok=True)
            safe_title = re.sub(r"[^\w\-]", "_", req.title)[:60]
            req_file = req_dir / f"REQ-{req.id:04d}-{safe_title}.md"
            req_file.write_text(
                f"# {req.title}\n\n"
                f"**Product:** {req.product.name}  \n"
                f"**Status:** {req.status}  \n"
                f"**Priority:** {req.priority}  \n\n"
                f"## Summary\n\n{req.summary or ''}\n\n"
                f"## Details\n\n{req.source_document or ''}\n",
                encoding="utf-8",
            )
            log("REQ_SAVED", f"Requirement saved to {req_file.relative_to(ws.parent.parent)}")
        except Exception as exc:
            logger.warning("Could not save requirement file: %s", exc)

        # ── Step 1: PO summarises requirement ────────────────────────────
        log("PO_READING", "Product Owner reading requirement document")
        doc = (req.source_document or req.summary or req.title)[:4000]
        po_summary = self._run_po(req, doc, llm_call, log)
        log("PO_DONE", f"PO summary: {po_summary[:100]}")

        # ── Step 2: Architect designs system ────────────────────────────
        log("ARCHITECT_DESIGNING", "Solution Architect designing the system")
        design_text = self._run_architect(req, doc, po_summary, llm_call, log)

        # ── Step 3: Parse JSON ───────────────────────────────────────────
        design = _extract_json(design_text)
        if not design.get("tasks"):
            log("FALLBACK", "Architect output not parseable — using fallback decomposition")
            design = self._fallback_design(req)
        else:
            log("DESIGN_PARSED", f"{len(design['tasks'])} tasks in design")

        # ── Step 4: Save artifact ────────────────────────────────────────
        artifact = self._save_artifact(req, design)
        log("ARTIFACT_SAVED", f"Architecture artifact id={artifact.id}")

        # ── Step 5: Create tasks + dependencies ─────────────────────────
        task_count = self._generate_tasks(req, artifact, design)
        log("TASKS_CREATED", f"{task_count} tasks created in DB")

        # ── Step 6: Approve ──────────────────────────────────────────────
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

        # ── Step 7: Dispatch ready tasks ────────────────────────────────
        dispatched = self._dispatch_ready(req.product_id)
        log("DISPATCHED", f"{dispatched} task(s) moved to READY")

        return artifact

    # ── LLM calls ──────────────────────────────────────────────────────────

    @staticmethod
    def _run_po(req, doc, llm_call, log) -> str:
        prompt = f"""You are a Product Owner reviewing a requirement.
Summarise the key goals in 3 bullet points, then write one sentence architect brief.

PRODUCT: {req.product.name}
REQUIREMENT: {req.title}
DOCUMENT: {doc[:2000]}

Output format:
- Key point 1
- Key point 2
- Key point 3
ARCHITECT BRIEF: <one sentence>"""
        text, error = llm_call(prompt, system="You are a Product Owner. Be concise.", emit_log=log)
        if error:
            raise RuntimeError(error)
        return text or f"Build {req.title} for {req.product.name}"

    @staticmethod
    def _run_architect(req, doc, po_summary, llm_call, log) -> str:
        prompt = ARCHITECT_PROMPT.format(
            product_name=req.product.name,
            title=req.title,
            document=doc[:3000],
        )
        text, error = llm_call(prompt, system=ARCHITECT_SYSTEM, emit_log=log)
        if error:
            raise RuntimeError(error)
        return text

    @staticmethod
    def _fallback_design(req) -> dict[str, Any]:
        slug = req.product.slug.replace("-", "_")
        return {
            "rationale": f"Standard full-stack decomposition for {req.title}",
            "tasks": [
                {
                    "title": f"Design data models for {req.title}",
                    "description": f"Create Django models, serializers and migrations for: {req.summary or req.title}",
                    "owner_role": "BACKEND_DEVELOPER",
                    "estimate": "M",
                    "files": [f"backend/apps/{slug}/models.py", f"backend/apps/{slug}/serializers.py", f"backend/apps/{slug}/migrations/0001_initial.py"],
                    "depends_on": [],
                },
                {
                    "title": f"Build REST API for {req.title}",
                    "description": f"Create DRF views, URLs and permissions for: {req.summary or req.title}",
                    "owner_role": "BACKEND_DEVELOPER",
                    "estimate": "M",
                    "files": [f"backend/apps/{slug}/views.py", f"backend/apps/{slug}/urls.py"],
                    "depends_on": [f"Design data models for {req.title}"],
                },
                {
                    "title": f"Build UI components for {req.title}",
                    "description": f"Create React components with TypeScript and Tailwind CSS for: {req.summary or req.title}",
                    "owner_role": "FRONTEND_DEVELOPER",
                    "estimate": "L",
                    "files": [f"frontend/src/pages/{req.product.slug}.tsx", f"frontend/src/components/{req.product.slug}/index.tsx"],
                    "depends_on": [f"Build REST API for {req.title}"],
                },
                {
                    "title": f"Write tests for {req.title}",
                    "description": f"Write pytest unit and integration tests for the backend, Jest tests for frontend",
                    "owner_role": "QA_ENGINEER",
                    "estimate": "M",
                    "files": [f"tests/test_{slug}.py", f"frontend/src/__tests__/{req.product.slug}.test.tsx"],
                    "depends_on": [f"Build REST API for {req.title}", f"Build UI components for {req.title}"],
                },
            ],
        }

    @staticmethod
    def _save_artifact(req, design) -> ArchitectureArtifact:
        artifact, _ = ArchitectureArtifact.objects.update_or_create(
            requirement=req,
            defaults={
                "design_json": design,
                "rationale": design.get("rationale", ""),
                "status": ArchitectureStatus.SUBMITTED,
            },
        )
        _emit("ARCHITECTURE_SUBMITTED", "ARCHITECTURE", artifact.id, {"requirement_id": req.id})
        return artifact

    @staticmethod
    @transaction.atomic
    def _generate_tasks(req, artifact, design) -> int:
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
            title = (raw.get("title") or f"Task {i+1}").strip()
            desc = raw.get("description", "")
            files = raw.get("files", []) or []
            criteria = raw.get("acceptance_criteria", []) or []
            if isinstance(criteria, str):
                criteria = [criteria]
            criteria_text = "\n".join(str(c).strip() for c in criteria if str(c).strip())
            tech_stack = raw.get("tech_stack", []) or []
            if isinstance(tech_stack, str):
                tech_stack = [tech_stack]
            if files:
                desc += f"\n\n__PLANNED_FILES__: {json.dumps(files)}"

            task = Task.objects.create(
                product=req.product, requirement=req, architecture=artifact,
                title=title, description=desc, owner_role=role,
                acceptance_criteria=criteria_text, tech_stack=tech_stack,
                estimate=est, order_index=i, status=TaskStatus.BLOCKED,
            )
            created[title] = task

        # Wire dependencies
        for raw in raw_tasks:
            child = created.get((raw.get("title") or "").strip())
            if not child:
                continue
            for dep_title in raw.get("depends_on", []):
                parent = created.get(dep_title.strip())
                if parent and parent.id != child.id:
                    TaskDependency.objects.get_or_create(task=child, depends_on_task=parent)

        return len(created)

    @staticmethod
    def _dispatch_ready(product_id: int) -> int:
        from apps.workflow.services.orchestrator import WorkflowOrchestrator
        return len(WorkflowOrchestrator.dispatch_ready_tasks(product_id))
