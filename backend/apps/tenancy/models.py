"""Tenant metadata models (live in the shared `public` schema).

Each :class:`Organization` is a tenant and owns its own PostgreSQL schema, which
django-tenants creates automatically on save. :class:`Domain` maps a hostname
(subdomain) to a tenant so the middleware can resolve the active schema per
request.
"""
from django.db import models
from django.db.models import TextChoices
from django_tenants.models import DomainMixin, TenantMixin


class OrgStatus(TextChoices):
    ACTIVE = "ACTIVE", "Active"
    TRIAL = "TRIAL", "Trial"
    SUSPENDED = "SUSPENDED", "Suspended"


class Organization(TenantMixin):
    """A customer tenant. `schema_name` (from TenantMixin) is the Postgres schema."""

    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=OrgStatus.choices, default=OrgStatus.TRIAL)
    created_on = models.DateField(auto_now_add=True)

    # Create/destroy the tenant's schema automatically with the row.
    auto_create_schema = True
    auto_drop_schema = False  # safety: never drop a customer's data implicitly

    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    """Hostname → tenant mapping (e.g. acme.neomonks.app → Organization 'acme')."""
    pass
