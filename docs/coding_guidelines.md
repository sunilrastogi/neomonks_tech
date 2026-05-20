# Neomonks Tech Coding Guidelines

# General Principles

Code must be:
- readable
- maintainable
- testable
- explicit
- modular

Prefer clarity over cleverness.

---

# Python Standards

## Required

- Python 3.12+
- type hints
- dataclasses or Pydantic where appropriate
- Ruff linting
- Black formatting

---

# Backend Structure

Preferred structure:

backend/
├── apps/
├── core/
├── services/
├── repositories/
├── tests/

---

# Django Standards

Use:
- Django REST Framework
- service layer architecture
- repository pattern where useful

Avoid:
- business logic in views
- fat serializers
- direct ORM logic in views

---

# Naming Conventions

## Python

Classes:
PascalCase

Functions:
snake_case

Constants:
UPPER_SNAKE_CASE

Private methods:
_prefix

---

# React Standards

Use:
- functional components
- hooks
- TypeScript
- feature-based organization

Avoid:
- class components
- excessive prop drilling
- duplicated UI logic

---

# TypeScript Rules

Required:
- strict mode
- explicit interfaces
- proper typing

Avoid:
- any
- implicit types

---

# Component Structure

Preferred:

src/
├── components/
├── pages/
├── hooks/
├── services/
├── types/

---

# API Layer

API logic must exist in:
- services/

Never call fetch directly from UI components.

---

# Error Handling

All services must:
- handle exceptions gracefully
- return structured errors
- log critical failures

Avoid silent failures.

---

# Logging Standards

Use structured logging.

Log:
- errors
- warnings
- security events
- deployment events

Do not log:
- passwords
- secrets
- tokens

---

# Testing Standards

Backend:
- pytest

Frontend:
- vitest

Minimum coverage:
- services
- APIs
- critical business logic

---

# Git Standards

Branch names:

feature/<name>
fix/<name>

Commit style:

feat: add login api
fix: resolve token refresh issue

---

# Pull Requests

Every PR must:
- solve one problem
- remain focused
- pass tests
- include summary

Avoid giant PRs.

---

# AI Agent Rules

Agents must:
- modify only owned directories
- avoid unrelated refactors
- generate deterministic code
- follow repository standards

Human review is required before merge.