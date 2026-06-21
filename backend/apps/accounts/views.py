"""Authentication views: session login/logout (HTML) + account API.

All of these run inside the tenant schema resolved by the subdomain, so
authentication, users and API keys are automatically tenant-scoped.
"""
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import ApiKey
from apps.accounts.serializers import ApiKeySerializer, UserSerializer

DASHBOARD_URL = "/api/v1/realtime/dashboard/"


def login_page(request):
    """GET renders the login form; POST authenticates within this tenant."""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=email, password=password)
        if user is not None and user.is_active:
            login(request, user)
            return redirect(request.GET.get("next") or DASHBOARD_URL)
        return render(request, "login.html", {"error": "Invalid email or password."}, status=401)

    if request.user.is_authenticated:
        return redirect(DASHBOARD_URL)
    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("/login/")


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old = request.data.get("old_password") or ""
        new = request.data.get("new_password") or ""
        if not request.user.check_password(old):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        if len(new) < 8:
            return Response({"detail": "New password must be at least 8 characters."}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed. Please sign in again."})


class ApiKeyViewSet(viewsets.ModelViewSet):
    """Manage tenant API keys. The full key is returned only once, on create."""

    serializer_class = ApiKeySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return ApiKey.objects.all()

    def create(self, request, *args, **kwargs):
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)
        obj, full_key = ApiKey.generate(name=name, created_by=request.user.email)
        data = ApiKeySerializer(obj).data
        data["key"] = full_key  # shown once — store it now
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Revoke rather than hard-delete (keeps the audit row)."""
        obj = self.get_object()
        obj.revoked = True
        obj.save(update_fields=["revoked"])
        return Response(status=status.HTTP_204_NO_CONTENT)
