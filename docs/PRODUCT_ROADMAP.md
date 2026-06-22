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

## Checkpoint 2 — Encrypt secrets at rest  `[x]`

`PlatformConfiguration` stores API keys / DB password / GitHub token in
plaintext columns. Encrypt them at rest.

- [x] Symmetric encryption (Fernet via `cryptography`) keyed by
      `CONFIG_ENCRYPTION_KEY` from env (`apps/workflow/crypto.py`); derived from
      `SECRET_KEY` in DEBUG, required explicitly in production
- [x] Transparent encrypt-on-write / decrypt-on-read field
      (`EncryptedCharField` in `apps/workflow/fields.py`); legacy plaintext rows
      stay readable and re-encrypt on next save
- [x] Migration written to encrypt existing rows (migration `0005`)
- [x] **Applied migration `0005`** — existing row encrypted; verified live that
      the DB column holds ciphertext while ORM reads return plaintext
- [x] Never log decrypted secrets; masked read API unchanged
      (`github_token_masked` etc. still only expose the last 4 chars)
- [x] Key rotation story: rotating `CONFIG_ENCRYPTION_KEY` invalidates stored
      ciphertext; `decrypt_secret` fails safe to empty so the app keeps running,
      then re-enter secrets in the Configurations tab to re-encrypt with the new key

> Encryption logic verified without the DB: round-trip, no double-encrypt,
> legacy-plaintext passthrough, field encrypt/decrypt, 200-char key fits in 1024,
> and masking still hides the raw secret. Only the live `migrate` apply + DB
> round-trip remain.

## Checkpoint 3 — Auth, RBAC & multi-tenancy  `[~]`

SaaS, subdomain-per-tenant, SSO (Azure AD) + email/password, seat packages +
pay-as-you-go. Full design in [`AUTH_TENANCY_DESIGN.md`](AUTH_TENANCY_DESIGN.md).

- [x] Design doc written (schema-per-tenant via django-tenants)
- [x] **3a** Tenancy core: `apps.tenancy` (Organization/Domain), `apps.accounts`
      custom email `User`, SHARED/TENANT split, `TenantMainMiddleware`, router.
      Validated (schema auto-creation, cross-tenant isolation, subdomain routing).
      **Live DB cut over**: `public` control-plane + `demo` tenant (demo.localhost)
      with 14 seeded agents + an owner user.
- [x] **3b** Authn: email/password login scoped per tenant (`/login/`,
      `/logout/`), sessions, `/api/v1/auth/me/`, change-password, hashed API keys
      (`Api-Key` header auth + management endpoints). DRF default flipped to
      `IsAuthenticated`; realtime/dashboard endpoints gated. Verified end-to-end.
      Password reset via email implemented (request + confirm API, reset page,
      env-driven email backend — console in dev, SMTP in prod once configured).
- [x] **3c** Tenant-context for background work: `submit()` captures the caller's
      schema and re-enters it in the worker; standalone loop iterates all tenants
      (`iterate_all_tenants`, `run_loop --schema`); executor semaphore + planner
      keys schema-qualified. Automated isolation tests (4) pass: product + user
      isolation, per-tenant `PlatformConfiguration`, `submit` schema preservation.
      _(No org columns needed — schema is the boundary.)_
- [x] **3d** RBAC: Owner/Admin/Member/Viewer hierarchy. `WorkflowRolePermission`
      (read=Viewer+, write=Member+, delete=Admin+) as DRF default; `IsOrgAdmin`
      gates API-key + user management and the realtime config/Ollama endpoints.
      Admin user-management endpoints (`/api/v1/auth/users/`, create/list/update/
      deactivate; only Owner grants Owner). 6 RBAC tests pass.
- [x] **3e** SSO (Azure AD / OIDC) per-tenant: `OrgSSOConfig` (encrypted secret),
      authorization-code flow (`/sso/login/` + `/sso/callback/`) over discovery →
      token → userinfo, JIT provisioning with domain allow-list + default role,
      admin config API, "Sign in with SSO" on the login page. 6 SSO tests pass.
      _Live Azure verification still pending your app registration (creds only)._
- [x] **3f** Billing: shared `apps.billing` (`Subscription` + `UsageRecord` keyed
      by Organization). Seat packages + enforcement on user creation (HTTP 402
      when full); pay-as-you-go usage metering (AGENT_RUN recorded by the executor);
      subscription + usage API; Stripe checkout + signature-verified webhook
      (graceful when keys absent). 5 billing tests pass (15 total).

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
