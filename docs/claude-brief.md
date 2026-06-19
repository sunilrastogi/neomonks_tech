# Claude Brief

Read this first:
- [agentic-workflow-plan.md](./agentic-workflow-plan.md)

## What This Repo Is
Neomunks Core is a monorepo for building customer products with agentic AI workflows. It currently has a prototype workflow, renamed human-style agents, a few extra specialist agents, a bootstrap flow, and a starter Django + Vite app.

## What Needs To Be Built
Create a real workflow control plane so the PO can:
- ingest a requirement document
- ask architect for a design
- create dependency-aware tasks
- assign tasks to agents
- ensure only one agent owns a file at a time
- get completion events without polling
- sync GitHub branches/PRs/reviews
- require human approval before merge
- show everything in a realtime kanban dashboard

## Current State
- `workflow_runner.py` is a hardcoded bootstrap script, not a workflow engine
- `main.py` only runs one frontend task
- agents have been renamed to human Indian names
- extra specialist agents have been added for QA, DevOps, data engineering, MLOps, data science, and BI
- agents still are not orchestrated by shared workflow state
- backend is still the default Django skeleton
- frontend is still the default Vite starter

## Must-Have Rules
- PO is the orchestrator
- agents do not poll for dependency completion
- human approval is required for architecture and merge
- two agents must never work on the same file at once
- use human Indian names as agent display names
- keep the workflow state as the source of truth

## Best First Implementation
1. Add workflow models and enums
2. Add orchestration services
3. Add file locking
4. Add task dependency resolution
5. Add GitHub PR sync
6. Add realtime dashboard

## Deliverable Style
Keep changes small, deterministic, and testable. Prefer backend workflow state first, then dashboard, then GitHub automation.
