# Backend Patterns

# Approved Stack

- Django
- Django REST Framework
- PostgreSQL
- Redis

---

# Backend Structure

backend/
├── apps/
├── core/
├── services/
├── repositories/
├── tests/

---

# Layer Responsibilities

Views:
- request parsing
- response formatting

Services:
- business logic

Repositories:
- database access

Models:
- persistence definitions

---

# API Standards

All APIs:
- versioned
- RESTful
- JSON-based

Prefix:

/api/v1/

---

# Authentication

Required:
- JWT
- refresh tokens
- RBAC

Use:
- django-simplejwt

---

# Database Standards

Primary DB:
- PostgreSQL

Use:
- UUID primary keys
- timestamps
- soft deletes where useful

---

# Query Standards

Avoid:
- N+1 queries
- large ORM loops

Use:
- select_related
- prefetch_related

---

# Validation

Validation order:
1. serializer validation
2. service validation
3. domain validation

---

# Error Handling

Return structured errors:

{
  \"error\": {
    \"code\": \"INVALID_INPUT\",
    \"message\": \"Invalid request\"
  }
}

---

# Async Tasks

Use:
- Celery + Redis

Only for:
- emails
- reports
- long-running jobs

Avoid unnecessary async workflows.

---

# Security Standards

Required:
- input sanitization
- RBAC
- rate limiting
- environment-based secrets

---

# Testing Standards

Required:
- API tests
- service tests
- permission tests
- serializer tests

---

# Migration Rules

Every schema change must:
- include migration
- be reversible
- avoid destructive operations