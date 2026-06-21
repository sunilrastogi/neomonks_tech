from django.contrib import admin

from apps.billing.models import Subscription, UsageRecord


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "seats_purchased", "status", "current_period_end")
    list_filter = ("plan", "status")
    search_fields = ("organization__name", "stripe_customer_id")


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("organization", "kind", "quantity", "task_id", "occurred_at", "reported_to_stripe")
    list_filter = ("kind", "reported_to_stripe")
    search_fields = ("organization__name",)
