from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workflow"
    verbose_name = "Workflow Control Plane"

    def ready(self):
        """Initialize app signals and handlers."""
        import apps.workflow.signals  # noqa
