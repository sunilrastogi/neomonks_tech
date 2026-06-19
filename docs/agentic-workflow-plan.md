# Autonomous Agentic Workflow For Neomunks Core

## Summary
Build a workflow control plane inside this monorepo so the Product Owner becomes the orchestrator of a dependency-aware, event-driven delivery pipeline. The core shift is from "agents run tasks" to "the system manages work state, locks, approvals, GitHub sync, and dashboard visibility," while humans still approve architecture and PR merges.

## Current Repo Status
- Agent modules have already been renamed to human Indian names.
- Extra specialist agents now exist for QA, DevOps, data engineering, MLOps, data science, and BI.
- The workflow engine, task graph, file locking, dashboard, and GitHub automation are still not implemented.

## Claude Build Brief
- Build in phases and keep each phase shippable.
- Prefer a single workflow backend first, then dashboard, then GitHub automation, then deeper orchestration polish.
- Keep agents role-based, but give them human display names everywhere user-facing.
- Make the workflow state the source of truth; agents should react to state changes rather than discover work by polling.

## Build Order
1. Define workflow data models and states.
2. Add Django app scaffolding for workflow, realtime, and GitHub integration.
3. Implement requirement intake and architecture approval flow.
4. Implement task graph creation, dependency resolution, and file locking.
5. Wire agent assignment, task completion events, and downstream unlocks.
6. Add GitHub branch/PR creation and PR status sync.
7. Build the dashboard and realtime updates.
8. Add hourly PO review job and merge gating.
9. Harden tests, permissions, and failure handling.

## Module Responsibilities
- `workflow` app:
  - owns product, requirement, architecture, task, dependency, lock, and approval state
  - exposes the PO orchestration API
  - dispatches ready tasks
  - records task lifecycle transitions

- `github` integration:
  - creates branches and PRs
  - reads PR status and review comments
  - syncs review state into the workflow database

- `realtime` app:
  - serves the live dashboard stream
  - publishes task and lock updates
  - keeps the kanban board in sync without page refresh

- `agents` registry:
  - stores display names, roles, and ownership boundaries
  - maps human names to LLM-backed worker profiles
  - prevents agents from claiming work outside their lane

- `frontend` dashboard:
  - shows kanban lanes, agent activity, blocked work, dependencies, locks, and PR status
  - reflects state updates immediately

## Proposed Data Models
- `Product`
  - name, slug, description, status, created_at

- `Requirement`
  - product, title, source_document, summary, status, priority, created_by

- `ArchitectureArtifact`
  - requirement, design_json, rationale, status, approved_by, approved_at

- `Task`
  - product, requirement, title, description, owner_role, assigned_agent, status, branch_name, pr_url, estimate, order_index

- `TaskDependency`
  - task, depends_on_task

- `FileLock`
  - product, task, file_path, locked_by_agent, locked_at, expires_at, released_at

- `AgentProfile`
  - display_name, role, model_name, enabled, allowed_paths

- `PullRequestRecord`
  - task, branch_name, pr_number, pr_url, status, review_state, merge_state, last_synced_at

- `ApprovalRecord`
  - object_type, object_id, decision, decided_by, decided_at, notes

- `WorkflowEvent`
  - event_type, entity_type, entity_id, payload_json, created_at

## Core State Machine
- Requirement:
  - `RECEIVED` -> `UNDER_REVIEW` -> `APPROVED` -> `REJECTED`

- Architecture:
  - `DRAFT` -> `SUBMITTED` -> `APPROVED` -> `CHANGES_REQUESTED`

- Task:
  - `BLOCKED` -> `READY` -> `IN_PROGRESS` -> `IN_REVIEW` -> `CHANGES_REQUESTED` -> `APPROVED` -> `MERGED`

- File Lock:
  - `ACTIVE` -> `RELEASED` or `EXPIRED`

## API Contracts
- `POST /api/v1/workflow/requirements`
  - create a requirement from the uploaded doc

