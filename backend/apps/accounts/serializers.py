from rest_framework import serializers

from apps.accounts.models import ApiKey, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "auth_source", "is_active", "is_staff"]
        read_only_fields = fields


class ApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = ["id", "name", "prefix", "created_by", "created_at", "last_used_at", "revoked"]
        read_only_fields = ["prefix", "created_by", "created_at", "last_used_at", "revoked"]
