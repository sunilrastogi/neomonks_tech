# Neomonks Tech Engineering Standards

## Company Philosophy

We prioritize:
- simplicity
- maintainability
- low operational overhead
- developer productivity
- cost efficiency
- scalable foundations

Avoid premature optimization.

Build MVP-first systems.

---

# Approved Technology Stack

## Frontend

Allowed:
- React
- Vite
- TypeScript
- TailwindCSS

Disallowed:
- Angular
- Vue
- jQuery

---

## Backend

Allowed:
- Python
- Django
- Django REST Framework

Disallowed:
- Node.js
- Express.js
- PHP
- Ruby on Rails

IMPORTANT:
All APIs must use Django REST Framework.

---

## Database

Primary:
- PostgreSQL

Caching:
- Redis

Disallowed:
- MongoDB unless explicitly approved
- Multiple databases for MVP systems

---

## Infrastructure

Allowed:
- Docker Compose
- GitHub Actions

Disallowed:
- Kubernetes
- ECS
- Complex orchestration

IMPORTANT:
Infrastructure must remain simple for local development.

---

## Deployment

Preferred:
- Single VM deployment
- Dockerized deployment

Avoid:
- Microservice deployments
- Multi-cluster systems
- Service mesh architectures

---

# Architecture Standards

## Preferred Architecture

Default:
- Modular monolith

Avoid:
- Microservices
- Event-driven systems
- Distributed architectures

unless scale requirements justify them.

---

## Monolith Structure

Backend structure:

backend/
├── apps/
├── core/
├── api/
├── services/
├── repositories/
├── tests/

---

## Frontend Structure

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   ├── hooks/
│   ├── services/
│   ├── store/
│   └── types/

---

# API Standards

All APIs must:
- use REST
- use /api/v1/
- return JSON
- use JWT authentication
- support pagination
- validate inputs

Example:

POST /api/v1/auth/login
GET /api/v1/expenses
POST /api/v1/expenses

---

# Authentication Standards

Required:
- JWT authentication
- refresh token rotation
- password hashing using bcrypt

Disallowed:
- session-based auth
- plaintext secrets

---

# Multi-Tenant SaaS Standards

All SaaS systems must support:
- organization ownership
- tenant isolation
- RBAC

Minimum roles:
- admin
- manager
- employee

---

# Coding Standards

## Python

Required:
- type hints
- service layer architecture
- repository pattern
- linting with ruff
- formatting with black

---

## React

Required:
- functional components
- hooks
- TypeScript interfaces
- reusable components

Disallowed:
- class components

---

# Testing Standards

Backend:
- pytest

Frontend:
- vitest

Minimum:
- API tests
- service tests

---

# Git Standards

Branch naming:

feature/<feature-name>
fix/<bug-name>

Commit format:

feat: add auth api
fix: correct token validation

---

# Pull Request Standards

Every PR must:
- include summary
- pass tests
- pass linting
- avoid unrelated changes

PR size should remain small.

---

# CI/CD Standards

GitHub Actions only.

Pipeline stages:
1. lint
2. test
3. build
4. deploy

---

# AI Agent Operating Rules

## Product Owner Agent

Responsibilities:
- requirements analysis
- task breakdown
- sprint planning

Cannot:
- modify source code

---

## Architect Agent

Responsibilities:
- architecture
- API contracts
- DB schemas

Cannot:
- implement UI features

---

## Frontend Agent

Allowed paths:
- frontend/

Cannot modify:
- backend/
- infra/

---

## Backend Agent

Allowed paths:
- backend/

Cannot modify:
- frontend/

---

## DevOps Agent

Allowed paths:
- .github/
- infra/

Cannot modify:
- frontend/
- backend/

---

# Cost Constraints

System must:
- run locally
- support low-cost deployment

Avoid:
- expensive managed services
- multi-cloud architecture
- unnecessary infrastructure

Monthly infrastructure target:
< $50/month

---

# Performance Constraints

Target:
- API response time < 300ms
- page load < 2s

Avoid:
- unnecessary abstractions
- overengineered patterns

---

# Security Standards

Required:
- HTTPS
- input validation
- rate limiting
- RBAC
- environment variables for secrets

Disallowed:
- hardcoded secrets
- unrestricted admin access

---

# Documentation Standards

Every major feature must include:
- README updates
- API documentation
- architecture notes

---

# Engineering Philosophy

Prefer:
- simple systems
- maintainable code
- explicit architecture
- predictable behavior

Avoid:
- unnecessary complexity
- trendy architecture
- premature scaling

---

# Cloud Standards

Primary cloud provider:
- Hetzner Cloud

Allowed:
- Single VPS deployments
- Docker Compose deployments
- Terraform provisioning

Disallowed initially:
- Kubernetes
- Multi-cloud
- Complex orchestration
- Service mesh

Infrastructure must:
- remain cost efficient
- support rapid deployment
- minimize operational overhea

---

# Deployment Architecture

Production deployment standard:

Internet
    ↓
Nginx
    ↓
React Frontend Container
    ↓
Django Backend Container
    ↓
PostgreSQL
    ↓
Redis

Deployment method:
- Docker Compose
- GitHub Actions CI/CD
- Single VPS initially

Scaling approach:
- Vertical scaling first
- Horizontal scaling later only if necessary