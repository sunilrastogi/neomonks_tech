from django.urls import path

from apps.billing.views import (
    CheckoutView, SubscriptionView, UsageSummaryView, stripe_webhook,
)

urlpatterns = [
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("usage/", UsageSummaryView.as_view(), name="usage"),
    path("webhook/", stripe_webhook, name="stripe-webhook"),
]
