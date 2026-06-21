"""Role-based access control for tenant users.

Role hierarchy (low → high): VIEWER < MEMBER < ADMIN < OWNER.
Isolation across tenants is enforced by the schema boundary; these permissions
govern what a user may do *within their own tenant*.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Role

ROLE_RANK = {
    Role.VIEWER: 0,
    Role.MEMBER: 1,
    Role.ADMIN: 2,
    Role.OWNER: 3,
}


def rank(role) -> int:
    return ROLE_RANK.get(role, -1)


class HasOrgRole(BasePermission):
    """Require the authenticated user to hold at least ``min_role``."""

    min_role = Role.VIEWER

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and rank(user.role) >= ROLE_RANK[self.min_role]
        )


class WorkflowRolePermission(BasePermission):
    """Method-tiered access for product/workflow resources.

    - read (GET/HEAD/OPTIONS): VIEWER+
    - create / update (POST/PUT/PATCH): MEMBER+
    - delete (DELETE): ADMIN+
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            needed = ROLE_RANK[Role.VIEWER]
        elif request.method == "DELETE":
            needed = ROLE_RANK[Role.ADMIN]
        else:
            needed = ROLE_RANK[Role.MEMBER]
        return rank(user.role) >= needed


class IsOrgAdmin(HasOrgRole):
    min_role = Role.ADMIN


class IsOrgOwner(HasOrgRole):
    min_role = Role.OWNER
