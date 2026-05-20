# Neomonks Tech Architecture Principles

## Philosophy

Architecture must prioritize:

- simplicity
- maintainability
- operational efficiency
- developer productivity
- predictable scaling
- low infrastructure complexity

We avoid premature optimization.

---

# Preferred Architecture Style

Default architecture:
- Modular Monolith

Avoid:
- microservices
- distributed event systems
- service mesh
- unnecessary async workflows

until scale requirements justify them.

---

# Scalability Philosophy

Preferred scaling order:

1. optimize code
2. optimize queries
3. add caching
4. vertical scaling
5. horizontal scaling
6. distributed architecture

Never start with distributed complexity.

---

# System Boundaries

Each major business domain must be isolated into modules.

Example:

backend/apps/
├── auth/
├── expenses/
├── reports/
├── billing/

Modules should:
- own their models
- own their services
- own their APIs

---

# Backend Principles

Use:
- Django
- Django REST Framework
- PostgreSQL
- Redis

Business logic must exist in:
- services/
- domain layer

Avoid fat views and fat serializers.

---

# Frontend Principles

Frontend architecture should prioritize:
- reusable components
- feature modularity
- predictable state management

Preferred stack:
- React
- TypeScript
- TailwindCSS

Avoid:
- large global state
- deeply nested components
- duplicated logic

---

# API Principles

All APIs must:
- be versioned
- use REST conventions
- return structured JSON
- use JWT authentication
- support pagination

API prefix:

/api/v1/

---

# Database Principles

Primary database:
- PostgreSQL

Avoid:
- multiple databases
- polyglot persistence
- unnecessary NoSQL systems

Use Redis only for:
- caching
- rate limiting
- queues

---

# Infrastructure Principles

Infrastructure must remain:
- reproducible
- simple
- low-cost
- Docker-first

Preferred:
- Docker Compose
- single VPS deployments
- Terraform

Avoid:
- Kubernetes initially
- complex orchestration

---

# Cloud Principles

Primary provider:
- Hetzner Cloud

Scaling philosophy:
- scale vertically first
- split services later only if needed

---

# Reliability Principles

Every system must support:
- health checks
- graceful failures
- structured logging
- observability
- rollback capability

---

# Security Principles

All systems must:
- validate inputs
- enforce RBAC
- encrypt secrets
- use HTTPS
- follow least privilege access

---

# AI Agent Principles

AI agents must:
- respect ownership boundaries
- avoid modifying unrelated modules
- follow standards strictly
- keep PRs small and focused

Human review is mandatory before merge.

---

# Engineering Philosophy

Prefer:
- boring technology
- operational simplicity
- explicit architecture
- deterministic workflows

Avoid:
- trendy complexity
- overengineering
- infrastructure sprawl