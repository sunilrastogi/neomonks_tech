"""
Management command: clean_run
Wipes all workflow data (tasks, requirements, architectures, events, locks, PRs)
and removes generated product/workspace folders, leaving agent profiles intact.

Usage:
    python manage.py clean_run              # prompts for confirmation
    python manage.py clean_run --yes        # skip confirmation
    python manage.py clean_run --yes --keep-products   # wipe DB only, keep folders
"""
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Wipe all workflow data and generated folders for a clean run."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        parser.add_argument("--keep-products", action="store_true",
                            help="Keep products/ and workspace/ folders on disk.")

    def handle(self, *args, **options):
        if not options["yes"]:
            confirm = input(
                "\nWARNING: This will delete ALL products, requirements, tasks, events and generated code.\n"
                "Agent profiles will be kept.\n"
                "Type YES to continue: "
            )
            if confirm.strip() != "YES":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        self._wipe_db()

        if not options["keep_products"]:
            self._wipe_folders()

        self.stdout.write(self.style.SUCCESS("\nDone. Clean run ready — start fresh from the dashboard."))

    # ── DB wipe ──────────────────────────────────────────────────────────

    def _wipe_db(self):
        from apps.workflow.models import (
            ApprovalRecord, ArchitectureArtifact, FileLock,
            Product, PullRequestRecord, Requirement,
            Task, TaskDependency, WorkflowEvent,
        )

        steps = [
            ("WorkflowEvents",       WorkflowEvent),
            ("FileLocks",            FileLock),
            ("PullRequestRecords",   PullRequestRecord),
            ("ApprovalRecords",      ApprovalRecord),
            ("TaskDependencies",     TaskDependency),
            ("Tasks",                Task),
            ("ArchitectureArtifacts",ArchitectureArtifact),
            ("Requirements",         Requirement),
            ("Products",             Product),
        ]

        self.stdout.write("\nClearing database…")
        for label, model in steps:
            count, _ = model.objects.all().delete()
            self.stdout.write(f"  deleted {count:>4}  {label}")

    # ── Folder wipe ───────────────────────────────────────────────────────

    def _wipe_folders(self):
        from django.conf import settings

        base = Path(settings.BASE_DIR)
        project_root = base.parent

        targets = [
            base / "workspace",                   # backend/workspace/
            project_root / "products" / "expense-tracker",
            project_root / "products" / "test-app",
        ]

        # Also find any other product folders that aren't the template
        products_dir = project_root / "products"
        if products_dir.exists():
            for child in products_dir.iterdir():
                if child.is_dir() and child not in targets:
                    targets.append(child)

        self.stdout.write("\nRemoving generated folders…")
        for path in targets:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
                self.stdout.write(f"  removed  {path}")
            else:
                self.stdout.write(f"  (missing) {path}")
