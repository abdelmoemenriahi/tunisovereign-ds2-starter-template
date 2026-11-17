"""Role-based permissions (RBAC) for the 4 Track 6 stakeholder roles.

STUDENT          -> submits projects, sees only their own data
MENTOR_AUDITOR   -> reviews all submissions, records findings
NATIONAL_ADMIN   -> manages cohorts and users (superset of MENTOR_AUDITOR)
AGENT_SERVICE    -> service account used by the AI agent / MCP server / gRPC ingestion
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import StakeholderUser

Role = StakeholderUser.Role


class HasRole(BasePermission):
    """Base class: the user must be authenticated AND have one of `allowed_roles`."""

    allowed_roles: tuple = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.allowed_roles)


class IsStudent(HasRole):
    allowed_roles = (Role.STUDENT,)


class IsMentorAuditor(HasRole):
    allowed_roles = (Role.MENTOR_AUDITOR, Role.NATIONAL_ADMIN)


class IsNationalAdmin(HasRole):
    allowed_roles = (Role.NATIONAL_ADMIN,)


class IsAgentService(HasRole):
    allowed_roles = (Role.AGENT_SERVICE,)


class IsStaffRole(HasRole):
    """Anyone who is NOT a plain student: mentor, admin or agent service."""

    allowed_roles = (Role.MENTOR_AUDITOR, Role.NATIONAL_ADMIN, Role.AGENT_SERVICE)


class ReadOnlyOrNationalAdmin(BasePermission):
    """Any authenticated user may read; only NATIONAL_ADMIN may write."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role == Role.NATIONAL_ADMIN


def is_staff_role(user) -> bool:
    return bool(user and user.is_authenticated and user.role in IsStaffRole.allowed_roles)


def submissions_for(user):
    """Row-level scoping shared by REST and GraphQL.

    Students only see their own submissions; staff roles see everything.
    """
    from .models import ProjectSubmission

    qs = ProjectSubmission.objects.all()
    if not user or not user.is_authenticated:
        return qs.none()
    if is_staff_role(user):
        return qs
    return qs.filter(student=user)
