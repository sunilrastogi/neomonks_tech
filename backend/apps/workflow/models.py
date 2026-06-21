"""
Workflow control plane data models.
Source of truth for requirements, products, tasks, locks, and approvals.
"""
from django.db import models
from django.utils import timezone
from django.db.models import TextChoices
import json


class RequirementStatus(TextChoices):
    """Requirement state transitions: RECEIVED -> UNDER_REVIEW -> APPROVED -> REJECTED"""
    RECEIVED = "RECEIVED", "Received"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class ArchitectureStatus(TextChoices):
    """Architecture artifact state: DRAFT -> SUBMITTED -> APPROVED -> CHANGES_REQUESTED"""
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes Requested"


class TaskStatus(TextChoices):
    """Task state machine: BLOCKED -> READY -> IN_PROGRESS -> IN_REVIEW -> CHANGES_REQUESTED -> APPROVED -> MERGED"""
    BLOCKED = "BLOCKED", "Blocked"
    READY = "READY", "Ready"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    IN_REVIEW = "IN_REVIEW", "In Review"
    CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes Requested"
    APPROVED = "APPROVED", "Approved"
    MERGED = "MERGED", "Merged"


class FileLockStatus(TextChoices):
    """File lock state: ACTIVE -> RELEASED or EXPIRED"""
    ACTIVE = "ACTIVE", "Active"
    RELEASED = "RELEASED", "Released"
    EXPIRED = "EXPIRED", "Expired"


class PRStatus(TextChoices):
    """Pull request status tracking"""
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    IN_REVIEW = "IN_REVIEW", "In Review"
    APPROVED = "APPROVED", "Approved"
    CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes Requested"
    MERGED = "MERGED", "Merged"
    CLOSED = "CLOSED", "Closed"


class PRMergeState(TextChoices):
    """GitHub PR merge state"""
    CLEAN = "CLEAN", "Can Merge"
    BLOCKED = "BLOCKED", "Blocked"
    UNKNOWN = "UNKNOWN", "Unknown"


class AgentRole(TextChoices):
    """Agent role definitions"""
    PRODUCT_OWNER = "PRODUCT_OWNER", "Product Owner"
    SOLUTION_ARCHITECT = "SOLUTION_ARCHITECT", "Solution Architect"
    FRONTEND_DEVELOPER = "FRONTEND_DEVELOPER", "Frontend Developer"
    BACKEND_DEVELOPER = "BACKEND_DEVELOPER", "Backend Developer"
    INFRA_ADMIN = "INFRA_ADMIN", "Infrastructure Admin"
    QA_ENGINEER = "QA_ENGINEER", "QA Engineer"
    DEVOPS_ENGINEER = "DEVOPS_ENGINEER", "DevOps Engineer"
    DATA_ENGINEER = "DATA_ENGINEER", "Data Engineer"
    MLOPS_ENGINEER = "MLOPS_ENGINEER", "MLOps Engineer"
    DATA_SCIENTIST = "DATA_SCIENTIST", "Data Scientist"
    BI_DEVELOPER = "BI_DEVELOPER", "BI Developer"
    FLUTTER_DEVELOPER = "FLUTTER_DEVELOPER", "Flutter Developer"
    ANDROID_DEVELOPER = "ANDROID_DEVELOPER", "Android Developer"
    IOS_DEVELOPER = "IOS_DEVELOPER", "iOS Developer"


