from django.db.models import Sum
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsOrgAdmin, IsOrgOwner
from apps.billing import services
from apps.billing.models import SEAT_PACKAGES, UsageRecord
from apps.billing.serializers import SubscriptionSerializer


class SubscriptionView(APIView):
    """GET current tenant's subscription + seat usage (Admin+)."""

    permission_classes = [IsOrgAdmin]

    def get(self, request):
        org = services.current_org()
        if org is None:
            return Response({"detail": "No tenant context."}, status=400)
        sub = services.get_or_create_subscription(org)
        data = SubscriptionSerializer(sub).data
        data["billing_configured"] = services.billing_configured()
        data["available_packages"] = SEAT_PACKAGES
        return Response(data)


class CheckoutView(APIView):
    """POST to start a Stripe Checkout for a seat package (Owner only)."""

    permission_classes = [IsOrgOwner]

    def post(self, request):
        org = services.current_org()
        if org is None:
            return Response({"detail": "No tenant context."}, status=400)
        plan = request.data.get("plan")
        if plan not in SEAT_PACKAGES:
            return Response({"detail": f"Unknown plan. Choose from {list(SEAT_PACKAGES)}."}, status=400)
        default_url = request.build_absolute_uri("/api/v1/realtime/dashboard/")
        url = services.create_checkout_session(
            org, plan,
            success_url=request.data.get("success_url") or default_url,
            cancel_url=request.data.get("cancel_url") or default_url,
        )
        return Response({"checkout_url": url})


class UsageSummaryView(APIView):
    """GET pay-as-you-go usage totals for the current tenant (Admin+)."""

    permission_classes = [IsOrgAdmin]

    def get(self, request):
        org = services.current_org()
        if org is None:
            return Response({"detail": "No tenant context."}, status=400)
        rows = (
            UsageRecord.objects.filter(organization=org)
            .values("kind")
            .annotate(total=Sum("quantity"))
        )
        return Response({"usage": {r["kind"]: r["total"] for r in rows}})


@csrf_exempt
def stripe_webhook(request: HttpRequest) -> JsonResponse:
    """Stripe webhook receiver (public, signature-verified)."""
    if request.method != "POST":
        return JsonResponse({"detail": "POST only"}, status=405)
    sig = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = services.construct_webhook_event(request.body, sig)
    except Exception as exc:
        return JsonResponse({"detail": f"Invalid webhook: {exc}"}, status=400)
    handled = services.apply_webhook_event(event)
    return JsonResponse({"handled": handled})
