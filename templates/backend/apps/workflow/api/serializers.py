"""API serializers for workflow models."""
from rest_framework import serializers
from apps.workflow.models import (
    Product, Requirement, ArchitectureArtifact, Task, TaskDependency,
    FileLock, AgentProfile, PullRequestRecord, ApprovalRecord,
    WorkflowEvent
)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'status', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class RequirementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = Requirement
        fields = ['id', 'product', 'product_name', 'title', 'summary', 'source_document',
                  'status', 'priority', 'created_by', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class ArchitectureArtifactSerializer(serializers.ModelSerializer):
    requirement_title = serializers.CharField(source='requirement.title', read_only=True)

    class Meta:
        model = ArchitectureArtifact
        fields = ['id', 'requirement', 'requirement_title', 'design_json', 'rationale',
                  'status', 'approved_by', 'approved_at', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class TaskDependencySerializer(serializers.ModelSerializer):
    task_title = serializers.CharField(source='task.title', read_only=True)
    depends_on_title = serializers.CharField(source='depends_on_task.title', read_only=True)

    class Meta:
        model = TaskDependency
        fields = ['id', 'task', 'task_title', 'depends_on_task', 'depends_on_title', 'created_at']
        read_only_fields = ['created_at']


class TaskSerializer(serializers.ModelSerializer):
    dependencies = TaskDependencySerializer(many=True, read_only=True)
    dependents = TaskDependencySerializer(many=True, read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    requirement_title = serializers.CharField(source='requirement.title', read_only=True, allow_null=True)

    class Meta:
        model = Task
        fields = ['id', 'product', 'product_name', 'requirement', 'requirement_title',
                  'title', 'description', 'owner_role', 'assigned_agent', 'status',
                  'branch_name', 'pr_url', 'estimate', 'order_index',
                  'dependencies', 'dependents', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class FileLockSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = FileLock
        fields = ['id', 'product', 'product_name', 'task', 'task_title', 'file_path',
                  'locked_by_agent', 'status', 'locked_at', 'expires_at', 'released_at',
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at', 'locked_at']


class AgentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentProfile
        fields = ['id', 'display_name', 'role', 'model_name', 'enabled', 'allowed_paths',
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class PullRequestRecordSerializer(serializers.ModelSerializer):
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = PullRequestRecord
        fields = ['id', 'task', 'task_title', 'branch_name', 'pr_number', 'pr_url',
                  'status', 'merge_state', 'review_state', 'review_comments',
                  'last_synced_at', 'created_at']
        read_only_fields = ['created_at', 'last_synced_at']


class ApprovalRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalRecord
        fields = ['id', 'object_type', 'object_id', 'decision', 'decided_by',
                  'decided_at', 'notes', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class WorkflowEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowEvent
        fields = ['id', 'event_type', 'entity_type', 'entity_id', 'payload_json', 'created_at']
        read_only_fields = ['created_at']


class TaskGraphSerializer(serializers.Serializer):
    """Serializer for task graph representation with dependencies."""
    product_id = serializers.IntegerField()
    tasks = TaskSerializer(many=True)
    dependencies = TaskDependencySerializer(many=True)
    locks = FileLockSerializer(many=True)
    ready_tasks = TaskSerializer(many=True)
    in_progress_tasks = TaskSerializer(many=True)
