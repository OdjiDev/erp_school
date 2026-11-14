from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import load_workbook

from apps.academics.models import AcademicYear, SchoolClass
from apps.academics.utils import current_academic_year
from apps.students.models import (
    Enrollment,
    EnrollmentStatus,
    Guardian,
    Student,
    StudentStatus,
)

from .access import accessible_schools, user_can_import
from .excel import build_workbook
from .forms import ExcelImportForm
from .import_service import run_import
from .models import Organization
from .selectors import tenant_scoped_view


def _school_context(school):
    return {
        "school": school,
        "current_year": current_academic_year(school),
        "years": AcademicYear.objects.filter(school=school).order_by("-start_date"),
    }


@login_required
def home(request):
    schools = list(accessible_schools(request.user))
    if not schools:
        return render(request, "tenancy/no_access.html", status=403)
    if len(schools) == 1:
        school = schools[0]
        return redirect(
            "school:dashboard",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    groups = {}
    for school in schools:
        groups.setdefault(school.organization, []).append(school)
    return render(request, "tenancy/home.html", {"groups": groups})


@login_required
def organization_home(request, org_slug):
    organization = get_object_or_404(Organization.all_objects, slug=org_slug)
    schools = [
        school
        for school in accessible_schools(request.user)
        if school.organization_id == organization.id
    ]
    if not schools:
        raise PermissionDenied("Vous n'avez pas accès à cette organisation.")
    if len(schools) == 1:
        school = schools[0]
        return redirect(
            "school:dashboard",
            org_slug=school.organization.slug,
            school_code=school.code,
        )
    return render(
        request,
        "tenancy/organization_home.html",
        {"organization": organization, "schools": schools},
    )


@login_required
@tenant_scoped_view
def dashboard(request, org_slug, school_code):
    school = request.school
    context = _school_context(school)
    year = context["current_year"]

    student_count = Student.objects.filter(
        school=school, status=StudentStatus.ACTIVE
    ).count()
    guardian_count = Guardian.objects.filter(
        organization=school.organization
    ).count()

    class_count = 0
    enrollment_count = 0
    capacity = 0
    occupancy_rate = 0
    recent_enrollments = Enrollment.objects.none()

    if year:
        classes = SchoolClass.objects.filter(school=school, academic_year=year)
        class_count = classes.count()
        capacity = classes.aggregate(total=Sum("capacity"))["total"] or 0
        enrollments = Enrollment.objects.filter(
            school=school, academic_year=year
        )
        enrollment_count = enrollments.filter(
            status=EnrollmentStatus.ACTIVE
        ).count()
        if capacity:
            occupancy_rate = round(enrollment_count * 100 / capacity)
        recent_enrollments = enrollments.select_related(
            "student", "school_class"
        ).order_by("-created_at")[:8]

    context.update(
        {
            "student_count": student_count,
            "guardian_count": guardian_count,
            "class_count": class_count,
            "enrollment_count": enrollment_count,
            "capacity": capacity,
            "occupancy_rate": occupancy_rate,
            "recent_enrollments": recent_enrollments,
        }
    )
    return render(request, "tenancy/dashboard.html", context)


@login_required
@tenant_scoped_view
def excel_import(request, org_slug, school_code):
    school = request.school
    if not user_can_import(request.user, school):
        raise PermissionDenied(
            "Vous n'avez pas le droit d'importer des données dans cette école."
        )
    report = None
    dry_run = None
    form = ExcelImportForm(
        request.POST or None,
        request.FILES or None,
        school=school,
    )

    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["fichier"]
        academic_year = form.cleaned_data["annee"]
        dry_run = form.cleaned_data["dry_run"]

        try:
            workbook = load_workbook(
                upload, data_only=True, read_only=True
            )
        except Exception:
            form.add_error(
                "fichier",
                "Impossible de lire ce classeur. Vérifiez qu'il s'agit "
                "bien d'un fichier Excel .xlsx non protégé.",
            )
        else:
            report = run_import(
                workbook,
                school.organization,
                school,
                academic_year,
                dry_run=dry_run,
                create_classes=form.cleaned_data["creer_classes"],
            )
            if report.has_errors:
                messages.error(
                    request,
                    "Import annulé : aucune donnée n'a été enregistrée.",
                )
            elif dry_run:
                messages.success(
                    request,
                    "Simulation réussie : aucune donnée n'a été enregistrée.",
                )
            else:
                messages.success(request, "Import terminé avec succès.")

    return render(
        request,
        "tenancy/excel_import.html",
        {
            "school": school,
            "form": form,
            "report": report,
            "dry_run": dry_run,
            "has_years": form.fields["annee"].queryset.exists(),
        },
    )


@login_required
@tenant_scoped_view
def excel_template(request, org_slug, school_code):
    school = request.school
    if not user_can_import(request.user, school):
        raise PermissionDenied(
            "Vous n'avez pas le droit de télécharger ce modèle."
        )
    workbook = build_workbook(school=school)

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )
    response["Content-Disposition"] = (
        f'attachment; filename="modele_import_{school.code}.xlsx"'
    )
    workbook.save(response)
    return response
