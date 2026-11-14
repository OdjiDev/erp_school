from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.academics.models import ClassSubject
from apps.academics.utils import current_academic_year
from apps.tenancy.access import (
    USER_ROLES,
    user_can_manage_structure,
    user_can_manage_users,
)
from apps.tenancy.forms import (
    MembershipForm,
    StaffUserCreateForm,
    UserEditForm,
)
from apps.tenancy.models import Membership, Role
from apps.tenancy.selectors import tenant_scoped_view

User = get_user_model()


def _ensure_user_management(request):
    if not user_can_manage_users(request.user, request.school):
        raise PermissionDenied(
            "Vous n'avez pas le droit de gérer les comptes de cette école."
        )


def _visible_memberships(request, user=None):
    memberships = Membership.all_objects.filter(
        organization=request.school.organization
    ).select_related("user", "school")
    if user is not None:
        memberships = memberships.filter(user=user)
    if not request.can_manage_organization:
        memberships = memberships.filter(
            Q(school=request.school) | Q(school__isnull=True)
        )
    return memberships


def _get_visible_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    memberships = _visible_memberships(request, target)
    if not request.can_manage_organization:
        # Un directeur d'école n'agit que sur les comptes rattachés à son
        # école. Les rôles portant sur toute l'organisation restent hors de
        # sa portée, même s'ils sont visibles dans la liste.
        memberships = memberships.filter(school=request.school)
    if not memberships.exists():
        raise Http404("Utilisateur introuvable dans cette école.")
    return target


def _get_editable_membership(request, membership_id):
    membership = get_object_or_404(
        Membership.all_objects.select_related("user", "school"),
        pk=membership_id,
        organization=request.school.organization,
    )
    if membership.school_id is None:
        if not request.can_manage_organization:
            raise Http404("Rôle introuvable dans cette école.")
    elif membership.school_id != request.school.id:
        raise Http404("Rôle introuvable dans cette école.")
    if not request.can_manage_organization and membership.role in {
        Role.PLATFORM_ADMIN.value,
        Role.ORG_ADMIN.value,
    }:
        raise PermissionDenied(
            "Vous ne pouvez pas modifier un rôle d'administration client."
        )
    return membership


def _editable_membership(membership, request):
    if membership.school_id is None:
        return request.can_manage_organization
    if membership.school_id != request.school.id:
        return False
    if request.can_manage_organization:
        return True
    return membership.role not in {
        Role.PLATFORM_ADMIN.value,
        Role.ORG_ADMIN.value,
    }


@login_required
@tenant_scoped_view
def user_list(request, org_slug, school_code):
    _ensure_user_management(request)
    school = request.school
    memberships = _visible_memberships(request).order_by(
        "user__last_name", "user__first_name", "user__username", "role"
    )
    query = request.GET.get("q", "").strip()
    if query:
        memberships = memberships.filter(
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
        )
    paginator = Paginator(memberships, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    for membership in page_obj.object_list:
        membership.can_edit = _editable_membership(membership, request)
        membership.can_open = (
            request.can_manage_organization
            or membership.school_id == request.school.id
        )
        membership.can_toggle = (
            membership.can_edit and membership.user_id != request.user.id
        )

    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "tenancy/user_list.html",
        {
            "school": school,
            "page_obj": page_obj,
            "memberships": page_obj.object_list,
            "query": query,
            "base_query": params.urlencode(),
            "total_count": paginator.count,
            "can_manage_organization": request.can_manage_organization,
        },
    )


@login_required
@tenant_scoped_view
def user_create(request, org_slug, school_code):
    _ensure_user_management(request)
    school = request.school
    form = StaffUserCreateForm(
        request.POST or None,
        school=school,
        can_manage_organization=request.can_manage_organization,
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
        role = user.memberships.first()
        messages.success(
            request,
            f"Compte « {user.get_username()} » créé"
            + (f" avec le rôle {role.get_role_display()}." if role else "."),
        )
        return redirect(
            "school:user_edit",
            org_slug=school.organization.slug,
            school_code=school.code,
            user_id=user.id,
        )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": "Nouvel utilisateur",
            "form_intro": (
                "Créez un identifiant de connexion et attribuez un rôle. "
                "Le compte n'a accès qu'à la portée choisie."
            ),
            "form": form,
            "submit_label": "Créer le compte",
            "cancel_url": reverse(
                "school:user_list",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                },
            ),
        },
    )


