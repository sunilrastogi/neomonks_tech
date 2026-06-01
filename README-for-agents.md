# README For Agents

Start here:
- [docs/claude-brief.md](docs/claude-brief.md)
- [docs/agentic-workflow-plan.md](docs/agentic-workflow-plan.md)

## What This Repo Is
This is the Neomunks Core monorepo for building customer products with agentic AI workflows.

## Current Reality
- `workflow_runner.py` is a prototype bootstrap script.
- `main.py` runs one demo frontend task.
- Agent modules have already been renamed to human Indian names.
- Extra specialist agents already exist for QA, DevOps, data engineering, MLOps, data science, and BI.
- There is still no real shared workflow engine yet.
- Django backend and Vite frontend are still starter scaffolds.

## Target Outcome
Build a workflow control plane where the Product Owner can:
- ingest a requirement document
- ask the architect for a design
- create dependency-aware tasks
- assign work to agents
- prevent two agents from editing the same file
- receive completion events without polling
- sync GitHub branches and PRs
- require human approval before merge
- show everything on a realtime kanban dashboard

## Non-Negotiable Rules
- Product Owner is the orchestrator.
- Agents should not poll for dependency completion.
- Human approval is required for architecture and merge.
- Two agents must not work on the same file at once.
- Use human Indian names as agent display names.
- Keep workflow state as the source of truth.

## Best Build Order
1. Workflow models and enums
2. Orchestration services
3. File locking
4. Task dependencies and event dispatch
5. GitHub PR sync
6. Realtime dashboard
7. Hourly review/merge gating

## Implementation Style
Keep changes small, deterministic, and testable. Prefer backend workflow state first, then dashboard, then GitHub automation.
