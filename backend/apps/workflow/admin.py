"""Django admin configuration for workflow models."""
from django.contrib import admin
from apps.workflow.models import (
    Product, Requirement, ArchitectureArtifact, Task, TaskDependency,
    FileLock, AgentProfile, PullRequestRecord, ApprovalRecord, WorkflowEvent,
    PlatformConfiguration
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status', 'created_at')
    search_fields = ('name', 'slug')
    list_filter = ('status', 'created_at')


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = ('title', 'product', 'status', 'priority', 'created_at')
    search_fields = ('title', 'product__name')
    list_filter = ('status', 'priority', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ArchitectureArtifact)
class ArchitectureArtifactAdmin(admin.ModelAdmin):
    list_display = ('requirement', 'status', 'approved_by', 'approved_at', 'created_at')
    search_fields = ('requirement__title',)
    list_filter = ('status', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'product', 'owner_role', 'assigned_agent', 'status', 'order_index')
    search_fields = ('title', 'product__name', 'assigned_agent')
    list_filter = ('status', 'owner_role', 'product', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TaskDependency)
class TaskDependencyAdmin(admin.ModelAdmin):
    list_display = ('task', 'depends_on_task', 'created_at')
    search_fields = ('task__title', 'depends_on_task__title')
    readonly_fields = ('created_at',)


@admin.register(FileLock)
class FileLockAdmin(admin.ModelAdmin):
    list_display = ('file_path', 'locked_by_agent', 'status', 'expires_at', 'locked_at')
    search_fields = ('file_path', 'locked_by_agent', 'product__name')
    list_filter = ('status', 'locked_at', 'expires_at')
    readonly_fields = ('created_at', 'updated_at', 'locked_at')


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'role', 'model_name', 'enabled', 'created_at')
    search_fields = ('display_name', 'role')
    list_filter = ('role', 'enabled', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PullRequestRecord)
class PullRequestRecordAdmin(admin.ModelAdmin):
    list_display = ('task', 'pr_number', 'status', 'merge_state', 'review_state', 'last_synced_at')
    search_fields = ('task__title', 'branch_name', 'pr_url')
    list_filter = ('status', 'merge_state', 'last_synced_at')
    readonly_fields = ('last_synced_at', 'created_at')


@admin.register(ApprovalRecord)
class ApprovalRecordAdmin(admin.ModelAdmin):
    list_display = ('object_type', 'object_id', 'decision', 'decided_by', 'decided_at', 'created_at')
    search_fields = ('decided_by',)
    list_filter = ('object_type', 'decision', 'decided_at', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WorkflowEvent)
class WorkflowEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'entity_type', 'entity_id', 'created_at')
    search_fields = ('event_type', 'entity_type')
    list_filter = ('event_type', 'entity_type', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(PlatformConfiguration)
class PlatformConfigurationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'llm_mode', 'github_repo', 'updated_at')
    readonly_fields = ('updated_at',)
