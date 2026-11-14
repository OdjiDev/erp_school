from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from apps.common.tenancy import tenant_scope

from .access import (
    IMPORT_ROLES,
    GRADING_ROLES,
    STUDENT_ROLES,
    STRUCTURE_ROLES,
    USER_ROLES,
    school_roles_for_user,
    user_can_access_school,
)
from .models import School


def resolve_school(user, org_slug, school_code):
    """Retourne l'école demandée si l'utilisateur y a accès, sinon 403/404."""
    school = get_object_or_404(
        School.all_objects.select_related("organization"),
        organization__slug=org_slug,
        code=(school_code or "").strip().upper(),
    )
    if not user_can_access_school(user, school):
        raise PermissionDenied("Vous n'avez pas accès à cet établissement.")
    return school


def tenant_scoped_view(view):
    """Resolve the URL school before running a view inside its tenant scope."""

    @wraps(view)
    def wrapped(request, org_slug, school_code, *args, **kwargs):
        school = resolve_school(request.user, org_slug, school_code)
        request.school = school
        roles = school_roles_for_user(request.user, school)
        request.school_roles = roles
        request.can_import = bool(roles.intersection(IMPORT_ROLES))
        request.can_manage_students = bool(roles.intersection(STUDENT_ROLES))
        request.can_manage_structure = bool(roles.intersection(STRUCTURE_ROLES))
        request.can_manage_users = bool(roles.intersection(USER_ROLES))
        request.can_manage_grades = bool(roles.intersection(GRADING_ROLES))
        request.can_manage_organization = (
            request.user.is_superuser
            or "platform_admin" in roles
            or "org_admin" in roles
        )
        with tenant_scope(school.organization_id, school.pk):
            return view(request, org_slug, school_code, *args, **kwargs)

    return wrapped