- `GET /api/v1/workflow/products/:id`
  - return product state, task graph, and active locks

- `POST /api/v1/workflow/requirements/:id/architecture`
  - submit architecture artifact from architect agent

- `POST /api/v1/workflow/architectures/:id/approve`
  - human approval gate for architecture

- `POST /api/v1/workflow/tasks`
  - create tasks from an approved architecture

- `POST /api/v1/workflow/tasks/:id/assign`
  - assign a task to a specific agent after lock validation

- `POST /api/v1/workflow/tasks/:id/complete`
  - mark task done and emit downstream unblock events

- `POST /api/v1/workflow/prs/sync`
  - sync GitHub PR state into the workflow store

- `POST /api/v1/workflow/prs/:id/approve`
  - approve merge after human review

- `GET /api/v1/workflow/stream`
  - realtime event feed for dashboard updates

## Acceptance Criteria
- A requirement can be uploaded and tracked end to end.
- The architect can return a structured design artifact.
- The PO can turn architecture into a dependency graph of tasks.
- Tasks only become available when dependencies are satisfied.
- Two agents cannot hold overlapping file locks at the same time.
- Agents can create branches and PRs from assigned work.
- The PO can see PR status and review comments.
- Human approval is required before merge.
- The dashboard shows live work state without manual refresh.
- The system uses agent display names in the UI and logs.

## Key Changes
- Add a workflow backend in Django.
  - Create a dedicated `workflow` domain with persistent models for requirements, products, architecture artifacts, tasks, dependencies, file locks, agent assignments, PRs, review status, and merge decisions.
  - Add services for orchestration, task dispatch, lock management, GitHub sync, PR polling, and approval gating.
  - Wire DRF endpoints for requirement intake, task status, approval actions, and dashboard data.
  - Add a realtime update stream for the dashboard, ideally via SSE to keep complexity lower than full bidirectional websockets.

- Turn the Product Owner into the orchestrator.
  - Replace the current one-off crew kickoff flow with a PO-led state machine.
  - Flow should be: requirement intake -> architect design -> human approval -> task graph creation -> dependency release -> agent assignment -> PR creation -> review polling -> merge gate.
  - No agent should poll for dependency completion; only the central dispatcher should move tasks from `BLOCKED` to `READY` and emit events.

- Add dependency and file ownership controls.
  - Model task dependencies explicitly so the PO can release work in the right order.
  - Add file/path locking before task assignment so two agents cannot work on the same file at once.
  - Make lock ownership visible on the dashboard and release locks on completion, rejection, or timeout cleanup.

- Add GitHub automation and review loop.
  - Add a GitHub integration layer that can create branches, push code, open PRs, read review comments, and check mergeability.
  - Add an hourly PO review job that checks PR status and updates the workflow state.
  - If a PR is rejected, convert review comments into follow-up work items and route them back to the owning agent.

- Rename agents to human Indian names.
  - Introduce an agent registry with separate `display_name` and `role`.
  - Keep functional roles intact, but show human names in logs, task cards, PR metadata, and dashboard lanes.
  - Example display names: Rahul Sharma, Ananya Iyer, Priya Nair, Arjun Mehta, Vikram Singh.

- Build the realtime dashboard.
  - Replace the starter Vite screen with a kanban-style operations dashboard.
  - Show: who is working on what, current task state, dependencies, next available work, file locks, PR status, and approval blockers.
  - Include a live activity feed so you can see task transitions without refreshing.

## Files / Modules To Add
- Backend control plane:
  - `backend/apps/workflow/models.py`
  - `backend/apps/workflow/services/orchestrator.py`
  - `backend/apps/workflow/services/task_dispatcher.py`
  - `backend/apps/workflow/services/lock_manager.py`
  - `backend/apps/workflow/services/architecture_manager.py`
  - `backend/apps/workflow/services/pr_monitor.py`
  - `backend/apps/workflow/services/approval_manager.py`
  - `backend/apps/workflow/api/views.py`
  - `backend/apps/workflow/api/serializers.py`
  - `backend/apps/workflow/api/urls.py`
  - `backend/apps/workflow/tasks.py`
  - `backend/apps/workflow/events.py`
  - `backend/apps/workflow/signals.py`

