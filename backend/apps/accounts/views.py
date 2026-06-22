"""Authentication views: session login/logout (HTML) + account API.

All of these run inside the tenant schema resolved by the subdomain, so
authentication, users and API keys are automatically tenant-scoped.
"""
import secrets as _secrets

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import redirect, render
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import oidc
from apps.accounts.models import ApiKey, OrgSSOConfig, Role, User
from apps.accounts.permissions import IsOrgAdmin
from apps.accounts.serializers import (
    ApiKeySerializer, SSOConfigSerializer, UserAdminSerializer, UserSerializer,
)

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
        return render(request, "login.html",
                      {"error": "Invalid email or password.", "sso_enabled": OrgSSOConfig.load().enabled},
                      status=401)

    if request.user.is_authenticated:
        return redirect(DASHBOARD_URL)
    return render(request, "login.html", {"sso_enabled": OrgSSOConfig.load().enabled})


def logout_view(request):
    logout(request)
    return redirect("/login/")


# ── SSO (OIDC) ─────────────────────────────────────────────────────────────────

def sso_login(request):
    """Begin the OIDC flow for this tenant."""
    cfg = OrgSSOConfig.load()
    if not (cfg.enabled and cfg.discovery_url and cfg.client_id):
        return redirect("/login/?sso=unavailable")
    state = _secrets.token_urlsafe(24)
    nonce = _secrets.token_urlsafe(24)
    request.session["sso_state"] = state
    request.session["sso_nonce"] = nonce
    redirect_uri = request.build_absolute_uri("/sso/callback/")
    try:
        url = oidc.build_authorize_url(cfg, redirect_uri, state, nonce)
    except Exception:
        return redirect("/login/?sso=error")
    return redirect(url)


def sso_callback(request):
    """Handle the IdP redirect: exchange code, provision user, start session."""
    cfg = OrgSSOConfig.load()
    if not cfg.enabled:
        return redirect("/login/")
    code = request.GET.get("code")
    state = request.GET.get("state")
    if not code or not state or state != request.session.get("sso_state"):
        return redirect("/login/?sso=badstate")
    redirect_uri = request.build_absolute_uri("/sso/callback/")
    try:
        token = oidc.exchange_code(cfg, code, redirect_uri)
        claims = oidc.fetch_userinfo(cfg, token["access_token"])
        user = oidc.provision_user(cfg, claims)
    except oidc.SSODomainNotAllowed:
        return redirect("/login/?sso=denied")
    except Exception:
        return redirect("/login/?sso=error")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.pop("sso_state", None)
    request.session.pop("sso_nonce", None)
    return redirect(DASHBOARD_URL)


class SSOConfigView(APIView):
    """Admin: view/update this tenant's SSO configuration."""

    permission_classes = [IsOrgAdmin]

    def get(self, request):
        return Response(SSOConfigSerializer(OrgSSOConfig.load()).data)

    def post(self, request):
        cfg = OrgSSOConfig.load()
        serializer = SSOConfigSerializer(cfg, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(SSOConfigSerializer(cfg).data)


# ── Password reset ─────────────────────────────────────────────────────────────

class PasswordResetRequestView(APIView):
    """Request a reset link. Always 200 (does not reveal whether the email exists)."""

    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = request.build_absolute_uri(f"/reset-password/?uid={uid}&token={token}")
            send_mail(
                "Reset your NeoMonks password",
                f"Use this link to reset your password:\n\n{reset_url}\n\n"
                f"If you didn't request this, you can ignore this email.",
                getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@neomonks.local"),
                [email],
                fail_silently=True,
            )
        return Response({"detail": "If that email is registered, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uidb64 = request.data.get("uid") or ""
        token = request.data.get("token") or ""
        new_password = request.data.get("new_password") or ""
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except Exception:
            return Response({"detail": "Invalid reset link."}, status=status.HTTP_400_BAD_REQUEST)
        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Invalid or expired reset link."}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 8:
            return Response({"detail": "Password must be at least 8 characters."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated. You can now sign in."})


def reset_password_page(request):
    """Static page that posts uid/token/new password to the confirm endpoint."""
    return render(request, "reset_password.html")


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


class UserAdminViewSet(viewsets.ModelViewSet):
    """Admin-only management of users within the current tenant."""

    serializer_class = UserAdminSerializer
    permission_classes = [IsOrgAdmin]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return User.objects.all().order_by("email")

    def _guard_owner_role(self, serializer):
        # Only an Owner may grant the Owner role.
        if serializer.validated_data.get("role") == Role.OWNER and self.request.user.role != Role.OWNER:
            raise PermissionDenied("Only an Owner can assign the Owner role.")

    def perform_create(self, serializer):
        from apps.billing.services import assert_can_add_user
        assert_can_add_user()  # raises SeatLimitExceeded (HTTP 402) when full
        self._guard_owner_role(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._guard_owner_role(serializer)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Deactivate rather than hard-delete; you cannot deactivate yourself."""
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "You cannot deactivate your own account."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApiKeyViewSet(viewsets.ModelViewSet):
    """Manage tenant API keys (admin only). The full key is returned once, on create."""

    serializer_class = ApiKeySerializer
    permission_classes = [IsOrgAdmin]
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
