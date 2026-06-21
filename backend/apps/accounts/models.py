"""Per-tenant user model.

`apps.accounts` is a TENANT app, so each tenant schema gets its own user table —
email is therefore unique *within a tenant*, which matches one-org-per-user.
"""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import TextChoices


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