class EventType(TextChoices):
    """Workflow event types for audit trail and realtime updates"""
    REQUIREMENT_CREATED = "REQUIREMENT_CREATED", "Requirement Created"
    REQUIREMENT_REVIEWED = "REQUIREMENT_REVIEWED", "Requirement Reviewed"
    REQUIREMENT_APPROVED = "REQUIREMENT_APPROVED", "Requirement Approved"
    REQUIREMENT_REJECTED = "REQUIREMENT_REJECTED", "Requirement Rejected"
    ARCHITECTURE_SUBMITTED = "ARCHITECTURE_SUBMITTED", "Architecture Submitted"
    ARCHITECTURE_APPROVED = "ARCHITECTURE_APPROVED", "Architecture Approved"
    ARCHITECTURE_CHANGES_REQUESTED = "ARCHITECTURE_CHANGES_REQUESTED", "Architecture Changes Requested"
    TASK_CREATED = "TASK_CREATED", "Task Created"
    TASK_READY = "TASK_READY", "Task Ready"
    TASK_ASSIGNED = "TASK_ASSIGNED", "Task Assigned"
    TASK_IN_PROGRESS = "TASK_IN_PROGRESS", "Task In Progress"
    TASK_COMPLETED = "TASK_COMPLETED", "Task Completed"
    TASK_IN_REVIEW = "TASK_IN_REVIEW", "Task In Review"
    TASK_APPROVED = "TASK_APPROVED", "Task Approved"
    TASK_CHANGES_REQUESTED = "TASK_CHANGES_REQUESTED", "Task Changes Requested"
    TASK_MERGED = "TASK_MERGED", "Task Merged"
    LOCK_ACQUIRED = "LOCK_ACQUIRED", "Lock Acquired"
    LOCK_RELEASED = "LOCK_RELEASED", "Lock Released"
    LOCK_EXPIRED = "LOCK_EXPIRED", "Lock Expired"
    PR_CREATED = "PR_CREATED", "PR Created"
    PR_OPENED = "PR_OPENED", "PR Opened"
    PR_REVIEWED = "PR_REVIEWED", "PR Reviewed"
    PR_APPROVED = "PR_APPROVED", "PR Approved"
    PR_CHANGES_REQUESTED = "PR_CHANGES_REQUESTED", "PR Changes Requested"
    PR_MERGED = "PR_MERGED", "PR Merged"
    PR_CLOSED = "PR_CLOSED", "PR Closed"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED", "Approval Requested"
    APPROVAL_GRANTED = "APPROVAL_GRANTED", "Approval Granted"
    APPROVAL_DENIED = "APPROVAL_DENIED", "Approval Denied"


