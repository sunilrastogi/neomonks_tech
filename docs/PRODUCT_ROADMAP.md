# NeoMonks Core — Product Maturity Roadmap

Plan for taking NeoMonks Core from an internal multi-agent SDLC tool to a product
organisations can buy and self-host or consume as SaaS.

> Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Positioning (the wedge)

Sell the **governed AI engineering org** — PO → Architect → dev agents → human PR
gate, with audit, cost control, and the ability to run **self-hosted with local
LLMs**. The differentiator versus Devin / Copilot Workspace / Factory is
**control, privacy, and on-prem** for regulated / privacy-sensitive buyers.

- Lead deployment model: **self-hosted (Docker Compose → Helm)**, with managed
  SaaS as the easy on-ramp.
- Pricing: seat-based for reviewers + usage-based for agent runs/tokens, with
  hard org spend caps.

---

## Checkpoint 1 — Repo hygiene & production-safe settings  `[x]`

Small, removes active liabilities, no new product surface.

- [x] Save this roadmap to `docs/PRODUCT_ROADMAP.md`
- [x] Confirm `.env` is gitignored and never committed (it is)
- [x] Add `.env.example` documenting every environment variable
- [x] Declare `python-dotenv` and `cryptography` in `requirements.txt`
- [x] Make `settings.py` env-driven and load `.env`:
  - [x] `DJANGO_SECRET_KEY` from env (refuses insecure default when not DEBUG)
  - [x] `DJANGO_DEBUG` from env (defaults to `False` — production-safe)
  - [x] `DJANGO_ALLOWED_HOSTS` from env
  - [x] Opt-in HTTPS/security headers via `DJANGO_SECURE=True`
- [ ] **Action for owner:** rotate the GitHub PAT currently in local `.env`
      (it was never committed, but treat any key that has left the machine as
      compromised).

## Checkpoint 2 — Encrypt secrets at rest  `[ ]`

`PlatformConfiguration` stores API keys / DB password / GitHub token in
plaintext columns. Encrypt them at rest.

- [ ] Symmetric encryption (Fernet via `cryptography`) keyed by
      `CONFIG_ENCRYPTION_KEY` from env / secret manager
- [ ] Transparent encrypt-on-write / decrypt-on-read for secret fields
- [ ] Migration to encrypt existing rows
- [ ] Never log decrypted secrets; keep the masked read API
- [ ] Key rotation story documented

## Checkpoint 3 — Auth, RBAC & multi-tenancy  `[ ]`

The real foundation. Design doc first, then implement.

- [ ] Design doc: tenancy model (Org → Workspace → Product), role model
      (Owner / Admin / Reviewer / Viewer), token model (user session + API keys)
- [ ] Replace `AllowAny` default permission; require auth on all API
- [ ] OIDC / SSO support for enterprise
- [ ] Per-org isolation enforced on every model and query
- [ ] Move `PlatformConfiguration` from global singleton to per-org/workspace
- [ ] Audit: every privileged action attributed to a user

---

## Later phases (not yet scheduled in detail)

### Trust & reliability
- [ ] **Sandbox agent execution** — containerised runs, no host access,
      egress allow-list, resource limits (agents currently run shell + git on host)
- [ ] **Cost governance** — per-org/run token budgets, rate limits, hard spend caps
- [ ] **Audit log** — promote `WorkflowEvent` to an immutable, exportable audit trail
- [ ] **Quality gates** — block tasks from the review gate until the customer's
      CI (tests/lint/typecheck) passes
- [ ] **Eval harness** — task success rate, diff-acceptance, rework count;
      enables safe model swaps and is a sales asset

### Architecture maturity
- [ ] Rebuild the single-file `dashboard.html` as a real SPA (README already
      advertises React/TS/Vite)
- [ ] Replace the thread-pool loop with a durable job queue (Celery/RQ/Temporal)
- [ ] Fix migration discipline (live Postgres schema has drifted ahead of migrations)
- [ ] Make agents actually consume `PlatformConfiguration` (today they read model/
      keys from `settings`/env, so the LLM provider toggle is not yet wired through)

### Productization & GTM
- [ ] Docker Compose + Helm chart for self-host
- [ ] Billing / metering integration
- [ ] SOC 2 Type II evidence trail (audit log + RBAC + encryption are prerequisites)
- [ ] Guided onboarding: "first requirement → first PR in 10 minutes"
- [ ] Curated starter stacks built on the existing template scaffolding

---

## Suggested sequencing

1. Checkpoint 1 — hygiene & settings  ← _current_
2. Checkpoint 2 — secrets encryption
3. Checkpoint 3 — auth + multi-tenancy
4. Sandbox + cost caps + CI gates
5. Frontend rebuild + job queue
6. Eval harness + audit/export
7. Packaging (Helm, billing, docs)
