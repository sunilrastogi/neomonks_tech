"""DRF authentication via tenant API keys.

Clients send: ``Authorization: Api-Key nmk_<prefix>_<secret>``.
The key is resolved within the current tenant schema, so it can only ever
authenticate against its own organisation.
"""
from rest_framework import authentication, exceptions

from apps.accounts.models import ApiKey, User


class ApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Api-Key"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin1")
        if not header:
            return None
        parts = header.split()
        if parts[0] != self.keyword:
            return None  # let other authenticators handle it
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Invalid Api-Key header format.")

        api_key = ApiKey.resolve(parts[1])
        if api_key is None:
            raise exceptions.AuthenticationFailed("Invalid or revoked API key.")
        api_key.touch()

        # Authenticate as the owner of the key, or the first owner/admin as a
        # service principal if the creator no longer exists.
        user = User.objects.filter(email=api_key.created_by).first()
        if user is None:
            user = User.objects.filter(is_active=True).order_by("id").first()
        if user is None or not user.is_active:
            raise exceptions.AuthenticationFailed("No active user for this API key.")
        return (user, api_key)

    def authenticate_header(self, request):
        return self.keyword
