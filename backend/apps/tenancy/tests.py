"""Cross-tenant isolation tests (schema-per-tenant).

Run with the django-tenants test runner (configured via TEST_RUNNER):
    python manage.py test apps.tenancy
"""
from django.test import override_settings
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
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