class Product(models.Model):
    """Product entity - represents a deliverable system."""
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    github_repo = models.CharField(
        max_length=255, blank=True, default="",
        help_text="GitHub repository for this product, e.g. 'org/repo'"
    )
    status = models.CharField(
        max_length=50,
        default="ACTIVE",
        choices=[
            ("ACTIVE", "Active"),
            ("ARCHIVED", "Archived"),
            ("PAUSED", "Paused"),
        ]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Requirement(models.Model):
    """Requirement intake from product owner or document."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="requirements")
    title = models.CharField(max_length=255)
    summary = models.TextField()
    source_document = models.TextField(blank=True, help_text="Original document or description")
    status = models.CharField(
        max_length=50,
        choices=RequirementStatus.choices,
        default=RequirementStatus.RECEIVED
    )
    priority = models.CharField(
        max_length=20,
        choices=[("CRITICAL", "Critical"), ("HIGH", "High"), ("MEDIUM", "Medium"), ("LOW", "Low")],
        default="MEDIUM"
    )
    created_by = models.CharField(max_length=255, default="system")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name}: {self.title}"


class ArchitectureArtifact(models.Model):
    """Architecture design produced by Solution Architect."""
    requirement = models.OneToOneField(
        Requirement, on_delete=models.CASCADE, related_name="architecture"
    )
    design_json = models.JSONField(
        default=dict,
        help_text="Structured design document: components, data models, APIs, dependencies"
    )
    rationale = models.TextField(help_text="Why this design was chosen")
    status = models.CharField(
        max_length=50,
        choices=ArchitectureStatus.choices,
        default=ArchitectureStatus.DRAFT
    )
    approved_by = models.CharField(max_length=255, blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Architecture for {self.requirement.title}"


class Task(models.Model):
    """Execution unit - one deliverable by one agent."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="tasks")
    requirement = models.ForeignKey(
        Requirement, on_delete=models.SET_NULL, null=True, related_name="tasks"
    )
    architecture = models.ForeignKey(
        ArchitectureArtifact, on_delete=models.SET_NULL, null=True, related_name="tasks"
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    acceptance_criteria = models.TextField(
        blank=True, default="",
        help_text="Acceptance criteria the deliverable must satisfy (one per line)"
    )
    tech_stack = models.JSONField(
        default=list, blank=True,
        help_text="Technologies/libraries this task should use"
    )
    owner_role = models.CharField(
        max_length=50,
        choices=AgentRole.choices,
        help_text="Role responsible for this task"
    )
    assigned_agent = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Human display name of assigned agent (e.g., Priya Nair)"
    )
    status = models.CharField(
        max_length=50,
        choices=TaskStatus.choices,
        default=TaskStatus.BLOCKED
    )
    branch_name = models.CharField(max_length=255, blank=True, null=True)
    pr_url = models.URLField(blank=True, null=True)
    estimate = models.CharField(
        max_length=20, blank=True,
        choices=[("XS", "Extra Small"), ("S", "Small"), ("M", "Medium"), ("L", "Large"), ("XL", "Extra Large")],
        help_text="Story points or time estimate"
    )
    order_index = models.IntegerField(default=0, help_text="Task order within product")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order_index", "-created_at"]
        unique_together = [("product", "branch_name")]

    def __str__(self):
        return f"{self.product.name}: {self.title} ({self.status})"


class TaskDependency(models.Model):
    """Explicit task dependency: task depends on another task completing."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependencies")
    depends_on_task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name="dependents"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("task", "depends_on_task")]

    def __str__(self):
        return f"{self.task.title} depends on {self.depends_on_task.title}"


class FileLock(models.Model):
    """Prevent two agents from editing the same file simultaneously."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="locks")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="locks")
    file_path = models.CharField(max_length=500, help_text="Relative path in repository")
    locked_by_agent = models.CharField(max_length=255)
    status = models.CharField(
        max_length=50,
        choices=FileLockStatus.choices,
        default=FileLockStatus.ACTIVE
    )
    locked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Lock auto-expires after this time")
    released_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-locked_at"]
        unique_together = [("product", "file_path", "status")]

    def __str__(self):
        return f"Lock: {self.file_path} by {self.locked_by_agent}"


class AgentProfile(models.Model):
    """Agent registry with display names, roles, and boundaries."""
    display_name = models.CharField(max_length=255, unique=True)
    role = models.CharField(max_length=50, choices=AgentRole.choices)
    model_name = models.CharField(
        max_length=255,
        default="claude-opus-4-6",
        help_text="LLM model this agent uses"
    )
    enabled = models.BooleanField(default=True)
    bio = models.TextField(
        blank=True, default="",
        help_text="Short biography / persona for the agent"
    )
    experience_years = models.IntegerField(
        default=0, help_text="Years of experience (persona detail)"
    )
    skills = models.JSONField(
        default=list, blank=True,
        help_text="List of skill strings that shape this agent's system prompt"
    )
    allowed_paths = models.JSONField(
        default=list,
        help_text="Glob patterns of files/dirs this agent can edit"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role", "display_name"]

    def __str__(self):
        return f"{self.display_name} ({self.role})"

    def build_system_prompt(self) -> str:
        """Compose the agent's base system prompt from its role, skills and scope.

        This is the canonical 'final agent prompt' shown on the profile page and
        used (with task-specific output instructions appended) during execution.
        """
        role_label = self.get_role_display()
        intro = f"You are {self.display_name}, a {role_label} at NeoMonks"
        if self.experience_years:
            intro += f" with {self.experience_years}+ years of experience"
        lines = [intro + "."]

        if (self.bio or "").strip():
            lines.append(self.bio.strip())

        responsibility = ROLE_RESPONSIBILITIES.get(self.role)
        if responsibility:
            lines.append(f"As a {role_label}, you {responsibility}")

        skills = [s for s in (self.skills or []) if str(s).strip()]
        if skills:
            lines.append("")
            lines.append("Your skills:")
            lines.extend(f"  - {s}" for s in skills)

        paths = [p for p in (self.allowed_paths or []) if str(p).strip()]
        if paths:
            lines.append("")
            lines.append("You own these areas of the codebase:")
            lines.extend(f"  - {p}" for p in paths)

        lines.append("")
        lines.append(
            "Always write complete, production-quality, working code that follows "
            "the team's engineering standards. Be concrete and avoid placeholders."
        )
        return "\n".join(lines)


# Plain-language description of what each role is responsible for. Used to build
# the agent system prompt (see AgentProfile.build_system_prompt).
ROLE_RESPONSIBILITIES = {
    AgentRole.PRODUCT_OWNER: "own requirement analysis, sprint planning, and task breakdown.",
    AgentRole.SOLUTION_ARCHITECT: "design system architecture, API contracts, and data models.",
    AgentRole.FRONTEND_DEVELOPER: "build React + TypeScript user interfaces with Tailwind CSS.",
    AgentRole.BACKEND_DEVELOPER: "build Django REST Framework APIs, models, and business logic.",
    AgentRole.INFRA_ADMIN: "scaffold projects and manage infrastructure and repositories.",
    AgentRole.QA_ENGINEER: "write automated tests and verify acceptance criteria.",
    AgentRole.DEVOPS_ENGINEER: "build CI/CD pipelines, Docker images, and deployment automation.",
    AgentRole.DATA_ENGINEER: "build data pipelines, ETL jobs, and data models.",
    AgentRole.MLOPS_ENGINEER: "operationalize ML models, training pipelines, and serving infra.",
    AgentRole.DATA_SCIENTIST: "build models, run experiments, and analyze data.",
    AgentRole.BI_DEVELOPER: "build dashboards, reports, and business-intelligence views.",
    AgentRole.FLUTTER_DEVELOPER: "build cross-platform mobile apps with Flutter and Dart.",
    AgentRole.ANDROID_DEVELOPER: "build native Android apps with Kotlin and Jetpack Compose.",
    AgentRole.IOS_DEVELOPER: "build native iOS apps with Swift and SwiftUI.",
}


class PullRequestRecord(models.Model):
    """Track GitHub PR state and sync."""
    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name="pr_record")
    branch_name = models.CharField(max_length=255)
    pr_number = models.IntegerField(null=True, blank=True)
    pr_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=50,
        choices=PRStatus.choices,
        default=PRStatus.DRAFT
    )
    merge_state = models.CharField(
        max_length=50,
        choices=PRMergeState.choices,
        default=PRMergeState.UNKNOWN
    )
    review_state = models.CharField(
        max_length=255, blank=True,
        help_text="APPROVED, CHANGES_REQUESTED, PENDING, etc."
    )
    review_comments = models.JSONField(default=list, help_text="List of review comments")
    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PR for {self.task.title}: {self.status}"


class ApprovalRecord(models.Model):
    """Human approval decisions for architecture and merge gates."""
    OBJECT_TYPES = [
        ("ARCHITECTURE", "Architecture"),
        ("PR", "Pull Request"),
        ("TASK", "Task"),
    ]
    object_type = models.CharField(max_length=50, choices=OBJECT_TYPES)
    object_id = models.IntegerField()
    decision = models.CharField(
        max_length=50,
        choices=[("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("PENDING", "Pending")],
        default="PENDING"
    )
    decided_by = models.CharField(max_length=255, null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.object_type} {self.object_id}: {self.decision}"


class WorkflowEvent(models.Model):
    """Audit trail and event stream for realtime updates."""
    event_type = models.CharField(max_length=100, choices=EventType.choices)
    entity_type = models.CharField(
        max_length=50,
        choices=[
            ("REQUIREMENT", "Requirement"),
            ("ARCHITECTURE", "Architecture"),
            ("TASK", "Task"),
            ("LOCK", "Lock"),
            ("PR", "Pull Request"),
            ("APPROVAL", "Approval"),
        ]
    )
    entity_id = models.IntegerField()
    payload_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} for {self.entity_type} {self.entity_id}"
