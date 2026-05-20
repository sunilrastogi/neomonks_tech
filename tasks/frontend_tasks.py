from crewai import Task
from agents.frontend_dev import frontend_dev

frontend_login_task = Task(
    description="""
    Build a production-grade login page.

    Requirements:
    - React
    - TypeScript
    - TailwindCSS
    - responsive design
    - loading state
    - validation
    - error handling

    Follow:
    - docs/frontend_patterns.md
    - docs/coding_guidelines.md
    - docs/engineering_standards.md

    Output:
    Return complete code for:
    frontend/src/pages/LoginPage.tsx
    """,
    expected_output="""
    Production-ready React login page.
    """,
    agent=frontend_dev
)