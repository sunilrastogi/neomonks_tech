"""
Management command: seed_agents
Creates AgentProfile rows for the full NeoMonks agent roster.
Safe to run multiple times — uses get_or_create.

Usage:
    python manage.py seed_agents
"""
from django.core.management.base import BaseCommand

from apps.workflow.models import AgentProfile


AGENTS = [
    {
        "display_name": "Rahul Mehta",
        "role": "PRODUCT_OWNER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["docs/", "requirements/"],
    },
    {
        "display_name": "Ananya Iyer",
        "role": "SOLUTION_ARCHITECT",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["architecture/", "docs/"],
    },
    {
        "display_name": "Priya Nair",
        "role": "FRONTEND_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["frontend/", "src/"],
    },
    {
        "display_name": "Arjun Mehta",
        "role": "BACKEND_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["backend/", "api/"],
    },
    {
        "display_name": "Vikram Singh",
        "role": "INFRA_ADMIN",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["infra/", "terraform/", "k8s/"],
    },
    {
        "display_name": "Meera Kapoor",
        "role": "QA_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["tests/", "qa/"],
    },
    {
        "display_name": "Nikhil Verma",
        "role": "DEVOPS_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": [".github/", "ci/", "docker/"],
    },
    {
        "display_name": "Aarav Sharma",
        "role": "DATA_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["data/", "pipelines/", "dbt/"],
    },
    {
        "display_name": "Isha Patel",
        "role": "MLOPS_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["mlops/", "models/", "pipelines/"],
    },
    {
        "display_name": "Rohan Gupta",
        "role": "DATA_SCIENTIST",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["notebooks/", "models/", "experiments/"],
    },
    {
        "display_name": "Neha Agarwal",
        "role": "BI_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["bi/", "dashboards/", "reports/"],
    },
]


class Command(BaseCommand):
    help = "Seed AgentProfile rows for the NeoMonks agent roster."

    def handle(self, *args, **options):
        created_count = 0
        for agent in AGENTS:
            obj, created = AgentProfile.objects.get_or_create(
                display_name=agent["display_name"],
                defaults={
                    "role": agent["role"],
                    "model_name": agent["model_name"],
                    "enabled": True,
                    "allowed_paths": agent["allowed_paths"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {obj.display_name} ({obj.role})"))
            else:
                self.stdout.write(f"  Exists:  {obj.display_name} ({obj.role})")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. {created_count} new agent(s) created, {len(AGENTS) - created_count} already existed.")
        )
