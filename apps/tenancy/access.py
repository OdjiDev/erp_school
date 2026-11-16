from django.db.models import Q

from .models import Membership, Role, School

STAFF_ROLES = [
    Role.PLATFORM_ADMIN.value,
    Role.ORG_ADMIN.value,
    Role.SCHOOL_ADMIN.value,
    Role.SECRETARY.value,
    Role.ACCOUNTANT.value,
    Role.TEACHER.value,
    Role.SURVEILLANT.value,
    Role.AUDITOR.value,
]

MANAGEMENT_ROLES = [
    Role.PLATFORM_ADMIN.value,
    Role.ORG_ADMIN.value,
    Role.SCHOOL_ADMIN.value,
    Role.SECRETARY.value,
]

USER_ROLES = [
    Role.PLATFORM_ADMIN.value,
    Role.ORG_ADMIN.value,
    Role.SCHOOL_ADMIN.value,
]

IMPORT_ROLES = MANAGEMENT_ROLES
STRUCTURE_ROLES = MANAGEMENT_ROLES
STUDENT_ROLES = MANAGEMENT_ROLES
TEACHER_ROLES = MANAGEMENT_ROLES

GRADING_ROLES = [*MANAGEMENT_ROLES, Role.TEACHER.value]

FINANCE_VIEW_ROLES = [
    Role.PLATFORM_ADMIN.value,
    Role.ORG_ADMIN.value,
    Role.SCHOOL_ADMIN.value,
    Role.ACCOUNTANT.value,
    Role.SECRETARY.value,
    Role.AUDITOR.value,
]
FINANCE_MANAGEMENT_ROLES = [
    Role.PLATFORM_ADMIN.value,
    Role.ORG_ADMIN.value,
    Role.SCHOOL_ADMIN.value,
    Role.ACCOUNTANT.value,
]
FINANCE_COLLECTION_ROLES = [
    *FINANCE_MANAGEMENT_ROLES,
    Role.SECRETARY.value,
]


def _user_has_role(user, school, roles):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        Membership.all_objects.filter(
            user=user,
            organization=school.organization,
            is_active=True,
            role__in=roles,
        )
        .filter(Q(school__isnull=True) | Q(school=school))
        .exists()
    )


def school_roles_for_user(user, school):
    """Rôles actifs de l'utilisateur sur une école, en une seule requête."""
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(Role.values)
    return set(
        Membership.all_objects.filter(
            user=user,
            organization=school.organization,
            is_active=True,
        )
        .filter(Q(school__isnull=True) | Q(school=school))
        .values_list("role", flat=True)
    )


def user_can_access_school(user, school):
    """Vérifie qu'un utilisateur peut administrer une école donnée."""
    return _user_has_role(user, school, STAFF_ROLES)


def user_can_import(user, school):
    """Vérifie qu'un utilisateur peut importer des données dans l'école."""
    return _user_has_role(user, school, IMPORT_ROLES)


def user_can_manage_structure(user, school):
    """Vérifie qu'un utilisateur peut modifier la structure académique."""
    return _user_has_role(user, school, STRUCTURE_ROLES)


def user_can_manage_students(user, school):
    """Vérifie qu'un utilisateur peut créer et modifier élèves et inscriptions."""
    return _user_has_role(user, school, STUDENT_ROLES)


def user_can_manage_teachers(user, school):
    """Vérifie qu'un utilisateur peut affecter les enseignants."""
    return _user_has_role(user, school, TEACHER_ROLES)


def user_can_manage_grades(user, school):
    """Vérifie que l'utilisateur peut ouvrir les écrans de notes."""
    return _user_has_role(user, school, GRADING_ROLES)


def user_can_view_finance(user, school):
    """Consultation des frais, factures, encaissements et caisses."""
    return _user_has_role(user, school, FINANCE_VIEW_ROLES)


def user_can_manage_finance(user, school):
    """Gestion des frais, échéanciers, remises, factures et caisses."""
    return _user_has_role(user, school, FINANCE_MANAGEMENT_ROLES)


def user_can_collect_payments(user, school):
    """Encaissement des paiements (espèces ou mobile money)."""
    return _user_has_role(user, school, FINANCE_COLLECTION_ROLES)


def user_can_manage_grading_settings(user, school):
    """Les rôles de gestion administrent les périodes et publient les notes."""
    return _user_has_role(user, school, MANAGEMENT_ROLES)


def user_can_grade_class_subject(user, school, class_subject):
    """Un enseignant ne peut noter que ses affectations dans cette école."""
    if user_can_manage_grading_settings(user, school):
        return True
    return (
        class_subject.school_class.school_id == school.pk
        and class_subject.teacher_id == user.pk
        and _user_has_role(user, school, [Role.TEACHER.value])
    )


def user_can_manage_users(user, school):
    """Vérifie qu'un utilisateur peut gérer les comptes et rôles de l'école."""
    return _user_has_role(user, school, USER_ROLES)


def user_can_manage_organization(user, organization):
    """Vérifie qu'un utilisateur administre l'organisation dans son ensemble."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return Membership.all_objects.filter(
        user=user,
        organization=organization,
        school__isnull=True,
        is_active=True,
        role__in=[Role.PLATFORM_ADMIN.value, Role.ORG_ADMIN.value],
    ).exists()


def accessible_schools(user):
    """Écoles accessibles à un utilisateur, via ses appartenances actives."""
    if not user.is_authenticated:
        return School.objects.none()
    if user.is_superuser:
        return (
            School.all_objects.select_related("organization")
            .all()
            .order_by("organization__name", "name", "code")
        )

    memberships = list(
        Membership.all_objects.filter(
            user=user, is_active=True, role__in=STAFF_ROLES
        ).only("organization_id", "school_id")
    )
    organization_ids = {
        membership.organization_id
        for membership in memberships
        if membership.school_id is None
    }
    school_ids = {
        membership.school_id
        for membership in memberships
        if membership.school_id is not None
    }
    return (
        School.all_objects.filter(
            Q(organization_id__in=organization_ids) | Q(id__in=school_ids)
        )
        .select_related("organization")
        .order_by("organization__name", "name", "code")
    )