- GitHub integration:
  - `backend/apps/github/service.py`
  - `backend/apps/github/webhooks.py`
  - `backend/apps/github/tasks.py`

- Realtime delivery:
  - `backend/apps/realtime/views.py`
  - `backend/apps/realtime/stream.py`
  - `backend/apps/realtime/services.py`

- Agent registry and identity:
  - `agents/registry.py`
  - `agents/profiles.py`
  - `agents/factories.py`

- Workflow entrypoints:
  - Update `workflow_runner.py` to call the new orchestrator instead of doing direct bootstrap work.
  - Update `main.py` to point at the new workflow entry flow or remove the demo-only crew kickoff.
  - Update `tasks/*.py` to become task templates/factories instead of single hardcoded tasks.

- Dashboard frontend:
  - `frontend/src/app/App.tsx` or equivalent top-level shell
  - `frontend/src/features/workflow/kanban.tsx`
  - `frontend/src/features/workflow/task-card.tsx`
  - `frontend/src/features/workflow/agent-lane.tsx`
  - `frontend/src/features/workflow/activity-feed.tsx`
  - `frontend/src/features/workflow/api.ts`
  - `frontend/src/features/workflow/useWorkflowStream.ts`
  - `frontend/src/styles/dashboard.css` or a rebuilt `frontend/src/style.css`

- Configuration and standards:
  - `backend/core/settings.py`
  - `backend/core/urls.py`
  - `requirements.txt`
  - `frontend/package.json`
  - `products/<product>/manifest.yaml` or `manifest.json` for product-level workflow metadata

## Test Plan
- Backend unit tests for:
  - task state transitions
  - dependency resolution
  - lock acquisition and conflict rejection
  - PR status updates
  - approval gating
  - hourly review job behavior

- Integration tests for:
  - requirement intake to architect output
  - task creation to assignment
  - task completion event releasing dependent tasks
  - PR comment ingestion creating follow-up work

- Frontend tests for:
  - kanban rendering
  - live update handling
  - blocked/ready/in-review state visualization

- End-to-end scenario:
  - submit requirement
  - generate architecture
  - approve it
  - create tasks
  - assign one agent
  - simulate PR approval/rejection
  - verify downstream tasks unlock only after completion

## Assumptions
- We keep the repo as a single control plane monorepo, not split into separate services yet.
- Manual approval remains mandatory for architecture approval and merge approval.
- Realtime dashboard updates can start with SSE for simplicity; upgrade to websockets later if bidirectional interaction becomes necessary.
- GitHub integration will use a bot token or GitHub App and will be the source of truth for PR state.
- The existing `products/expense_tracker` folder becomes the model for future product workspaces, each with its own manifest and workflow state.

## Task Tracker
- [x] Save the plan as markdown in the repo.
- [x] Expand the plan into a Claude-ready implementation brief.
- [x] Add build order and module responsibilities.
- [x] Add proposed data models and state machine.
- [x] Add API contracts and acceptance criteria.
- [x] Rename the existing agent modules to human Indian names.
- [x] Add missing specialist agents for QA, DevOps, data engineering, MLOps, data science, and BI.
- [ ] Create Django `workflow` app scaffold.
- [ ] Create `github` integration app scaffold.
- [x] Create `realtime` streaming app scaffold.
- [ ] Replace prototype agent definitions with registry/profile-based agents.
- [ ] Implement workflow models and migrations.
- [ ] Implement task dependency and file locking logic.
- [ ] Implement PO orchestration services.
- [ ] Implement GitHub branch and PR sync flow.
- [ ] Implement dashboard UI and live updates.
- [ ] Implement hourly PR review polling and merge gating.
- [ ] Add tests for state transitions, locking, and task unblock behavior.
