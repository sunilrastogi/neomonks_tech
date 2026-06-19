"""URL routing for workflow API endpoints."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.workflow.api.views import (
    ProductViewSet, RequirementViewSet, ArchitectureArtifactViewSet,
    TaskViewSet, TaskDependencyViewSet, FileLockViewSet,
    AgentProfileViewSet, PullRequestRecordViewSet, WorkflowEventViewSet
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'requirements', RequirementViewSet, basename='requirement')
router.register(r'architectures', ArchitectureArtifactViewSet, basename='architecture')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'dependencies', TaskDependencyViewSet, basename='dependency')
router.register(r'locks', FileLockViewSet, basename='lock')
router.register(r'agents', AgentProfileViewSet, basename='agent')
router.register(r'prs', PullRequestRecordViewSet, basename='pr')
router.register(r'events', WorkflowEventViewSet, basename='event')

urlpatterns = [
    path('', include(router.urls)),
]
