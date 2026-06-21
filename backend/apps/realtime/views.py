from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .stream import stream_events


def login_required_json(view):
    """Like login_required, but returns 403 JSON instead of redirecting.

    Suitable for the realtime JSON/SSE endpoints called from the dashboard via
    fetch/EventSource (which use the tenant session cookie).
    """
    @wraps(view)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Authentication required."}, status=403)
        return view(request, *args, **kwargs)
    return _wrapped


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "app": "realtime"})


@login_required_json
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

@login_required_json
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


@login_required
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


@login_required_json
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


@login_required_json
@require_GET
def requirement_file(request: HttpRequest, req_id: int) -> JsonResponse:
    """GET /api/v1/realtime/requirement-file/{req_id}/
    Returns the raw markdown content of the saved requirement file so the dashboard
    can display (and allow editing of) the requirement document.
    """
    from apps.workflow.models import Requirement
    from apps.workflow.autonomous.executor import product_workspace
    import re as _re

    try:
        req = Requirement.objects.select_related("product").get(id=req_id)
    except Requirement.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    ws = product_workspace(req.product.slug)
    req_dir = ws / "requirements"
    safe_title = _re.sub(r"[^\w\-]", "_", req.title)[:60]
    req_file = req_dir / f"REQ-{req.id:04d}-{safe_title}.md"

    if req_file.exists():
        content = req_file.read_text(encoding="utf-8")
    else:
        content = (
            f"# {req.title}\n\n"
            f"**Product:** {req.product.name}  \n"
            f"**Status:** {req.status}  \n\n"
            f"## Summary\n\n{req.summary or ''}\n\n"
            f"## Details\n\n{req.source_document or ''}\n"
        )

    return JsonResponse({
        "req_id": req_id,
        "title": req.title,
        "product": req.product.name,
        "status": req.status,
        "file_path": str(req_file) if req_file.exists() else None,
        "content": content,
    })


from django.views.decorators.http import require_POST as _require_POST

@login_required_json
@_require_POST
def requirement_file_save(request: HttpRequest, req_id: int) -> JsonResponse:
    """POST /api/v1/realtime/requirement-file/{req_id}/save/
    Saves updated markdown content back to the requirement file.
    """
    import json as _json
    import re as _re
    from apps.workflow.models import Requirement
    from apps.workflow.autonomous.executor import product_workspace

    try:
        req = Requirement.objects.select_related("product").get(id=req_id)
    except Requirement.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    try:
        body = _json.loads(request.body)
        content = body.get("content", "")
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    ws = product_workspace(req.product.slug)
    req_dir = ws / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    safe_title = _re.sub(r"[^\w\-]", "_", req.title)[:60]
    req_file = req_dir / f"REQ-{req.id:04d}-{safe_title}.md"
    req_file.write_text(content, encoding="utf-8")

    return JsonResponse({"saved": True, "file_path": str(req_file)})


# ── Platform configuration ────────────────────────────────────────────────────

# Secret fields are never returned in full; the dashboard receives a masked
# preview plus a boolean indicating whether a value is stored.
_SECRET_FIELDS = ("db_password", "llm_api_key", "github_token")


def _mask_secret(value: str) -> str:
    """Return a masked preview of a secret, e.g. '••••••O1bi0wN'."""
    if not value:
        return ""
    tail = value[-4:] if len(value) > 4 else ""
    return "••••••" + tail


