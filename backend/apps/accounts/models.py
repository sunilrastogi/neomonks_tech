"""Per-tenant user model.

`apps.accounts` is a TENANT app, so each tenant schema gets its own user table —
email is therefore unique *within a tenant*, which matches one-org-per-user.
"""
import hashlib
import secrets

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import TextChoices
from django.utils import timezone


class Role(TextChoices):
    OWNER = "OWNER", "Owner"      # billing + everything
    ADMIN = "ADMIN", "Admin"      # manage users / config, no billing
    MEMBER = "MEMBER", "Member"   # create requirements, run agents, review
    VIEWER = "VIEWER", "Viewer"   # read-only


class AuthSource(TextChoices):
    PASSWORD = "PASSWORD", "Password"
    SSO = "SSO", "SSO"


class UserManager(BaseUserManager):
    """Email-based user manager (no username)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Role.OWNER)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    # Drop username; authenticate by email instead.
    username = None
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    auth_source = models.CharField(max_length=20, choices=AuthSource.choices, default=AuthSource.PASSWORD)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKey(models.Model):
    """Programmatic access token for a tenant. Only the hash is stored.

    The full key (``nmk_<prefix>_<secret>``) is shown once at creation time.
    Lives in the tenant schema, so a key only ever grants access to its own org.
    """

    name = models.CharField(max_length=255)
    prefix = models.CharField(max_length=12, unique=True, db_index=True)
    hashed_key = models.CharField(max_length=64)
    created_by = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @classmethod
    def generate(cls, name: str, created_by: str = ""):
        """Create a key; returns (instance, full_plaintext_key)."""
        prefix = secrets.token_hex(4)          # 8 hex chars
        secret = secrets.token_urlsafe(32)
        full = f"nmk_{prefix}_{secret}"
        obj = cls.objects.create(
            name=name, prefix=prefix, hashed_key=_hash_key(full), created_by=created_by,
        )
        return obj, full

    @classmethod
    def resolve(cls, raw: str):
        """Return the live ApiKey for a presented raw key, or None."""
        if not raw or not raw.startswith("nmk_"):
            return None
        parts = raw.split("_", 2)
        if len(parts) != 3:
            return None
        try:
            obj = cls.objects.get(prefix=parts[1], revoked=False)
        except cls.DoesNotExist:
            return None
        if secrets.compare_digest(obj.hashed_key, _hash_key(raw)):
            return obj
        return None

    def touch(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])
