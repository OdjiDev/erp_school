from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.academics.models import AcademicYear, SchoolClass
from apps.academics.utils import current_academic_year
from apps.tenancy.access import user_can_manage_students
from apps.tenancy.selectors import tenant_scoped_view

from .forms import (
    EnrollmentForm,
    GuardianCreateLinkForm,
    GuardianForm,
    GuardianLinkEditForm,
    GuardianLinkForm,
    StudentForm,
)
from .models import (
    Enrollment,
    EnrollmentStatus,
    Guardian,
    Student,
    StudentGuardian,
    StudentStatus,
)


def _ensure_student_access(request):
    if not user_can_manage_students(request.user, request.school):
        raise PermissionDenied(
            "Vous n'avez pas le droit de modifier les élèves de cette école."
        )


def _school_kwargs(school):
    return {
        "org_slug": school.organization.slug,
        "school_code": school.code,
    }


def _form_context(school, title, intro, cancel_url):
    return {
        "school": school,
        "form_title": title,
        "form_intro": intro,
        "cancel_url": cancel_url,
    }


def _save_guardian_link(
    student, guardian, relationship, is_primary, is_financial_responsible
):
    with transaction.atomic():
        if is_primary:
            StudentGuardian.all_objects.filter(
                student=student, is_primary=True
            ).update(is_primary=False)
        link = StudentGuardian(
            student=student,
            guardian=guardian,
            relationship=relationship,
            is_primary=is_primary,
            is_financial_responsible=is_financial_responsible,
        )
        link.full_clean()
        link.save()
    return link


