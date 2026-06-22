"""Cross-tenant isolation tests (schema-per-tenant).

Run with the django-tenants test runner (configured via TEST_RUNNER):
    python manage.py test apps.tenancy
"""
import re
from unittest.mock import patch

from django.core import mail
from django.test import Client, override_settings
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context
from rest_framework.test import APIClient

from apps.accounts import oidc
from apps.accounts.models import OrgSSOConfig, Role, User
from apps.tenancy.models import Domain, Organization
from apps.workflow.autonomous.thread_pool import submit
from apps.workflow.models import PlatformConfiguration, Product


class TenantIsolationTests(TenantTestCase):
    """`self.tenant` is auto-created by TenantTestCase; we add a second tenant."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Tenants/domains are shared models — must be created in the public schema.
        with schema_context(get_public_schema_name()):
            cls.other = Organization(schema_name="test_other", name="Other Org")
            cls.other.save(verbosity=0)
            Domain.objects.create(domain="other.test.com", tenant=cls.other, is_primary=True)

    @classmethod
    def tearDownClass(cls):
        with schema_context(get_public_schema_name()):
            cls.other.delete(force_drop=True)
        super().tearDownClass()

    def test_product_data_is_isolated_between_tenants(self):
        Product.objects.create(name="P1", slug="p1")
        self.assertEqual(Product.objects.count(), 1)

        with tenant_context(self.other):
            self.assertEqual(Product.objects.count(), 0, "other tenant must not see P1")
            Product.objects.create(name="P2", slug="p2")
            self.assertEqual(Product.objects.count(), 1)

        # Back in the primary tenant: still only P1.
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Product.objects.first().name, "P1")

    def test_users_are_isolated_between_tenants(self):
        User.objects.create_user("a@one.test", password="x")
        with tenant_context(self.other):
            self.assertFalse(User.objects.filter(email="a@one.test").exists())

    def test_platform_configuration_is_per_tenant(self):
        c1 = PlatformConfiguration.load()
        c1.github_repo = "org/a"
        c1.save()

        with tenant_context(self.other):
            c2 = PlatformConfiguration.load()
            c2.github_repo = "org/b"
            c2.save()

        self.assertEqual(PlatformConfiguration.load().github_repo, "org/a")
        with tenant_context(self.other):
            self.assertEqual(PlatformConfiguration.load().github_repo, "org/b")

    def test_submit_preserves_tenant_schema(self):
        from django.db import connection

        captured = {}

        def job():
            from django.db import connection as worker_conn
            captured["schema"] = worker_conn.schema_name

        submit(job).result(timeout=15)
        self.assertEqual(captured["schema"], connection.schema_name)


@override_settings(ALLOWED_HOSTS=["*"])
class RBACTests(TenantTestCase):
    """Role-tiered access within a single tenant."""

    def setUp(self):
        super().setUp()
        # Product creation normally spawns the scaffolder on a background thread;
        # disable it so tests don't kick off git/filesystem work.
        from unittest.mock import patch

        from apps.workflow.api.views import ProductViewSet
        patcher = patch.object(ProductViewSet, "_scaffold_async", lambda *a, **k: None)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.host = self.tenant.get_primary_domain().domain
        self.viewer = User.objects.create_user("viewer@t.test", password="pw", role=Role.VIEWER)
        self.member = User.objects.create_user("member@t.test", password="pw", role=Role.MEMBER)
        self.admin = User.objects.create_user("admin@t.test", password="pw", role=Role.ADMIN)
        self.owner = User.objects.create_user("owner@t.test", password="pw", role=Role.OWNER)
        self.api = APIClient()

    def _as(self, user):
        self.api.force_authenticate(user=user)

    def test_viewer_can_read_but_not_create(self):
        self._as(self.viewer)
        self.assertEqual(self.api.get("/api/v1/workflow/products/", HTTP_HOST=self.host).status_code, 200)
        r = self.api.post("/api/v1/workflow/products/", {"name": "X", "slug": "x"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 403)

    def test_member_can_create_but_not_delete(self):
        self._as(self.member)
        r = self.api.post("/api/v1/workflow/products/", {"name": "Y", "slug": "y"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 201)
        pid = r.json()["id"]
        d = self.api.delete(f"/api/v1/workflow/products/{pid}/", HTTP_HOST=self.host)
        self.assertEqual(d.status_code, 403)

    def test_admin_can_delete(self):
        self._as(self.admin)
        r = self.api.post("/api/v1/workflow/products/", {"name": "Z", "slug": "z"},
                          format="json", HTTP_HOST=self.host)
        pid = r.json()["id"]
        d = self.api.delete(f"/api/v1/workflow/products/{pid}/", HTTP_HOST=self.host)
        self.assertIn(d.status_code, (200, 204))

    def test_user_management_is_admin_only(self):
        self._as(self.member)
        self.assertEqual(self.api.get("/api/v1/auth/users/", HTTP_HOST=self.host).status_code, 403)
        self._as(self.admin)
        self.assertEqual(self.api.get("/api/v1/auth/users/", HTTP_HOST=self.host).status_code, 200)

    def test_only_owner_can_grant_owner_role(self):
        self._as(self.admin)
        r = self.api.post("/api/v1/auth/users/",
                          {"email": "n1@t.test", "role": Role.OWNER, "password": "password123"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 403)
        self._as(self.owner)
        r = self.api.post("/api/v1/auth/users/",
                          {"email": "n2@t.test", "role": Role.OWNER, "password": "password123"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 201)

    def test_admin_can_create_member(self):
        self._as(self.admin)
        r = self.api.post("/api/v1/auth/users/",
                          {"email": "m2@t.test", "role": Role.MEMBER, "password": "password123"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(User.objects.filter(email="m2@t.test", role=Role.MEMBER).exists())


@override_settings(ALLOWED_HOSTS=["*"])
class BillingTests(TenantTestCase):
    """Seat enforcement, usage metering, subscription API, and webhook handling."""

    def setUp(self):
        super().setUp()
        from apps.billing.services import get_or_create_subscription

        self.host = self.tenant.get_primary_domain().domain
        self.sub = get_or_create_subscription(self.tenant)
        self.sub.seats_purchased = 2
        self.sub.status = "ACTIVE"
        self.sub.save()
        # Creating this admin directly counts as 1 active seat.
        self.admin = User.objects.create_user("admin@b.test", password="pw", role=Role.ADMIN)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_seat_limit_is_enforced(self):
        # 1 used, 2 seats → one more allowed (→2), then blocked.
        r1 = self.api.post("/api/v1/auth/users/",
                           {"email": "u1@b.test", "role": Role.MEMBER, "password": "password123"},
                           format="json", HTTP_HOST=self.host)
        self.assertEqual(r1.status_code, 201)
        r2 = self.api.post("/api/v1/auth/users/",
                           {"email": "u2@b.test", "role": Role.MEMBER, "password": "password123"},
                           format="json", HTTP_HOST=self.host)
        self.assertEqual(r2.status_code, 402)  # seat limit

    def test_subscription_endpoint_reports_seats(self):
        r = self.api.get("/api/v1/billing/subscription/", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["seats_purchased"], 2)
        self.assertIn("seats_used", body)
        self.assertIn("seats_available", body)

    def test_usage_recording_and_summary(self):
        from apps.billing.models import UsageEventType
        from apps.billing.services import record_usage

        record_usage(UsageEventType.AGENT_RUN, quantity=2, task_id=5)
        record_usage(UsageEventType.AGENT_RUN, quantity=1)
        r = self.api.get("/api/v1/billing/usage/", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["usage"].get("AGENT_RUN"), 3)

    def test_webhook_event_updates_subscription(self):
        from apps.billing.services import apply_webhook_event

        self.sub.stripe_customer_id = "cus_test"
        self.sub.save()
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {
                "customer": "cus_test",
                "status": "past_due",
                "items": {"data": [{"quantity": 10}]},
            }},
        }
        handled = apply_webhook_event(event)
        self.sub.refresh_from_db()
        self.assertTrue(handled)
        self.assertEqual(self.sub.seats_purchased, 10)
        self.assertEqual(self.sub.status, "PAST_DUE")

    def test_checkout_requires_stripe_config(self):
        owner = User.objects.create_user("owner@b.test", password="pw", role=Role.OWNER)
        self.api.force_authenticate(owner)
        r = self.api.post("/api/v1/billing/checkout/", {"plan": "team_10"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 503)  # billing not configured (no Stripe key)


class SSOProvisioningTests(TenantTestCase):
    """Pure provisioning logic for OIDC sign-in."""

    def _cfg(self, **over):
        cfg = OrgSSOConfig.load()
        cfg.enabled = True
        cfg.discovery_url = "https://idp.example/.well-known/openid-configuration"
        cfg.client_id = "cid"
        cfg.auto_provision = True
        cfg.default_role = Role.MEMBER
        for k, v in over.items():
            setattr(cfg, k, v)
        cfg.save()
        return cfg

    def test_auto_provisions_user_with_default_role(self):
        cfg = self._cfg(default_role=Role.ADMIN)
        user = oidc.provision_user(cfg, {"email": "New@Demo.test", "name": "New User"})
        self.assertEqual(user.email, "new@demo.test")
        self.assertEqual(user.role, Role.ADMIN)
        self.assertEqual(user.auth_source, "SSO")
        self.assertFalse(user.has_usable_password())

    def test_rejects_disallowed_domain(self):
        cfg = self._cfg(allowed_email_domains="acme.com, demo.test")
        with self.assertRaises(oidc.SSODomainNotAllowed):
            oidc.provision_user(cfg, {"email": "bob@evil.com"})

    def test_returns_existing_user(self):
        cfg = self._cfg()
        existing = User.objects.create_user("exists@demo.test", password="pw", role=Role.OWNER)
        user = oidc.provision_user(cfg, {"email": "exists@demo.test"})
        self.assertEqual(user.pk, existing.pk)
        self.assertEqual(user.role, Role.OWNER)  # unchanged

    def test_no_autoprovision_raises_for_unknown_user(self):
        cfg = self._cfg(auto_provision=False)
        with self.assertRaises(oidc.SSOError):
            oidc.provision_user(cfg, {"email": "ghost@demo.test"})


@override_settings(ALLOWED_HOSTS=["*"])
class SSOCallbackTests(TenantTestCase):
    @patch("apps.accounts.oidc.fetch_userinfo")
    @patch("apps.accounts.oidc.exchange_code")
    def test_callback_provisions_and_logs_in(self, m_exchange, m_userinfo):
        m_exchange.return_value = {"access_token": "tok"}
        m_userinfo.return_value = {"email": "sso@demo.test", "name": "SSO User"}
        cfg = OrgSSOConfig.load()
        cfg.enabled = True
        cfg.discovery_url = "https://idp.example/.well-known/openid-configuration"
        cfg.client_id = "cid"
        cfg.save()

        host = self.tenant.get_primary_domain().domain
        client = Client()
        session = client.session
        session["sso_state"] = "st123"
        session.save()

        resp = client.get("/sso/callback/?code=abc&state=st123", HTTP_HOST=host)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(email="sso@demo.test", auth_source="SSO").exists())

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_callback_rejects_bad_state(self):
        cfg = OrgSSOConfig.load()
        cfg.enabled = True
        cfg.save()
        host = self.tenant.get_primary_domain().domain
        resp = Client().get("/sso/callback/?code=abc&state=wrong", HTTP_HOST=host)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("sso=badstate", resp.url)


@override_settings(ALLOWED_HOSTS=["*"],
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.host = self.tenant.get_primary_domain().domain
        self.user = User.objects.create_user("reset@demo.test", password="OldPass123", role=Role.MEMBER)
        self.api = APIClient()
        mail.outbox = []

    def test_request_sends_email_then_confirm_changes_password(self):
        r = self.api.post("/api/v1/auth/password-reset/", {"email": "reset@demo.test"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        m = re.search(r"uid=([^&\s]+)&token=([^&\s]+)", mail.outbox[0].body)
        self.assertIsNotNone(m)
        uid, token = m.group(1), m.group(2)

        c = self.api.post("/api/v1/auth/password-reset/confirm/",
                          {"uid": uid, "token": token, "new_password": "BrandNew123"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(c.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNew123"))

    def test_unknown_email_still_returns_200_without_sending(self):
        r = self.api.post("/api/v1/auth/password-reset/", {"email": "nobody@demo.test"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_token_is_rejected(self):
        c = self.api.post("/api/v1/auth/password-reset/confirm/",
                          {"uid": "bad", "token": "bad", "new_password": "whatever123"},
                          format="json", HTTP_HOST=self.host)
        self.assertEqual(c.status_code, 400)
