from django.urls import path

from .views import (
    config_get, config_save, config_test_db, config_test_github, config_test_llm,
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
    path("config/", config_get, name="config-get"),
    path("config/save/", config_save, name="config-save"),
    path("config/test-db/", config_test_db, name="config-test-db"),
    path("config/test-llm/", config_test_llm, name="config-test-llm"),
    path("config/test-github/", config_test_github, name="config-test-github"),
]