@login_required
@tenant_scoped_view
def student_list(request, org_slug, school_code):
    school = request.school
    year = current_academic_year(school)

    students = Student.objects.filter(school=school)
    query = request.GET.get("q", "").strip()
    if query:
        students = students.filter(
            Q(matricule__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    status = request.GET.get("statut", "")
    if status in StudentStatus.values:
        students = students.filter(status=status)

    students = students.order_by("last_name", "first_name", "matricule")
    paginator = Paginator(students, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    current_enrollments = {}
    if year:
        current_enrollments = {
            enrollment.student_id: enrollment
            for enrollment in Enrollment.objects.filter(
                school=school,
                academic_year=year,
                student_id__in=[student.id for student in page_obj.object_list],
            ).select_related("school_class")
        }
    for student in page_obj.object_list:
        student.current_enrollment = current_enrollments.get(student.id)

    params = request.GET.copy()
    params.pop("page", None)
    context = {
        "school": school,
        "current_year": year,
        "page_obj": page_obj,
        "students": page_obj.object_list,
        "query": query,
        "status": status,
        "status_choices": StudentStatus.choices,
        "base_query": params.urlencode(),
        "total_count": paginator.count,
    }
    return render(request, "students/student_list.html", context)


@login_required
@tenant_scoped_view
def student_detail(request, org_slug, school_code, student_id):
    school = request.school
    student = get_object_or_404(Student, pk=student_id, school=school)
    guardianships = student.guardianships.select_related("guardian").order_by(
        "-is_primary", "guardian__last_name", "guardian__first_name"
    )
    enrollments = student.enrollments.select_related(
        "academic_year", "school_class"
    ).order_by("-academic_year__start_date")
    current_year = current_academic_year(school)
    current_enrollment = None
    if current_year:
        current_enrollment = next(
            (
                enrollment
                for enrollment in enrollments
                if enrollment.academic_year_id == current_year.id
            ),
            None,
        )
    context = {
        "school": school,
        "student": student,
        "guardianships": guardianships,
        "enrollments": enrollments,
        "current_year": current_year,
        "current_enrollment": current_enrollment,
    }
    return render(request, "students/student_detail.html", context)


@login_required
@tenant_scoped_view
def student_create(request, org_slug, school_code):
    _ensure_student_access(request)
    school = request.school
    form = StudentForm(request.POST or None, school=school)

    if request.method == "POST" and form.is_valid():
        student = form.save()
        messages.success(
            request,
            f"Élève « {student.full_name} » créé avec le matricule "
            f"{student.matricule}.",
        )
        return redirect(
            "school:student_detail",
            student_id=student.id,
            **_school_kwargs(school),
        )

    context = _form_context(
        school,
        "Nouvel élève",
        "Renseignez l'identité de l'élève. L'inscription se fait ensuite.",
        reverse("school:student_list", kwargs=_school_kwargs(school)),
    )
    context["form"] = form
    context["submit_label"] = "Créer l'élève"
    return render(request, "generic_form.html", context)


@login_required
@tenant_scoped_view
def student_edit(request, org_slug, school_code, student_id):
    _ensure_student_access(request)
    school = request.school
    student = get_object_or_404(Student, pk=student_id, school=school)
    form = StudentForm(
        request.POST or None, instance=student, school=school
    )

    if request.method == "POST" and form.is_valid():
        student = form.save()
        messages.success(request, "Fiche élève mise à jour.")
        return redirect(
            "school:student_detail",
            student_id=student.id,
            **_school_kwargs(school),
        )

    context = _form_context(
        school,
        f"Modifier {student.full_name}",
        f"Matricule {student.matricule}.",
        reverse(
            "school:student_detail",
            kwargs={**_school_kwargs(school), "student_id": student.id},
        ),
    )
    context["form"] = form
    context["submit_label"] = "Enregistrer"
    return render(request, "generic_form.html", context)


@login_required
@tenant_scoped_view
def guardian_list(request, org_slug, school_code):
    school = request.school
    guardians = (
        Guardian.objects.filter(organization=school.organization)
        .annotate(
            student_count=Count(
                "studentships",
                filter=Q(studentships__student__school=school),
                distinct=True,
            )
        )
        .order_by("last_name", "first_name")
    )
    query = request.GET.get("q", "").strip()
    if query:
        guardians = guardians.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
        )
    paginator = Paginator(guardians, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "students/guardian_list.html",
        {
            "school": school,
            "page_obj": page_obj,
            "guardians": page_obj.object_list,
            "query": query,
            "total_count": paginator.count,
        },
    )


@login_required
@tenant_scoped_view
def guardian_detail(request, org_slug, school_code, guardian_id):
    school = request.school
    guardian = get_object_or_404(
        Guardian, pk=guardian_id, organization=school.organization
    )
    links = (
        StudentGuardian.objects.filter(
            guardian=guardian, student__school=school
        )
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    context = {
        "school": school,
        "guardian": guardian,
        "links": links,
    }
    return render(request, "students/guardian_detail.html", context)


@login_required
@tenant_scoped_view
def guardian_create(request, org_slug, school_code):
    _ensure_student_access(request)
    school = request.school
    form = GuardianForm(
        request.POST or None, organization=school.organization
    )

    if request.method == "POST" and form.is_valid():
        guardian = form.save()
        messages.success(
            request, f"Tuteur « {guardian.full_name} » créé."
        )
        return redirect(
            "school:guardian_detail",
            guardian_id=guardian.id,
            **_school_kwargs(school),
        )

    context = _form_context(
        school,
        "Nouveau tuteur",
        "Le tuteur est partagé entre les écoles de l'organisation.",
        reverse("school:guardian_list", kwargs=_school_kwargs(school)),
    )
    context["form"] = form
    context["submit_label"] = "Créer le tuteur"
    return render(request, "generic_form.html", context)


@login_required
@tenant_scoped_view
def guardian_edit(request, org_slug, school_code, guardian_id):
    _ensure_student_access(request)
    school = request.school
    guardian = get_object_or_404(
        Guardian, pk=guardian_id, organization=school.organization
    )
    form = GuardianForm(
        request.POST or None,
        instance=guardian,
        organization=school.organization,
    )

    if request.method == "POST" and form.is_valid():
        guardian = form.save()
        messages.success(request, "Fiche tuteur mise à jour.")
        return redirect(
            "school:guardian_detail",
            guardian_id=guardian.id,
            **_school_kwargs(school),
        )

    context = _form_context(
        school,
        f"Modifier {guardian.full_name}",
        f"Téléphone {guardian.phone}.",
        reverse(
            "school:guardian_detail",
            kwargs={**_school_kwargs(school), "guardian_id": guardian.id},
        ),
    )
    context["form"] = form
    context["submit_label"] = "Enregistrer"
    return render(request, "generic_form.html", context)


@login_required
@tenant_scoped_view
def student_guardian_create(request, org_slug, school_code, student_id):
    _ensure_student_access(request)
    school = request.school
    student = get_object_or_404(Student, pk=student_id, school=school)
    existing_guardians = Guardian.objects.filter(
        organization=school.organization
    ).order_by("last_name", "first_name")
    has_primary = student.guardianships.filter(is_primary=True).exists()

    link_form = GuardianLinkForm(
        request.POST if request.POST.get("action") == "existing" else None,
        student=student,
    )
    new_form = GuardianCreateLinkForm(
        request.POST if request.POST.get("action") == "new" else None,
        organization=school.organization,
        initial={"is_primary": not has_primary},
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "existing" and link_form.is_valid():
            link = _save_guardian_link(
                student,
                link_form.cleaned_data["guardian"],
                link_form.cleaned_data["relationship"],
                link_form.cleaned_data["is_primary"],
                link_form.cleaned_data["is_financial_responsible"],
            )
            messages.success(
                request,
                f"Tuteur « {link.guardian.full_name} » lié à "
                f"{student.full_name}.",
            )
            return redirect(
                "school:student_detail",
                student_id=student.id,
                **_school_kwargs(school),
            )
        if action == "new" and new_form.is_valid():
            with transaction.atomic():
                guardian = new_form.save()
                _save_guardian_link(
                    student,
                    guardian,
                    new_form.cleaned_data["relationship"],
                    new_form.cleaned_data["is_primary"],
                    new_form.cleaned_data["is_financial_responsible"],
                )
            messages.success(
                request,
                f"Tuteur « {guardian.full_name} » créé et lié à "
                f"{student.full_name}.",
            )
            return redirect(
                "school:student_detail",
                student_id=student.id,
                **_school_kwargs(school),
            )

    return render(
        request,
        "students/guardian_link_create.html",
        {
            "school": school,
            "student": student,
            "link_form": link_form,
            "new_form": new_form,
            "existing_guardians": existing_guardians,
        },
    )


@login_required
@tenant_scoped_view
def student_guardian_edit(
    request, org_slug, school_code, student_id, link_id
):
    _ensure_student_access(request)
    school = request.school
    student = get_object_or_404(Student, pk=student_id, school=school)
    link = get_object_or_404(
        StudentGuardian, pk=link_id, student=student
    )
    form = GuardianLinkEditForm(request.POST or None, instance=link)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if form.cleaned_data["is_primary"]:
                StudentGuardian.all_objects.filter(
                    student=student, is_primary=True
                ).exclude(pk=link.pk).update(is_primary=False)
            form.save()
        messages.success(request, "Lien tuteur mis à jour.")
        return redirect(
            "school:student_detail",
            student_id=student.id,
            **_school_kwargs(school),
        )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": f"Modifier le lien — {link.guardian.full_name}",
            "form_intro": (
                f"{student.full_name} · {link.get_relationship_display()}"
            ),
            "form": form,
            "submit_label": "Enregistrer",
            "cancel_url": reverse(
                "school:student_detail",
                kwargs={
                    **_school_kwargs(school),
                    "student_id": student.id,
                },
            ),
        },
    )


@login_required
@tenant_scoped_view
def student_guardian_delete(
    request, org_slug, school_code, student_id, link_id
):
    _ensure_student_access(request)
    school = request.school
    if request.method != "POST":
        raise PermissionDenied("Cette action doit être confirmée.")
    student = get_object_or_404(Student, pk=student_id, school=school)
    link = get_object_or_404(
        StudentGuardian, pk=link_id, student=student
    )
    name = link.guardian.full_name
    link.delete()
    messages.success(
        request, f"Lien avec « {name} » retiré (le tuteur est conservé)."
    )
    return redirect(
        "school:student_detail",
        student_id=student.id,
        **_school_kwargs(school),
    )


@login_required
@tenant_scoped_view
def enrollment_list(request, org_slug, school_code):
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")

    selected_year = None
    year_id = request.GET.get("annee")
    if year_id:
        try:
            selected_year = years.get(pk=year_id)
        except (AcademicYear.DoesNotExist, ValidationError, ValueError):
            selected_year = None
    selected_year = selected_year or current_academic_year(school)

    classes = SchoolClass.objects.none()
    if selected_year:
        classes = SchoolClass.objects.filter(
            school=school, academic_year=selected_year
        ).order_by("level__order", "series__code", "section")

    enrollments = Enrollment.objects.filter(school=school)
    if selected_year:
        enrollments = enrollments.filter(academic_year=selected_year)

    selected_class = None
    class_id = request.GET.get("classe")
    if class_id and selected_year:
        try:
            selected_class = classes.get(pk=class_id)
        except (SchoolClass.DoesNotExist, ValidationError, ValueError):
            selected_class = None
        if selected_class is not None:
            enrollments = enrollments.filter(school_class=selected_class)

    status = request.GET.get("statut", "")
    if status in EnrollmentStatus.values:
        enrollments = enrollments.filter(status=status)

    query = request.GET.get("q", "").strip()
    if query:
        enrollments = enrollments.filter(
            Q(student__matricule__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
        )

    enrollments = enrollments.select_related(
        "student", "academic_year", "school_class"
    ).order_by(
        "school_class__level__order",
        "school_class__series__code",
        "school_class__section",
        "student__last_name",
        "student__first_name",
    )
    paginator = Paginator(enrollments, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "students/enrollment_list.html",
        {
            "school": school,
            "years": years,
            "selected_year": selected_year,
            "classes": classes,
            "selected_class": class_id or "",
            "status": status,
            "status_choices": EnrollmentStatus.choices,
            "query": query,
            "page_obj": page_obj,
            "enrollments": page_obj.object_list,
            "total_count": paginator.count,
            "base_query": params.urlencode(),
        },
    )


@login_required
@tenant_scoped_view
def enrollment_create(request, org_slug, school_code):
    _ensure_student_access(request)
    school = request.school
    current_year = current_academic_year(school)

    student = None
    student_id = request.GET.get("eleve")
    if student_id:
        try:
            student = get_object_or_404(
                Student, pk=student_id, school=school
            )
        except ValidationError:
            raise Http404("Élève introuvable.")
        if current_year and Enrollment.objects.filter(
            student=student, academic_year=current_year
        ).exists():
            messages.info(
                request,
                f"{student.full_name} est déjà inscrit pour "
                f"{current_year.name}. Modifiez cette inscription.",
            )
            return redirect(
                "school:student_detail",
                student_id=student.id,
                **_school_kwargs(school),
            )

    initial = {"student": student} if student else {}
    form = EnrollmentForm(
        request.POST or None, school=school, initial=initial
    )

    if request.method == "POST" and form.is_valid():
        enrollment = form.save()
        messages.success(
            request,
            f"{enrollment.student.full_name} inscrit en "
            f"{enrollment.school_class.display_name} "
            f"({enrollment.academic_year.name}).",
        )
        return redirect(
            "school:student_detail",
            student_id=enrollment.student_id,
            **_school_kwargs(school),
        )

    context = _form_context(
        school,
        "Nouvelle inscription",
        "Choisissez l'élève, l'année et la classe. Une seule inscription "
        "par élève et par année.",
        reverse("school:enrollment_list", kwargs=_school_kwargs(school)),
    )
    context["form"] = form
    context["submit_label"] = "Inscrire l'élève"
    return render(request, "students/enrollment_form.html", context)


@login_required
@tenant_scoped_view
def enrollment_edit(request, org_slug, school_code, enrollment_id):
    _ensure_student_access(request)
    school = request.school
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "academic_year"),
        pk=enrollment_id,
        school=school,
    )
    form = EnrollmentForm(
        request.POST or None,
        instance=enrollment,
        school=school,
        lock_identity=True,
    )

    if request.method == "POST" and form.is_valid():
        enrollment = form.save()
        messages.success(request, "Inscription mise à jour.")
        return redirect(
            "school:student_detail",
            student_id=enrollment.student_id,
            **_school_kwargs(school),
        )

    context = _form_context(
        school,
        f"Modifier l'inscription — {enrollment.student.full_name}",
        (
            f"{enrollment.academic_year.name} · "
            f"{enrollment.school_class.display_name}. L'élève et l'année "
            "sont verrouillés."
        ),
        reverse(
            "school:student_detail",
            kwargs={
                **_school_kwargs(school),
                "student_id": enrollment.student_id,
            },
        ),
    )
    context["form"] = form
    context["submit_label"] = "Enregistrer"
    return render(request, "generic_form.html", context)
