from django.urls import path

from .views import dashboard, event_stream, health, loop_status

app_name = "realtime"

urlpatterns = [
    path("health/", health, name="health"),
    path("stream/", event_stream, name="stream"),
    path("dashboard/", dashboard, name="dashboard"),
    path("loop-status/", loop_status, name="loop-status"),
]