@login_required
@tenant_scoped_view
def user_edit(request, org_slug, school_code, user_id):
    _ensure_user_management(request)
    school = request.school
    target = _get_visible_user(request, user_id)
    form = UserEditForm(
        request.POST or None,
        instance=target,
        can_deactivate=(
            request.can_manage_organization and target.id != request.user.id
        ),
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Compte utilisateur mis à jour.")
        return redirect(
            "school:user_edit",
            org_slug=school.organization.slug,
            school_code=school.code,
            user_id=target.id,
        )

    memberships = _visible_memberships(request, target).order_by(
        "school__name", "role"
    )
    for membership in memberships:
        membership.can_edit = _editable_membership(membership, request)
        membership.can_toggle = (
            membership.can_edit and membership.user_id != request.user.id
        )
    return render(
        request,
        "tenancy/user_edit.html",
        {
            "school": school,
            "target_user": target,
            "form": form,
            "memberships": memberships,
            "is_self": target.id == request.user.id,
            "can_manage_organization": request.can_manage_organization,
        },
    )


@login_required
@tenant_scoped_view
def user_password_reset(request, org_slug, school_code, user_id):
    _ensure_user_management(request)
    school = request.school
    target = _get_visible_user(request, user_id)
    form = SetPasswordForm(target, request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            f"Mot de passe de « {target.get_username()} » réinitialisé.",
        )
        return redirect(
            "school:user_edit",
            org_slug=school.organization.slug,
            school_code=school.code,
            user_id=target.id,
        )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": "Réinitialiser le mot de passe",
            "form_intro": (
                f"Compte {target.get_username()}. Communiquez le nouveau mot "
                "de passe à l'utilisateur par un canal sûr."
            ),
            "form": form,
            "submit_label": "Réinitialiser",
            "cancel_url": reverse(
                "school:user_edit",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                    "user_id": target.id,
                },
            ),
        },
    )


@login_required
@tenant_scoped_view
def membership_create(request, org_slug, school_code, user_id):
    _ensure_user_management(request)
    school = request.school
    target = _get_visible_user(request, user_id)
    form = MembershipForm(
        request.POST or None,
        school=school,
        user=target,
        can_manage_organization=request.can_manage_organization,
    )

    if request.method == "POST" and form.is_valid():
        membership = form.save(commit=False)
        membership.user = target
        membership.organization = school.organization
        if not request.can_manage_organization:
            membership.school = school
        membership.save()
        messages.success(
            request,
            f"Rôle « {membership.get_role_display()} » ajouté à "
            f"{target.get_username()}.",
        )
        return redirect(
            "school:user_edit",
            org_slug=school.organization.slug,
            school_code=school.code,
            user_id=target.id,
        )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": f"Ajouter un rôle — {target.get_username()}",
            "form_intro": (
                "Un utilisateur peut cumuler plusieurs rôles, à l'échelle "
                "de l'école ou de l'organisation."
            ),
            "form": form,
            "submit_label": "Ajouter le rôle",
            "cancel_url": reverse(
                "school:user_edit",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                    "user_id": target.id,
                },
            ),
        },
    )


