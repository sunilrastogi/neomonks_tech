from rest_framework import serializers

from apps.billing.models import Subscription
from apps.billing.services import active_user_count, seats_remaining


class SubscriptionSerializer(serializers.ModelSerializer):
    seats_used = serializers.SerializerMethodField()
    seats_available = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "plan", "seats_purchased", "seats_used", "seats_available",
            "status", "current_period_end", "stripe_customer_id",
        ]
        read_only_fields = fields

    def get_seats_used(self, obj):
        return active_user_count()

    def get_seats_available(self, obj):
        return seats_remaining(obj)
