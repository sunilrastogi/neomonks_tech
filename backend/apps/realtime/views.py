from __future__ import annotations

from django.http import HttpRequest, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .stream import stream_events


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "app": "realtime"})


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
