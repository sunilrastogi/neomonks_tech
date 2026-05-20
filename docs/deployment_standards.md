# Deployment Standards

# Deployment Philosophy

Deployments must be:
- repeatable
- automated
- observable
- reversible

---

# Approved Infrastructure

Primary provider:
- Hetzner Cloud

Preferred deployment:
- Single VPS
- Docker Compose

---

# Container Standards

All services must:
- run in Docker
- support health checks
- use environment variables

---

# Required Services

Production stack:

- frontend
- backend
- postgres
- redis
- nginx

---

# CI/CD Standards

Use:
- GitHub Actions

Pipeline stages:
1. lint
2. test
3. build
4. deploy

---

# Deployment Strategy

Preferred:
- rolling deployment
- zero downtime where possible

---

# Environment Separation

Required environments:
- local
- staging
- production

Never share secrets across environments.

---

# Secrets Management

Use:
- environment variables
- GitHub secrets

Never:
- commit secrets
- hardcode credentials

---

# Monitoring

Required:
- uptime monitoring
- error logging
- CPU/memory tracking

Preferred tools:
- Uptime Kuma
- Grafana
- Loki

---

# Backup Standards

Required:
- daily database backups
- backup verification
- restore testing

---

# Rollback Standards

Every deployment must support:
- rollback
- previous image restoration

---

# Infrastructure as Code

Preferred:
- Terraform

Avoid:
- manual infrastructure changes

---

# SSL Standards

Required:
- HTTPS
- Let's Encrypt
- automatic renewal