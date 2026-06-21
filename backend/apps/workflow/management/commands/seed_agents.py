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
        "skills": ["Requirement analysis", "User story writing", "Sprint planning", "Backlog grooming"],
    },
    {
        "display_name": "Ananya Iyer",
        "role": "SOLUTION_ARCHITECT",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["architecture/", "docs/"],
        "skills": ["System design", "API contract design", "Data modeling", "Scalability"],
    },
    {
        "display_name": "Priya Nair",
        "role": "FRONTEND_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["frontend/", "src/"],
        "skills": ["React", "TypeScript", "TailwindCSS", "Vite", "Accessibility"],
    },
    {
        "display_name": "Arjun Mehta",
        "role": "BACKEND_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["backend/", "api/"],
        "skills": ["Python", "Django", "Django REST Framework", "PostgreSQL", "Redis"],
    },
    {
        "display_name": "Vikram Singh",
        "role": "INFRA_ADMIN",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["infra/", "terraform/", "k8s/"],
        "skills": ["Terraform", "Kubernetes", "Docker", "Project scaffolding"],
    },
    {
        "display_name": "Meera Kapoor",
        "role": "QA_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["tests/", "qa/"],
        "skills": ["pytest", "Jest", "Integration testing", "Test automation"],
    },
    {
        "display_name": "Nikhil Verma",
        "role": "DEVOPS_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": [".github/", "ci/", "docker/"],
        "skills": ["GitHub Actions", "CI/CD", "Docker", "Deployment automation"],
    },
    {
        "display_name": "Aarav Sharma",
        "role": "DATA_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["data/", "pipelines/", "dbt/"],
        "skills": ["ETL", "dbt", "SQL", "Data pipelines"],
    },
    {
        "display_name": "Isha Patel",
        "role": "MLOPS_ENGINEER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["mlops/", "models/", "pipelines/"],
        "skills": ["Model serving", "Training pipelines", "MLflow", "Monitoring"],
    },
    {
        "display_name": "Rohan Gupta",
        "role": "DATA_SCIENTIST",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["notebooks/", "models/", "experiments/"],
        "skills": ["Machine learning", "Statistics", "pandas", "Experimentation"],
    },
    {
        "display_name": "Neha Agarwal",
        "role": "BI_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["bi/", "dashboards/", "reports/"],
        "skills": ["Dashboarding", "SQL", "Reporting", "Data visualization"],
    },
    {
        "display_name": "Diya Rao",
        "role": "FLUTTER_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["mobile/", "lib/"],
        "skills": ["Flutter", "Dart", "Provider/Riverpod", "Cross-platform UI", "REST integration"],
    },
    {
        "display_name": "Karan Malhotra",
        "role": "ANDROID_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["android/"],
        "skills": ["Kotlin", "Jetpack Compose", "Android SDK", "Material Design", "Coroutines"],
    },
    {
        "display_name": "Sara Khan",
        "role": "IOS_DEVELOPER",
        "model_name": "ollama/qwen2.5-coder:7b",
        "allowed_paths": ["ios/"],
        "skills": ["Swift", "SwiftUI", "UIKit", "Combine", "Xcode"],
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
                    "skills": agent.get("skills", []),
                    "allowed_paths": agent["allowed_paths"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {obj.display_name} ({obj.role})"))
            else:
                # Backfill skills for agents seeded before the skills field existed.
                if not obj.skills and agent.get("skills"):
                    obj.skills = agent["skills"]
                    obj.save(update_fields=["skills", "updated_at"])
                    self.stdout.write(f"  Updated: {obj.display_name} (added skills)")
                else:
                    self.stdout.write(f"  Exists:  {obj.display_name} ({obj.role})")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. {created_count} new agent(s) created, {len(AGENTS) - created_count} already existed.")
        )
