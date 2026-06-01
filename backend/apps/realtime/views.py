from __future__ import annotations

from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .stream import stream_events


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "app": "realtime"})


@require_GET
def ollama_status(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/realtime/ollama-status/"""
    from django.conf import settings
    configured_model = getattr(settings, "DEFAULT_AGENT_MODEL", "ollama/qwen2.5-coder:7b")
    model_tag = configured_model.replace("ollama/", "")
    ollama_host = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
    models_path = getattr(settings, "OLLAMA_MODELS_PATH", "")

    try:
        import requests as req_lib
        r = req_lib.get(f"{ollama_host}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        model_ready = any(
            m == model_tag or m.startswith(model_tag.split(":")[0])
            for m in models
        )
        # Try to detect which OLLAMA_MODELS the running process is using
        running_models_path = None
        try:
            import subprocess, sys
            if sys.platform == "win32":
                out = subprocess.check_output(
                    ["wmic", "process", "where", "name='ollama.exe'", "get", "EnvironmentVariables"],
                    timeout=3, stderr=subprocess.DEVNULL
                ).decode(errors="replace")
                import re
                m = re.search(r"OLLAMA_MODELS=([^;\s]+)", out)
                if m:
                    running_models_path = m.group(1)
        except Exception:
            pass

        return JsonResponse({
            "running": True,
            "models": models,
            "configured_model": model_tag,
            "model_ready": model_ready,
            "models_path": models_path,
            "running_models_path": running_models_path,
        })
    except Exception:
        return JsonResponse({
            "running": False,
            "models": [],
            "configured_model": model_tag,
            "model_ready": False,
            "models_path": models_path,
            "running_models_path": None,
        })


from django.views.decorators.http import require_POST

@require_POST
def ollama_start(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/realtime/ollama-start/
    Kill any existing Ollama process, then restart with OLLAMA_MODELS set correctly.
    """
    import os, subprocess, sys, time
    from django.conf import settings

    models_path = getattr(settings, "OLLAMA_MODELS_PATH", "")

    # Kill any running Ollama process so we can restart with the right env var
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                           capture_output=True, timeout=5)
        else:
            subprocess.run(["pkill", "-f", "ollama serve"],
                           capture_output=True, timeout=5)
        time.sleep(1)  # give it a moment to fully die
    except Exception:
        pass  # it may not be running — that's fine

    env = os.environ.copy()
    if models_path:
        env["OLLAMA_MODELS"] = models_path
    # Force CPU-only to avoid CUDA_Host buffer OOM on low-VRAM GPUs
    env["OLLAMA_NUM_GPU"] = "0"

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        msg = f"Ollama restarted with OLLAMA_MODELS={models_path or '(default)'}. Check status in 3-5 seconds."
        return JsonResponse({"started": True, "message": msg})
    except FileNotFoundError:
        return JsonResponse({
            "started": False,
            "message": "ollama not found in PATH. Install from https://ollama.com"
        }, status=400)
    except Exception as e:
        return JsonResponse({"started": False, "message": str(e)}, status=500)


@require_GET
def pr_review(request: HttpRequest, task_id: int):
    """GET /api/v1/realtime/pr-review/{task_id}/
    Local PR review page — shows task details, files written, approve/reject buttons.
    """
    from apps.workflow.models import Task, PullRequestRecord
    from apps.workflow.autonomous.executor import product_workspace, ROLE_SUBDIR
    from pathlib import Path

    try:
        task = Task.objects.select_related("product", "requirement").get(id=task_id)
    except Task.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)

    SKIP = {"node_modules", "venv", ".git", "__pycache__", "dist", "build"}
    ws = product_workspace(task.product.slug)
    files = []
    if ws.exists():
        for f in sorted(ws.rglob("*")):
            if any(p in SKIP for p in f.parts):
                continue
            if f.is_file():
                files.append(str(f.relative_to(ws)))

    try:
        pr = PullRequestRecord.objects.get(task=task)
    except PullRequestRecord.DoesNotExist:
        pr = None

    return render(request, "pr_review.html", {
        "task": task,
        "pr": pr,
        "files": files,
        "workspace": str(ws),
    })


@require_GET
def loop_status(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/realtime/loop-status/
    Returns the current state of the autonomous loop (what it's doing right now).
    """
    from apps.workflow.autonomous.loop import get_loop_status
    from apps.workflow.models import Requirement, RequirementStatus, Task, TaskStatus

    status = get_loop_status()

    # Enrich with live DB counts
    status["db"] = {
        "requirements_received": Requirement.objects.filter(status=RequirementStatus.RECEIVED).count(),
        "requirements_planning": Requirement.objects.filter(status=RequirementStatus.UNDER_REVIEW).count(),
        "tasks_ready":       Task.objects.filter(status=TaskStatus.READY).count(),
        "tasks_in_progress": Task.objects.filter(status=TaskStatus.IN_PROGRESS).count(),
        "tasks_in_review":   Task.objects.filter(status=TaskStatus.IN_REVIEW).count(),
    }

    # Recent planning steps from WorkflowEvent
    from apps.workflow.models import WorkflowEvent
    recent_steps = list(
        WorkflowEvent.objects.filter(event_type="PLANNING_STEP")
        .order_by("-created_at")[:20]
        .values("entity_id", "payload_json", "created_at")
    )
    status["recent_planning_steps"] = [
        {
            "req_id": s["entity_id"],
            "step":   s["payload_json"].get("step"),
            "detail": s["payload_json"].get("detail"),
            "ts":     s["created_at"].isoformat(),
        }
        for s in recent_steps
    ]

    return JsonResponse(status)


@require_GET
def event_stream(request: HttpRequest) -> StreamingHttpResponse:
    since_id = int(request.GET.get("since", 0))
    response = StreamingHttpResponse(
        stream_events(since_id=since_id),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_GET
def dashboard(request: HttpRequest):
    return render(request, "dashboard.html")
