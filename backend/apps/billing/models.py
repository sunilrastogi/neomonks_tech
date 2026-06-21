"""Billing models — live in the shared (public) schema, keyed by Organization.

Subscriptions and usage are vendor-side records (one row per tenant), so they
belong in the control-plane schema rather than inside each tenant schema.
"""
from django.db import models
from django.db.models import TextChoices
from django.utils import timezone


class SubscriptionStatus(TextChoices):
    TRIALING = "TRIALING", "Trialing"
    ACTIVE = "ACTIVE", "Active"
    PAST_DUE = "PAST_DUE", "Past due"
    CANCELED = "CANCELED", "Canceled"


# Seat packages offered. Maps a plan key → included seats. Stripe Price IDs are
# configured separately (settings.STRIPE_PRICES) so pricing can change without code.
SEAT_PACKAGES = {
    "trial": 5,
    "team_5": 5,
    "team_10": 10,
    "team_25": 25,
    "team_50": 50,
}


class Subscription(models.Model):
    """One per Organization. Mirrors the authoritative state held in Stripe."""

    organization = models.OneToOneField(
        "tenancy.Organization", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.CharField(max_length=50, default="trial")
    seats_purchased = models.PositiveIntegerField(default=5)
    status = models.CharField(
        max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIALING
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="")
    current_period_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization.name}: {self.plan} ({self.seats_purchased} seats, {self.status})"

    @property
    def is_billable_active(self) -> bool:
        return self.status in (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE)


class UsageEventType(TextChoices):
    AGENT_RUN = "AGENT_RUN", "Agent run"
    LLM_TOKENS = "LLM_TOKENS", "LLM tokens"


class UsageRecord(models.Model):
    """A pay-as-you-go usage event for an organization (metered for billing)."""

    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.CASCADE, related_name="usage_records"
    )
    kind = models.CharField(max_length=20, choices=UsageEventType.choices)
    quantity = models.PositiveIntegerField(default=1)
    # Reference to the originating task (in the tenant schema) — stored as an id,
    # not an FK, since this row lives in the public schema.
    task_id = models.IntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    reported_to_stripe = models.BooleanField(default=False)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["organization", "-occurred_at"])]

    def __str__(self):
        return f"{self.organization_id} {self.kind} x{self.quantity}"
