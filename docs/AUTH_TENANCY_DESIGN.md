# Checkpoint 3 — Auth, RBAC & Multi-Tenancy: Design

Status: **DRAFT for review** — no code until this is signed off.

## 1. Product requirements (from product owner)

- **SaaS, multi-tenant** ("like Snowflake"): one deployment serves many client orgs.
- **Subdomain per client**: `acme.neomonks.app`, `globex.neomonks.app`.
- **SSO**: clients integrate their IdP (Azure AD / Entra ID first) — OIDC.
- **Email + password** fallback login.
- **User management**: org admins create/manage users.
- **Seat-based billing** in packages (5, 10, … seats) **plus pay-as-you-go**
  usage (agent runs / LLM tokens).

---

## 2. Key decisions & recommendations

> These are the decisions that shape everything else. Recommendation given for
> each; please confirm or override before implementation.

### D1. Isolation strategy — **DECIDED: schema-per-tenant (`django-tenants`)**
Each org gets its own PostgreSQL **schema**; a shared `public` schema holds only
tenant metadata. Resolved via the request subdomain. Strong isolation that suits
the "Snowflake-like" positioning.

Consequences (these *simplify* later work):
- **No `org_id` column** on business tables and **no per-query org filtering** —
  the schema *is* the boundary, set by middleware via the search path.
- `PlatformConfiguration` stays a per-schema singleton automatically (one row in
  each tenant schema) — no model change needed.
- Per-tenant `auth` → each org has its **own user table**, so email is naturally
  unique per tenant.

Trade-offs to accept: migrations run across all schemas (`migrate_schemas`);
thousands of schemas add migration time and connection/search-path overhead;
cross-tenant analytics needs deliberate aggregation. Acceptable at expected scale.

### D2. User ↔ Org cardinality — **Recommend: user belongs to one org**
Each client has its own subdomain and IdP, so a user (email) lives in exactly one
tenant. Simpler uniqueness, simpler SSO, matches the subdomain model. A
`Membership` join table (user in many orgs) is the alternative — more flexible but
adds an "active org" concept and complicates email uniqueness. We can add it later
if needed; v1 uses a direct `org` FK on the user.

### D3. Custom user model — **Recommend: yes, now**
Switch to a custom `User` with **email as the login field** and an `org` FK.
The codebase has no FK to `auth.User` and `created_by` is just a string, so the
blast radius is small — but a custom user model must be introduced with a careful
migration of the existing `auth_user` table (see §9). Doing it now (pre-customers)
is far cheaper than later.