def _config_to_dict(cfg) -> dict:
    """Serialize the configuration for the dashboard, masking secrets."""
    return {
        # Database
        "db_engine": cfg.db_engine,
        "db_name": cfg.db_name,
        "db_user": cfg.db_user,
        "db_password": "",
        "db_password_set": bool(cfg.db_password),
        "db_password_masked": _mask_secret(cfg.db_password),
        "db_host": cfg.db_host,
        "db_port": cfg.db_port,
        # LLM
        "llm_mode": cfg.llm_mode,
        "llm_provider": cfg.llm_provider,
        "llm_api_key": "",
        "llm_api_key_set": bool(cfg.llm_api_key),
        "llm_api_key_masked": _mask_secret(cfg.llm_api_key),
        "llm_model": cfg.llm_model,
        "ollama_host": cfg.ollama_host,
        "ollama_model": cfg.ollama_model,
        "ollama_models_path": cfg.ollama_models_path,
        # GitHub
        "github_token": "",
        "github_token_set": bool(cfg.github_token),
        "github_token_masked": _mask_secret(cfg.github_token),
        "github_repo": cfg.github_repo,
        "github_base_branch": cfg.github_base_branch,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@login_required_json
@require_GET
def config_get(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/realtime/config/ — current platform configuration (secrets masked)."""
    from apps.workflow.models import PlatformConfiguration

    cfg = PlatformConfiguration.load()
    return JsonResponse(_config_to_dict(cfg))


@login_required_json
@require_POST
def config_save(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/realtime/config/ — persist platform configuration.

    Plain fields are overwritten with whatever is supplied. Secret fields
    (password / api key / token) are only overwritten when a non-empty value
    is sent, so the dashboard can submit blanks to keep existing secrets.
    """
    import json as _json
    from apps.workflow.models import PlatformConfiguration

    try:
        body = _json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    cfg = PlatformConfiguration.load()

    plain_fields = (
        "db_engine", "db_name", "db_user", "db_host", "db_port",
        "llm_mode", "llm_provider", "llm_model",
        "ollama_host", "ollama_model", "ollama_models_path",
        "github_repo", "github_base_branch",
    )
    for field in plain_fields:
        if field in body and body[field] is not None:
            setattr(cfg, field, str(body[field]).strip())

    for field in _SECRET_FIELDS:
        val = body.get(field)
        if val:  # only update when a real value is provided
            setattr(cfg, field, str(val).strip())

    cfg.save()
    return JsonResponse({"saved": True, **_config_to_dict(cfg)})


def _resolved_secret(body_value, stored_value) -> str:
    """For test endpoints: use the submitted secret if present, else the stored one."""
    val = (body_value or "").strip()
    return val if val else stored_value


@login_required_json
@require_POST
def config_test_db(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/realtime/config/test-db/ — try a psycopg connection with given params."""
    import json as _json
    from apps.workflow.models import PlatformConfiguration

    body = _json.loads(request.body or "{}") if request.body else {}
    cfg = PlatformConfiguration.load()

    name = (body.get("db_name") or cfg.db_name).strip()
    user = (body.get("db_user") or cfg.db_user).strip()
    password = _resolved_secret(body.get("db_password"), cfg.db_password)
    host = (body.get("db_host") or cfg.db_host).strip()
    port = (body.get("db_port") or cfg.db_port).strip()

    try:
        try:
            import psycopg  # psycopg 3
            conn = psycopg.connect(
                dbname=name, user=user, password=password,
                host=host, port=port or "5432", connect_timeout=5,
            )
        except ImportError:
            import psycopg2  # psycopg 2 fallback
            conn = psycopg2.connect(
                dbname=name, user=user, password=password,
                host=host, port=port or "5432", connect_timeout=5,
            )
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
        conn.close()
        return JsonResponse({"ok": True, "message": f"Connected — {version}"})
    except Exception as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=400)


@login_required_json
@require_POST
def config_test_llm(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/realtime/config/test-llm/ — verify LLM connectivity (online or local)."""
    import json as _json
    from apps.workflow.models import PlatformConfiguration

    body = _json.loads(request.body or "{}") if request.body else {}
    cfg = PlatformConfiguration.load()
    mode = (body.get("llm_mode") or cfg.llm_mode or "LOCAL").upper()

    try:
        import requests as req_lib
    except ImportError:
        return JsonResponse({"ok": False, "message": "requests library not available"}, status=500)

    if mode == "LOCAL":
        host = (body.get("ollama_host") or cfg.ollama_host or "http://localhost:11434").strip()
        want = (body.get("ollama_model") or cfg.ollama_model or "").strip()
        try:
            r = req_lib.get(f"{host}/api/tags", timeout=5)
            models = [m["name"] for m in r.json().get("models", [])]
            if want and not any(m == want or m.startswith(want.split(":")[0]) for m in models):
                return JsonResponse({
                    "ok": False,
                    "message": f'Ollama reachable but model "{want}" not found. Available: {", ".join(models) or "none"}',
                }, status=400)
            return JsonResponse({"ok": True, "message": f"Ollama reachable — {len(models)} model(s) available"})
        except Exception as e:
            return JsonResponse({"ok": False, "message": f"Ollama not reachable at {host}: {e}"}, status=400)

    # ONLINE providers
    provider = (body.get("llm_provider") or cfg.llm_provider or "OPENAI").upper()
    api_key = _resolved_secret(body.get("llm_api_key"), cfg.llm_api_key)
    if not api_key:
        return JsonResponse({"ok": False, "message": "API key is required for online providers"}, status=400)

    endpoints = {
        "OPENAI": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {api_key}"}),
        "ANTHROPIC": ("https://api.anthropic.com/v1/models", {"x-api-key": api_key, "anthropic-version": "2023-06-01"}),
        "GROQ": ("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {api_key}"}),
        "MISTRAL": ("https://api.mistral.ai/v1/models", {"Authorization": f"Bearer {api_key}"}),
        "OPENROUTER": ("https://openrouter.ai/api/v1/models", {"Authorization": f"Bearer {api_key}"}),
        "GOOGLE": (f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}", {}),
    }
    url, headers = endpoints.get(provider, endpoints["OPENAI"])
    try:
        r = req_lib.get(url, headers=headers, timeout=10)
        if r.status_code in (200, 201):
            return JsonResponse({"ok": True, "message": f"{provider.title()} API key valid"})
        return JsonResponse({
            "ok": False,
            "message": f"{provider.title()} returned HTTP {r.status_code} — check the API key",
        }, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=400)


@login_required_json
@require_POST
def config_test_github(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/realtime/config/test-github/ — validate token and repo access."""
    import json as _json
    from apps.workflow.models import PlatformConfiguration

    body = _json.loads(request.body or "{}") if request.body else {}
    cfg = PlatformConfiguration.load()
    token = _resolved_secret(body.get("github_token"), cfg.github_token)
    repo = (body.get("github_repo") or cfg.github_repo or "").strip()

    if not token:
        return JsonResponse({"ok": False, "message": "GitHub token is required"}, status=400)

    try:
        import requests as req_lib
    except ImportError:
        return JsonResponse({"ok": False, "message": "requests library not available"}, status=500)

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    try:
        u = req_lib.get("https://api.github.com/user", headers=headers, timeout=10)
        if u.status_code != 200:
            return JsonResponse({"ok": False, "message": f"Token invalid (HTTP {u.status_code})"}, status=400)
        login = u.json().get("login", "?")
        if repo:
            rr = req_lib.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=10)
            if rr.status_code != 200:
                return JsonResponse({
                    "ok": False,
                    "message": f"Authenticated as {login}, but repo '{repo}' not accessible (HTTP {rr.status_code})",
                }, status=400)
            return JsonResponse({"ok": True, "message": f"Authenticated as {login} — repo '{repo}' accessible"})
        return JsonResponse({"ok": True, "message": f"Authenticated as {login}"})
    except Exception as e:
        return JsonResponse({"ok": False, "message": str(e)}, status=400)


@login_required_json
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


@login_required
@require_GET
def dashboard(request: HttpRequest):
    return render(request, "dashboard.html")
