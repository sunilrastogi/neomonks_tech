from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import (
    ApiKeyViewSet, ChangePasswordView, MeView, UserAdminViewSet, login_page, logout_view,
)

router = DefaultRouter()
router.register(r"api-keys", ApiKeyViewSet, basename="api-key")
router.register(r"users", UserAdminViewSet, basename="user")

# Page routes (HTML)
page_urlpatterns = [
    path("login/", login_page, name="login"),
    path("logout/", logout_view, name="logout"),
]

# API routes (mounted under /api/v1/auth/)
api_urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
] + router.urls
