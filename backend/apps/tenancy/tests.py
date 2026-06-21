"""Cross-tenant isolation tests (schema-per-tenant).

Run with the django-tenants test runner (configured via TEST_RUNNER):
    python manage.py test apps.tenancy
"""
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context

from apps.accounts.models import User
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
