from django.urls import path

from .views import (
    dashboard, event_stream, health, loop_status,
    ollama_status, ollama_start, pr_review,
    requirement_file, requirement_file_save,
)

app_name = "realtime"

urlpatterns = [
    path("health/", health, name="health"),
    path("stream/", event_stream, name="stream"),
    path("dashboard/", dashboard, name="dashboard"),
    path("loop-status/", loop_status, name="loop-status"),
    path("ollama-status/", ollama_status, name="ollama-status"),
    path("ollama-start/", ollama_start, name="ollama-start"),
    path("pr-review/<int:task_id>/", pr_review, name="pr-review"),
    path("requirement-file/<int:req_id>/", requirement_file, name="requirement-file"),
    path("requirement-file/<int:req_id>/save/", requirement_file_save, name="requirement-file-save"),
]
