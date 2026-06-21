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

### D1. Isolation strategy — **Recommend: shared DB, row-level (`org_id`)**
| Option | Isolation | Ops cost | When |
|---|---|---|---|
| **Row-level `org_id` FK (recommend)** | Logical | Low | Standard B2B SaaS; scales to thousands of tenants |
| Schema-per-tenant (`django-tenants`) | Strong | Medium | Customers contractually require physical separation |
| DB-per-tenant | Strongest | High | A few large regulated whales |

Recommendation: **row-level** now, with a clean `TenantScopedModel` base + enforced
querysets so we *could* migrate heavy tenants to schema-per-tenant later without
rewriting business logic. This matches self-serve subdomain SaaS and PAYG.

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

## 3. Tenancy & data model

### New app: `apps.tenancy`
```
Organization
  id, name, slug (== subdomain, unique), status (ACTIVE/SUSPENDED/TRIAL)
  created_at, updated_at

User (custom, AUTH_USER_MODEL)
  email (unique), full_name, org (FK -> Organization)
  role (OWNER/ADMIN/MEMBER/VIEWER)
  is_active, auth_source (PASSWORD/SSO), last_login, date_joined
  password (unused when auth_source=SSO)

OrgSSOConfig            # per-org OIDC settings (D4)
  org (OneToOne), enabled, provider (AZURE_AD/GENERIC_OIDC)
  oidc_client_id, oidc_client_secret (encrypted), oidc_discovery_url
  default_role_for_new_users, allowed_email_domains

Subscription            # mirror of Stripe state (D5)
  org (OneToOne), stripe_customer_id, stripe_subscription_id
  plan, seats_purchased, status, current_period_end

UsageRecord             # PAYG metering
  org, kind (AGENT_RUN/LLM_TOKENS), quantity, unit_cost, occurred_at, task (nullable)

ApiKey                  # programmatic access, hashed
  org, name, prefix, hashed_key, created_by, last_used_at, revoked
```

### Tenant scoping of existing models
`Product`, `Requirement`, `ArchitectureArtifact`, `Task`, `TaskDependency`,
`FileLock`, `AgentProfile`, `PullRequestRecord`, `ApprovalRecord`,
`WorkflowEvent` — each gains `org = FK(Organization)`.

`PlatformConfiguration` — **stop being a global singleton**; becomes **one row
per org** (`org = OneToOne`). Each tenant configures its own LLM keys / GitHub /
(optional) external DB. `load()` becomes `for_org(org)`.

`created_by: CharField` → keep as-is for now (display only) or later FK to `User`.

### Enforcement pattern
```python
class TenantScopedModel(models.Model):
    org = models.ForeignKey('tenancy.Organization', on_delete=models.CASCADE)
    objects = TenantManager()        # .for_org(org) helper
    class Meta: abstract = True
```
- A `TenantManager`/`QuerySet` with `.for_org(org)`.
- Middleware sets `request.org`; a thin service/base viewset always filters by it.
- **Write path**: `perform_create` injects `request.org`; never trust client input.

---

## 4. Subdomain routing & tenant resolution

`TenantMiddleware` (early in stack):
1. Parse host → subdomain (`acme` from `acme.neomonks.app`).
2. Look up `Organization` by slug; 404 / suspended page if missing/disabled.
3. Attach `request.org`.
4. Reserved subdomains (`app`, `www`, `api`, `admin`) bypass tenant resolution
   for the marketing/control plane.

Local dev: support `acme.localhost` and a `X-Org-Slug` header fallback for tests.
`ALLOWED_HOSTS` gets a wildcard (`.neomonks.app`) in production.

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
- Object-level: every queryset filtered to `request.org` (defense in depth even
  if an id is guessed).
- Sensitive actions (delete repo, change billing, edit SSO) require ADMIN/OWNER.
- Django admin remains a **separate staff/superuser control plane** (vendor side),
  not exposed to tenants.

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

The DB currently holds one implicit tenant's data.
1. Add `apps.tenancy`, custom `User`, `Organization` (no FK swaps yet).
2. Data migration: create a `default` Organization; create an OWNER user from an
   env-provided bootstrap admin; migrate existing `auth_user` rows.
3. Add nullable `org` FK to each domain model; backfill to the `default` org;
   then make non-null.
4. Convert `PlatformConfiguration` to per-org (move the existing singleton row to
   the default org).
5. Flip DRF defaults to authenticated; add middleware; wire login.
6. Billing last (can ship behind a flag).

> Custom user model note: introducing `AUTH_USER_MODEL` after `0001` requires the
> standard "create custom user app + careful migration" dance. Because nothing
> FKs to `auth.User` today, the main work is the auth/session/admin tables. We'll
> validate on a DB copy before running against the live (drifted) Postgres.

---

## 10. Proposed implementation sub-checkpoints

Each is a reviewable stop with tests.

- **3a — Tenancy core**: `apps.tenancy`, `Organization`, custom `User`,
  `TenantMiddleware`, subdomain resolution, admin. *(no billing/SSO yet)*
- **3b — Authn**: email/password login scoped to org, sessions, logout, password
  reset; DRF `IsAuthenticated` default; API keys.
- **3c — Org scoping**: add `org` to all domain models + enforced querysets +
  cross-tenant isolation tests; `PlatformConfiguration` per-org.
- **3d — RBAC**: roles + `HasOrgRole`; user-management UI/endpoints (admin
  creates users).
- **3e — SSO (Azure AD/OIDC)**: per-org `OrgSSOConfig`, Authlib login/callback,
  JIT provisioning.
- **3f — Billing**: Stripe subscriptions, seat packages + enforcement, PAYG
  metering, webhooks.

---

## 11. Open questions for product owner

1. Confirm **D1 row-level isolation** (vs. schema-per-tenant) for v1.
2. Confirm **D2 single-org users** (vs. cross-org membership).
3. Root domain for subdomains (e.g. `*.neomonks.app`)?
4. Stripe as the billing provider — OK?
5. Seat tiers exact list (5/10/25/50/custom?) and PAYG units to meter first
   (agent runs? LLM tokens? both?).
6. Should the control plane (signup, billing portal) live on `app.` while tenant
   workspaces live on `<org>.`? (Recommended.)
