# Neomonks Core

## Overview

Neomonks Core is an AI-native autonomous software engineering platform designed to build, orchestrate, and manage multiple software products using coordinated AI agents.

The platform combines:

* local LLMs
* AI agent orchestration
* engineering governance
* deterministic project scaffolding
* automated workflows
* structured outputs
* Git-based SDLC automation

The system is designed to operate as an AI-powered software company where specialized agents collaborate to:

* analyze requirements
* design systems
* scaffold projects
* generate code
* manage workflows
* create pull requests
* support future autonomous SDLC execution

---

# Vision

Neomonks Core aims to become:

* an AI-native software factory
* a multi-product engineering platform
* an autonomous SDLC orchestration system
* a governed AI engineering organization

The platform prioritizes:

* deterministic workflows
* maintainable architecture
* engineering governance
* cost-efficient infrastructure
* production-grade standards
* local-first AI execution

---

# Core Concepts

## Multi-Product Architecture

The platform supports building multiple independent products.

Each product is isolated under:

```text
products/
```

Example:

```text
products/
├── expense_tracker/
├── ai_roasting_platform/
└── future_products/
```

Each product contains:

```text
frontend/
backend/
infra/
docs/
tests/
```

---

# AI Agent Organization

Neomonks Core uses specialized named agents.

## Current Agents

| Agent | Role                         |
| ----- | ---------------------------- |
| Gwenn | Product Owner                |
| Aria  | Solution Architect           |
| Kai   | Frontend Engineer            |
| Rowan | Backend Engineer             |
| Atlas | Infrastructure Administrator |

---

# Agent Responsibilities

## Gwenn — Product Owner

Responsibilities:

* requirement analysis
* sprint planning
* task breakdown
* engineering coordination

---

## Aria — Solution Architect

Responsibilities:

* architecture design
* API contracts
* system boundaries
* infrastructure decisions

---

## Kai — Frontend Engineer

Responsibilities:

* React development
* TypeScript implementation
* UI architecture
* frontend standards compliance

---

## Rowan — Backend Engineer

Responsibilities:

* Django development
* DRF APIs
* PostgreSQL integration
* backend architecture

---

## Atlas — Infrastructure Administrator

Responsibilities:

* project scaffolding
* template management
* infrastructure initialization
* repository setup
* deterministic workspace generation

---

# Engineering Standards

The platform uses centralized governance documentation.

Location:

```text
docs/
```

Current standards:

```text
engineering_standards.md
architecture_principles.md
coding_guidelines.md
frontend_patterns.md
backend_patterns.md
deployment_standards.md
security_standards.md
```

These documents define:

* approved technologies
* architecture rules
* coding standards
* deployment standards
* security requirements
* AI agent operating boundaries

---

# Approved Technology Stack

## Frontend

* React
* TypeScript
* Vite
* TailwindCSS

## Backend

* Python
* Django
* Django REST Framework

## Database

* PostgreSQL
* Redis

## Infrastructure

* Docker Compose
* GitHub Actions
* Hetzner Cloud

## AI Stack

* Ollama
* CrewAI
* local open-source LLMs

---

# Local AI Stack

The platform uses local models through Ollama.

Current models:

| Model             | Purpose                        |
| ----------------- | ------------------------------ |
| qwen2.5-coder:7b  | development agents             |
| mistral:7b        | orchestration and architecture |
| mxbai-embed-large | embeddings                     |

---

# Workflow Architecture

Current workflow direction:

```text
Requirement
    ↓
Gwenn (PO)
    ↓
Aria (Architect)
    ↓
Atlas (Infra Admin)
    ↓
Product Workspace Creation
    ↓
Kai (Frontend)
    ↓
Rowan (Backend)
    ↓
Git Workflow
    ↓
PR Creation
```

---

# Structured Output System

The platform uses deterministic structured outputs.

Example:

```text
CREATE_FOLDER: products/expense_tracker/frontend

CREATE_FILE: products/expense_tracker/README.md
```

This enables:

* reliable parsing
* autonomous filesystem generation
* deterministic orchestration
* future Git automation

---

# Filesystem Orchestration

Current capabilities:

* autonomous folder creation
* autonomous file generation
* structured output parsing
* workflow execution
* Git integration foundation

Implemented through:

```text
utils/
├── file_writer.py
├── folder_manager.py
├── git_manager.py
├── output_parser.py
└── shell_runner.py
```

---

# Template-Based Scaffolding

Neomonks Core uses deterministic templates instead of interactive CLI bootstrapping.

Location:

```text
templates/
```

Current direction:

```text
templates/
├── frontend/
├── backend/
├── docker/
└── github_actions/
```

Atlas copies templates into product workspaces.

This avoids:

* interactive shell prompts
* tooling instability
* non-deterministic scaffolding

---

# Current Repository Structure

```text
neomonks_core/
│
├── agents/
├── workflows/
├── utils/
├── docs/
├── templates/
├── products/
├── infra/
├── logs/
├── db/
├── memory/
├── vectorstore/
│
├── workflow_runner.py
├── main.py
├── requirements.txt
├── .env
└── .gitignore
```

---

# Current Development Status

## Completed

* local AI stack setup
* Ollama integration
* VS Code integration
* CrewAI orchestration
* engineering governance docs
* structured output parsing
* autonomous folder creation
* autonomous file generation
* Git integration foundation
* multi-product architecture
* named agent system
* deterministic scaffolding direction

---

# Planned Next Phases

## Phase 1

Template-based project initialization.

## Phase 2

Git branch automation.

## Phase 3

GitHub PR automation.

## Phase 4

Realtime agent observability dashboard.

## Phase 5

Review feedback loops.

## Phase 6

Advanced orchestration and memory systems.

---

# Long-Term Goals

Planned capabilities:

* autonomous SDLC execution
* multi-agent collaboration
* PR review automation
* infrastructure orchestration
* workflow observability
* organizational memory
* AI-native software operations

---

# Design Philosophy

Neomonks Core prioritizes:

* simplicity
* maintainability
* deterministic behavior
* operational efficiency
* low infrastructure complexity
* governed AI execution

The system intentionally avoids:

* premature microservices
* unnecessary orchestration complexity
* uncontrolled autonomous execution
* infrastructure sprawl

---

# Security Philosophy

AI agents:

* operate within governed boundaries
* cannot directly access secrets
* cannot bypass review processes
* use controlled execution layers

Human review remains mandatory before production deployment.

---

# Future Internal Products

Potential future products:

* Neomonks Control Center
* AI orchestration dashboard
* workflow observability platform
* autonomous SDLC manager
* AI-native DevOps tooling

---

# Current Focus

Current priority:

Build a stable and deterministic autonomous engineering execution layer before adding advanced autonomy.

Focus areas:

* deterministic outputs
* reliable workflows
* governed execution
* scalable architecture
* maintainable orchestration

---

# License

Internal Neomonks Tech platform.
