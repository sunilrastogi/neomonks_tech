from rest_framework import serializers

from apps.accounts.models import ApiKey, OrgSSOConfig, Role, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "auth_source", "is_active", "is_staff"]
        read_only_fields = fields


class UserAdminSerializer(serializers.ModelSerializer):
    """Admin-facing user management (create/list/update within the tenant)."""

    password = serializers.CharField(write_only=True, required=False, min_length=8, allow_blank=False)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "auth_source", "is_active", "password"]
        read_only_fields = ["id", "auth_source"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Password is required for new users."})
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class ApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = ["id", "name", "prefix", "created_by", "created_at", "last_used_at", "revoked"]
        read_only_fields = ["prefix", "created_by", "created_at", "last_used_at", "revoked"]


class SSOConfigSerializer(serializers.ModelSerializer):
    """Admin-facing SSO config. The client secret is write-only and only
    overwritten when a non-empty value is sent."""

    client_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    client_secret_set = serializers.SerializerMethodField()

    class Meta:
        model = OrgSSOConfig
        fields = [
            "enabled", "provider", "discovery_url", "client_id",
            "client_secret", "client_secret_set",
            "allowed_email_domains", "default_role", "auto_provision", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def get_client_secret_set(self, obj):
        return bool(obj.client_secret)

    def update(self, instance, validated_data):
        secret = validated_data.pop("client_secret", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if secret:  # keep existing when blank/omitted
            instance.client_secret = secret
        instance.save()
        return instance
