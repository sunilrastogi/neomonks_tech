"""Billing logic: subscriptions, seat enforcement, usage metering, Stripe.

All Stripe calls are guarded so the app runs (and tests pass) without keys
configured — they raise BillingNotConfigured only when a billing action is
actually attempted.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from rest_framework.exceptions import APIException

from apps.billing.models import (
    SEAT_PACKAGES, Subscription, SubscriptionStatus, UsageEventType, UsageRecord,
)

logger = logging.getLogger(__name__)


class SeatLimitExceeded(APIException):
    status_code = 402
    default_detail = "Seat limit reached for your plan. Upgrade to add more users."
    default_code = "seat_limit_exceeded"


class BillingNotConfigured(APIException):
    status_code = 503
    default_detail = "Billing is not configured on this deployment."
    default_code = "billing_not_configured"


# ── tenant / subscription helpers ──────────────────────────────────────────────

def current_org():
    """The Organization for the active schema, or None on the public schema."""
    org = getattr(connection, "tenant", None)
    if org is None or getattr(org, "schema_name", None) in (None, "public"):
        return None
    return org


def get_or_create_subscription(org) -> Subscription:
    sub, _ = Subscription.objects.get_or_create(
        organization=org,
        defaults={
            "plan": "trial",
            "seats_purchased": SEAT_PACKAGES["trial"],
            "status": SubscriptionStatus.TRIALING,
        },
    )
    return sub


def active_user_count() -> int:
    """Active users in the *current tenant schema*."""
    from apps.accounts.models import User
    return User.objects.filter(is_active=True).count()


def seats_remaining(sub: Subscription) -> int:
    return max(0, sub.seats_purchased - active_user_count())


def assert_can_add_user() -> None:
    """Raise SeatLimitExceeded if the current tenant has no free seats."""
    org = current_org()
    if org is None:
        return  # no billing context (control plane) — don't block
    sub = get_or_create_subscription(org)
    if not sub.is_billable_active:
        raise SeatLimitExceeded("Your subscription is not active. Update billing to add users.")
    if active_user_count() >= sub.seats_purchased:
        raise SeatLimitExceeded(
            f"Seat limit reached ({sub.seats_purchased} seats). Upgrade your plan to add more users."
        )


# ── usage metering (PAYG) ──────────────────────────────────────────────────────

def record_usage(kind: str, quantity: int = 1, task_id: int | None = None, org=None):
    """Record a usage event for the current (or given) org. No-op on public."""
    org = org or current_org()
    if org is None:
        return None
    try:
        return UsageRecord.objects.create(
            organization=org, kind=kind, quantity=quantity, task_id=task_id
        )
    except Exception:  # metering must never break the agent run
        logger.exception("Failed to record usage (kind=%s, task=%s)", kind, task_id)
        return None


# ── Stripe ─────────────────────────────────────────────────────────────────────

def _stripe():
    key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not key:
        return None
    import stripe
    stripe.api_key = key
    return stripe


def billing_configured() -> bool:
    return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))


def create_checkout_session(org, plan: str, success_url: str, cancel_url: str) -> str:
    """Create a Stripe Checkout session to buy/change a seat package. Returns its URL."""
    s = _stripe()
    if s is None:
        raise BillingNotConfigured()
    price_id = getattr(settings, "STRIPE_PRICES", {}).get(plan)
    if not price_id:
        raise BillingNotConfigured(f"No Stripe price configured for plan '{plan}'.")

    sub = get_or_create_subscription(org)
    customer_id = sub.stripe_customer_id or None
    session = s.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=org.schema_name,
        metadata={"org_schema": org.schema_name, "plan": plan},
    )
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str):
    """Verify + parse a Stripe webhook payload."""
    s = _stripe()
    if s is None:
        raise BillingNotConfigured()
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise BillingNotConfigured("STRIPE_WEBHOOK_SECRET is not set.")
    return s.Webhook.construct_event(payload, sig_header, secret)


def apply_webhook_event(event) -> bool:
    """Update local Subscription state from a Stripe event. Returns True if handled."""
    etype = event.get("type") if isinstance(event, dict) else event["type"]
    obj = (event.get("data") or {}).get("object") if isinstance(event, dict) else event["data"]["object"]

    if etype == "checkout.session.completed":
        schema = (obj.get("metadata") or {}).get("org_schema") or obj.get("client_reference_id")
        if not schema:
            return False
        from apps.tenancy.models import Organization
        org = Organization.objects.filter(schema_name=schema).first()
        if not org:
            return False
        sub = get_or_create_subscription(org)
        sub.stripe_customer_id = obj.get("customer") or sub.stripe_customer_id
        sub.stripe_subscription_id = obj.get("subscription") or sub.stripe_subscription_id
        sub.status = SubscriptionStatus.ACTIVE
        plan = (obj.get("metadata") or {}).get("plan")
        if plan in SEAT_PACKAGES:
            sub.plan = plan
            sub.seats_purchased = SEAT_PACKAGES[plan]
        sub.save()
        return True

    if etype in ("customer.subscription.updated", "customer.subscription.created"):
        sub = Subscription.objects.filter(stripe_customer_id=obj.get("customer")).first()
        if not sub:
            return False
        status_map = {
            "active": SubscriptionStatus.ACTIVE,
            "trialing": SubscriptionStatus.TRIALING,
            "past_due": SubscriptionStatus.PAST_DUE,
            "unpaid": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELED,
        }
        sub.status = status_map.get(obj.get("status"), sub.status)
        # quantity → seats
        items = ((obj.get("items") or {}).get("data") or [])
        if items and items[0].get("quantity"):
            sub.seats_purchased = items[0]["quantity"]
        sub.save()
        return True

    if etype == "customer.subscription.deleted":
        sub = Subscription.objects.filter(stripe_customer_id=obj.get("customer")).first()
        if sub:
            sub.status = SubscriptionStatus.CANCELED
            sub.save(update_fields=["status", "updated_at"])
            return True

    if etype == "invoice.payment_failed":
        sub = Subscription.objects.filter(stripe_customer_id=obj.get("customer")).first()
        if sub:
            sub.status = SubscriptionStatus.PAST_DUE
            sub.save(update_fields=["status", "updated_at"])
            return True

    return False