### D4. SSO protocol — **Recommend: OIDC first (Azure AD), SAML later**
Azure AD/Entra fully supports OIDC. Use **per-org IdP config** (client id/secret/
discovery URL) stored encrypted (reuse Checkpoint 2's `EncryptedCharField`).
Library: `authlib` (clean OIDC, framework-agnostic). SAML (`python3-saml`) added
later for IdPs that need it.

### D5. Billing engine — **Recommend: Stripe**
Stripe Billing for seat subscriptions (quantity = seats, tiered packages) +
metered usage for PAYG. Stripe handles invoicing, proration, dunning, tax. We
store a mirror of subscription/seat state locally for enforcement.

---

## 3. App layout & data model (django-tenants)

Apps are split into **SHARED_APPS** (migrate to `public`) and **TENANT_APPS**
(migrate to each tenant schema).

```
SHARED_APPS  (public schema — control plane / tenant metadata)
  django_tenants
  apps.tenancy            # Organization (TenantMixin), Domain (DomainMixin)
  django.contrib.contenttypes
  + billing models (Subscription, UsageRecord) live here, keyed by Organization

TENANT_APPS  (one copy per tenant schema — the product itself)
  django.contrib.auth, admin, sessions, messages, staticfiles, postgres
  apps.accounts           # custom email User (+ role, auth_source), API keys
  apps.workflow           # Product/Requirement/Task/... unchanged
  apps.realtime
  rest_framework, django_filters
```

### `apps.tenancy` (shared)
```
Organization(TenantMixin)   # schema_name, auto_create_schema=True
  name, status (ACTIVE/SUSPENDED/TRIAL), created_on
Domain(DomainMixin)         # domain (e.g. acme.neomonks.app), tenant, is_primary
```

### `apps.accounts` (tenant) — custom user, per-tenant
```
User(AbstractUser)          # AUTH_USER_MODEL = accounts.User
  email (unique *within the schema* → unique per tenant), full_name,
  role (OWNER/ADMIN/MEMBER/VIEWER), auth_source (PASSWORD/SSO),
  is_active/is_staff, USERNAME_FIELD='email'
ApiKey                      # name, prefix, hashed_key, created_by, last_used_at, revoked
OrgSSOConfig                # per-tenant OIDC (D4): provider, client id/secret(enc),
                            # discovery_url, allowed_email_domains, default_role
```

### Existing models — **no changes needed**
`Product`, `Requirement`, `Task`, `AgentProfile`, `PlatformConfiguration`, etc.
need **no `org` column**: each tenant schema has its own copy of these tables.
`PlatformConfiguration` stays a per-schema singleton (one config per tenant).
`created_by: CharField` can later become an FK to `accounts.User`.

### Billing models (shared, keyed by Organization)
```
Subscription(org OneToOne)  stripe_customer_id, stripe_subscription_id, plan,
                            seats_purchased, status, current_period_end
UsageRecord(org)            kind (AGENT_RUN/LLM_TOKENS), quantity, unit_cost, occurred_at
```

### Enforcement
- `django_tenants.middleware.main.TenantMainMiddleware` sets the active schema
  from the request host — all ORM queries are automatically scoped to that schema.
- `DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']`.
- Background jobs (the autonomous loop) must run inside `tenant_context(org)` so
  worker threads target the right schema.

---

## 4. Subdomain routing & tenant resolution

`TenantMainMiddleware` (first in stack) maps the request host → `Domain` →
`Organization` → sets the Postgres `search_path` to that schema. The `public`
tenant (a special Organization with `schema_name='public'`) serves the control
plane on the bare/`app` domain.

- Reserved subdomains (`app`, `www`, `api`, `admin`) map to the public tenant.
- Unknown subdomain → 404 (configurable landing).
- Local dev: `acme.localhost` works in browsers; tests use
  `django_tenants.test.client.TenantClient` / `tenant_context`.
- Production `ALLOWED_HOSTS` includes the wildcard root (e.g. `.neomonks.app`).

---

## 5. Authentication

- **Email + password**: Django auth backend over the custom user, scoped so the
  login only authenticates users **within `request.org`**.
- **SSO (OIDC / Azure AD)**: per-org login button → Authlib OIDC code flow →
  on callback, match/provision user by email (respecting `allowed_email_domains`
  and `default_role_for_new_users`), create a session.
- **Sessions** for the dashboard (browser). **API keys** (hashed, §3) for
  programmatic/CI access via a custom DRF authentication class.
- **Just-in-time provisioning** for SSO users (optional, org-controlled).

---

## 6. Authorization / RBAC

Roles (per org): **OWNER** (billing + everything), **ADMIN** (manage users/config,
no billing), **MEMBER** (create requirements, run agents, review), **VIEWER**
(read-only).

- DRF: replace `AllowAny` default with `IsAuthenticated` + a
  `HasOrgRole(min_role=...)` permission.
- Cross-tenant reads are prevented by the schema boundary itself; RBAC governs
  *what a user can do within their own tenant*.
- Sensitive actions (delete repo, change billing, edit SSO) require ADMIN/OWNER.
- Tenant admin lives inside each schema (per-tenant). A separate vendor control
  plane on the public schema is added with billing (3f).

---

## 7. Billing & seats

- **Packages**: Stripe Prices for seat tiers (5/10/25/…); subscription quantity =
  seats. `seats_purchased` mirrored locally.
- **Seat enforcement**: creating/activating a user checks
  `active_users < seats_purchased`; over-limit → block with upgrade prompt.
- **PAYG**: emit `UsageRecord` on agent run / token spend; report metered usage to
  Stripe; enforce optional hard spend caps (ties into the later "cost governance"
  roadmap item).
- **Webhooks**: Stripe → update `Subscription` status (paid, past_due, canceled →
  suspend org).
- **Trials**: `status=TRIAL` with a seat/usage allowance.

---

## 8. Security considerations

- Cross-tenant leakage is the top risk → enforce org filter centrally, add
  automated tests that assert org A cannot read/write org B for **every** endpoint.
- All per-org secrets encrypted (Checkpoint 2 field).
- API keys stored hashed; shown once.
- Rate-limit auth endpoints; lock out brute force.
- Subdomain cookie scoping; CSRF trusted origins per the wildcard domain.

---

## 9. Migration / rollout plan

The live DB holds only trivial seed/dev data (1 product, 14 seeded agents,
0 requirements/tasks/users, all in `public`), so conversion is low-risk and the
data is re-seedable.

**Validation first (done in 3a):** build everything against a *fresh throwaway
database* — prove `migrate_schemas --shared`, tenant creation (auto-creates a
schema + runs tenant migrations), per-tenant user creation, and subdomain routing.

**Live cutover (gated, with backup):**
1. `pg_dump` the live DB.
2. Move the existing public-schema business tables out of the way (they belong in
   a tenant schema now, not `public`).
3. `migrate_schemas --shared` to build the public/control-plane schema.
4. Create the `public` tenant + a first real Organization (its schema is created
   and migrated automatically), map its Domain.
5. Re-seed agents / recreate the single product inside the tenant schema (cheaper
   than data-preserving table moves given the trivial volume).
6. Create the first OWNER user in the tenant.

> Because the live data is disposable seed data, we prefer a clean rebuild under
> django-tenants over a fragile data-preserving migration of the drifted schema.

---

## 10. Proposed implementation sub-checkpoints

Each is a reviewable stop with tests.

- **3a — Tenancy core**: django-tenants wired up; `apps.tenancy`
  (`Organization`/`Domain`), `apps.accounts` custom email `User`,
  SHARED/TENANT app split, `TenantMainMiddleware`, router. Validated on a fresh
  DB (schema creation + subdomain routing). *(no billing/SSO yet)*
- **3b — Authn**: email/password login (per-tenant), sessions, logout, password
  reset; DRF `IsAuthenticated` default; API keys.
- **3c — Tenant-context & isolation tests**: run the autonomous loop / background
  threads inside `tenant_context`; cross-tenant isolation tests; confirm
  `PlatformConfiguration` is per-tenant. *(No org columns needed — schema is the
  boundary.)*
- **3d — RBAC**: roles + `HasOrgRole`; user-management endpoints (admin creates
  users within the tenant).
- **3e — SSO (Azure AD/OIDC)**: per-tenant `OrgSSOConfig`, Authlib login/callback,
  JIT provisioning.
- **3f — Billing**: Stripe subscriptions (shared schema), seat packages +
  enforcement, PAYG metering, webhooks, vendor control plane on `public`.

---

## 11. Open questions for product owner

1. ~~D1 isolation~~ — **decided: schema-per-tenant**.
2. **D2 single-org users** confirmed by the schema model (users live per schema).
3. Root domain for subdomains (e.g. `*.neomonks.app`)? — needed for 3b/prod hosts.
4. Stripe as the billing provider — OK? (needed at 3f)
5. Seat tiers exact list (5/10/25/50/custom?) and PAYG units to meter first
   (agent runs? LLM tokens? both?). (needed at 3f)
6. Control plane (signup, billing portal) on `app.` while tenant workspaces live
   on `<org>.`? (Recommended.)