@login_required
@tenant_scoped_view
def membership_edit(request, org_slug, school_code, membership_id):
    _ensure_user_management(request)
    school = request.school
    membership = _get_editable_membership(request, membership_id)
    form = MembershipForm(
        request.POST or None,
        instance=membership,
        school=school,
        user=membership.user,
        can_manage_organization=request.can_manage_organization,
    )

    if request.method == "POST" and form.is_valid():
        if membership.user_id == request.user.id:
            if not form.cleaned_data["is_active"]:
                form.add_error(
                    "is_active",
                    "Vous ne pouvez pas désactiver votre propre rôle.",
                )
            elif form.cleaned_data["role"] not in USER_ROLES:
                form.add_error(
                    "role",
                    "Vous ne pouvez pas retirer votre propre accès à la "
                    "gestion des utilisateurs.",
                )
        if not form.errors:
            membership = form.save(commit=False)
            membership.organization = school.organization
            if not request.can_manage_organization:
                membership.school = school
            membership.save()
            messages.success(request, "Rôle mis à jour.")
            return redirect(
                "school:user_edit",
                org_slug=school.organization.slug,
                school_code=school.code,
                user_id=membership.user_id,
            )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": "Modifier le rôle",
            "form_intro": (
                f"{membership.user.get_username()} · "
                f"{membership.get_role_display()}"
            ),
            "form": form,
            "submit_label": "Enregistrer",
            "cancel_url": reverse(
                "school:user_edit",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                    "user_id": membership.user_id,
                },
            ),
        },
    )


@login_required
@tenant_scoped_view
def membership_toggle(request, org_slug, school_code, membership_id):
    _ensure_user_management(request)
    school = request.school
    if request.method != "POST":
        raise PermissionDenied("Cette action doit être confirmée.")
    membership = _get_editable_membership(request, membership_id)
    if membership.user_id == request.user.id:
        messages.error(
            request, "Vous ne pouvez pas désactiver votre propre rôle."
        )
    else:
        membership.is_active = not membership.is_active
        membership.save()
        state = "activé" if membership.is_active else "désactivé"
        messages.success(
            request,
            f"Rôle « {membership.get_role_display()} » {state} pour "
            f"{membership.user.get_username()}.",
        )
    return redirect(
        "school:user_edit",
        org_slug=school.organization.slug,
        school_code=school.code,
        user_id=membership.user_id,
    )


@login_required
@tenant_scoped_view
def teacher_list(request, org_slug, school_code):
    if not user_can_manage_structure(request.user, request.school):
        raise PermissionDenied(
            "Vous n'avez pas le droit de consulter les enseignants."
        )
    school = request.school
    memberships = (
        Membership.all_objects.filter(
            organization=school.organization,
            role=Role.TEACHER,
            is_active=True,
        )
        .filter(Q(school__isnull=True) | Q(school=school))
        .select_related("user", "school")
        .order_by("user__last_name", "user__first_name")
    )

    teachers = {}
    for membership in memberships:
        teacher = teachers.setdefault(membership.user_id, membership.user)
        teacher.org_wide = getattr(teacher, "org_wide", False) or (
            membership.school_id is None
        )

    year = current_academic_year(school)
    assignment_counts = {}
    if year and teachers:
        assignment_counts = dict(
            ClassSubject.objects.filter(
                school_class__school=school,
                school_class__academic_year=year,
                teacher_id__in=teachers.keys(),
            )
            .values_list("teacher_id")
            .annotate(total=Count("id"))
        )

    query = request.GET.get("q", "").strip()
    teacher_list_items = list(teachers.values())
    if query:
        needle = query.lower()
        teacher_list_items = [
            teacher
            for teacher in teacher_list_items
            if needle
            in " ".join(
                [
                    teacher.get_username(),
                    teacher.get_full_name(),
                    teacher.email or "",
                ]
            ).lower()
        ]
    for teacher in teacher_list_items:
        teacher.assignment_count = assignment_counts.get(teacher.id, 0)

    teacher_list_items.sort(
        key=lambda teacher: (
            teacher.last_name.lower(),
            teacher.first_name.lower(),
            teacher.get_username().lower(),
        )
    )
    paginator = Paginator(teacher_list_items, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    for teacher in page_obj.object_list:
        teacher.assignment_count = assignment_counts.get(teacher.id, 0)

    return render(
        request,
        "tenancy/teacher_list.html",
        {
            "school": school,
            "page_obj": page_obj,
            "teachers": page_obj.object_list,
            "query": query,
            "total_count": paginator.count,
            "current_year": year,
            "can_manage_users": request.can_manage_users,
        },
    )
