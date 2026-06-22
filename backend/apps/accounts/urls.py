from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import (
    ApiKeyViewSet, ChangePasswordView, MeView, PasswordResetConfirmView,
    PasswordResetRequestView, SSOConfigView, UserAdminViewSet,
    login_page, logout_view, reset_password_page, sso_callback, sso_login,
)

router = DefaultRouter()
router.register(r"api-keys", ApiKeyViewSet, basename="api-key")
router.register(r"users", UserAdminViewSet, basename="user")

# Page routes (HTML)
page_urlpatterns = [
    path("login/", login_page, name="login"),
    path("logout/", logout_view, name="logout"),
    path("sso/login/", sso_login, name="sso-login"),
    path("sso/callback/", sso_callback, name="sso-callback"),
    path("reset-password/", reset_password_page, name="reset-password"),
]

# API routes (mounted under /api/v1/auth/)
api_urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("sso-config/", SSOConfigView.as_view(), name="sso-config"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
] + router.urls
