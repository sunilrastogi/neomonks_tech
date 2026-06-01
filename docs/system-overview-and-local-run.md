# System Overview And Local Run

This document describes the target end-state of Neomunks Core after the workflow control plane has been implemented.

## Current Status Snapshot
- Agent modules have already been renamed to human Indian names.
- Extra agents already exist for QA, DevOps, data engineering, MLOps, data science, and BI.
- The system still lacks the workflow control plane, realtime dashboard, and GitHub/PR automation.

## What The System Does
Neomunks Core becomes an autonomous product delivery system:

- A user uploads a requirement document for a product.
- The Product Owner agent reads it and coordinates the workflow.
- The Solution Architect agent converts it into a structured design.
- The Product Owner turns the design into dependency-aware tasks.
- Developer agents pick up only ready work.
- File locks prevent two agents from editing the same file at once.
- Agents push code to GitHub and open PRs.
- Humans review PRs and approve or reject them.
- The Product Owner checks PR status on a schedule.
- A realtime dashboard shows the live workflow state.

## Main Components

### Control Plane
The backend is the source of truth for:

- requirements
- products
- architecture artifacts
- tasks
- task dependencies
- file locks
- agent assignments
- pull requests
- approvals
- workflow events

### Execution Plane
Agents execute only the work assigned to them:

- Product Owner
- Solution Architect
- Frontend Developer
- Backend Developer
- Infrastructure/DevOps Agent
- QA Engineer
- Data Engineer
- MLOps Engineer
- Data Scientist
- BI Developer

Each agent has:

- a human display name
- a role
- owned file paths
- allowed actions

### Visibility Plane
The dashboard shows:

- active products
- current tasks
- dependency status
- blocked work
- in-progress work
- file locks
- PR status
- approval status
- activity feed

## Core Flow
1. Upload requirement document.
2. PO creates or updates the requirement record.
3. Architect generates a design artifact.
4. Human approves architecture.
5. PO creates tasks and dependencies.
6. Dispatcher marks only dependency-free tasks as ready.
7. Agent claims a task and receives file locks.
8. Agent implements work and opens a PR.
9. PR status syncs back from GitHub.
10. Human approves or requests changes.
11. PO checks PR state hourly.
12. Approved PRs can be merged.
13. Merged tasks unlock downstream work.

## Local Run Requirements
When the system is fully built, local development should use:

- Python 3.12+
- Node.js for the frontend
- PostgreSQL
- Redis
- Django backend
- Vite frontend

## Environment Variables
Expected environment variables should include:

- `DEBUG`
- `SECRET_KEY`
- `DATABASE_URL` or PostgreSQL connection fields
- `REDIS_URL`
- `GITHUB_TOKEN` or GitHub App credentials
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- any AI model endpoint variables used by the agents

## Local Startup
Typical local startup sequence:

1. Start PostgreSQL.
2. Start Redis.
3. Start the Django backend.
4. Start the frontend dev server.
5. Start the workflow dispatcher or worker process.
6. Start the periodic PR review job.

## Example Run Commands
These are the expected commands once the system exists:

```bash
python backend/manage.py migrate
python backend/manage.py runserver
```

```bash
cd frontend
npm install
npm run dev
```

```bash
# worker / scheduler process
python -m celery -A core worker
python -m celery -A core beat
```

## How To Verify It Works
- The dashboard loads and shows current workflow state.
- A requirement document can be uploaded.
- The architect can produce a structured plan.
- Tasks are created with dependencies.
- Only ready tasks can be assigned.
- File locks prevent overlap.
- Agents can create branches and PRs.
- PR review status appears in the dashboard.
- Approved PRs can be merged.
- Downstream tasks unlock after completion.

## Recovery Expectations
The system should support:

- retrying failed workflow steps
- resuming from saved state
- releasing stale file locks
- re-syncing PR status
- replaying workflow events for debugging

## Operator Notes
- The backend database is the source of truth.
- The dashboard is a view of workflow state, not the source of truth.
- Agents should react to state changes, not poll dependencies.
- Human approval remains mandatory for architecture and merge.

## Final Goal
At the end, this repo should feel like a small autonomous operating system for product delivery: the PO coordinates, agents execute, humans approve critical gates, and the dashboard always reflects the live truth.
