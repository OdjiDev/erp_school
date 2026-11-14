from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from apps.students.models import EnrollmentStatus, StudentGuardian
from apps.tenancy.access import user_can_manage_structure
from apps.tenancy.selectors import tenant_scoped_view

from .forms import (
    AcademicYearForm,
    ClassForm,
    ClassSubjectAddForm,
    ClassSubjectTeacherFormSet,
    CurriculumSubjectForm,
    LevelForm,
    SeriesForm,
    SubjectForm,
    default_academic_year,
)
from .models import (
    AcademicYear,
    ClassSubject,
    Curriculum,
    CurriculumSubject,
    Level,
    SchoolClass,
    Series,
    Subject,
)
from .utils import current_academic_year


def _ensure_structure_access(request):
    if not user_can_manage_structure(request.user, request.school):
        raise PermissionDenied(
            "Vous n'avez pas le droit de modifier la structure académique."
        )


def _form_context(school, title, intro, cancel_url):
    return {
        "school": school,
        "form_title": title,
        "form_intro": intro,
        "cancel_url": cancel_url,
    }


@login_required
@tenant_scoped_view
def structure(request, org_slug, school_code):
    _ensure_structure_access(request)
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    levels = (
        Level.objects.filter(school=school)
        .prefetch_related("series")
        .order_by("order", "code")
    )
    context = {
        "school": school,
        "years": years,
        "levels": levels,
        "current_year": AcademicYear.objects.filter(
            school=school, is_current=True
        ).first(),
    }
    return render(request, "academics/structure.html", context)


@login_required
@tenant_scoped_view
def academic_year_create(request, org_slug, school_code):
    _ensure_structure_access(request)
    school = request.school
    form = AcademicYearForm(
        request.POST or None,
        school=school,
        initial=default_academic_year() if request.method == "GET" else None,
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            year = form.save(commit=False)
            year.school = school
            year.save()
            if year.is_current:
                AcademicYear.objects.filter(
                    school=school, is_current=True
                ).exclude(pk=year.pk).update(is_current=False)
        messages.success(
            request, f"Année scolaire « {year.name} » créée."
        )
        return redirect(
            "school:structure",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    context = _form_context(
        school,
        "Nouvelle année scolaire",
        "Définissez la période de l'année et indiquez si elle est courante.",
        "school:structure",
    )
    context["form"] = form
    return render(request, "academics/structure_form.html", context)


@login_required
@tenant_scoped_view
def academic_year_edit(request, org_slug, school_code, year_id):
    _ensure_structure_access(request)
    school = request.school
    year = get_object_or_404(AcademicYear, pk=year_id, school=school)
    form = AcademicYearForm(
        request.POST or None, instance=year, school=school
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            year = form.save(commit=False)
            year.school = school
            year.save()
            if year.is_current:
                AcademicYear.objects.filter(
                    school=school, is_current=True
                ).exclude(pk=year.pk).update(is_current=False)
        messages.success(
            request, f"Année scolaire « {year.name} » mise à jour."
        )
        return redirect(
            "school:structure",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    context = _form_context(
        school,
        f"Modifier l'année {year.name}",
        "Une seule année peut être marquée comme courante.",
        "school:structure",
    )
    context["form"] = form
    return render(request, "academics/structure_form.html", context)


@login_required
@tenant_scoped_view
def level_create(request, org_slug, school_code):
    _ensure_structure_access(request)
    school = request.school
    next_order = (
        Level.objects.filter(school=school).aggregate(Max("order"))[
            "order__max"
        ]
        or 0
    ) + 1
    form = LevelForm(
        request.POST or None,
        school=school,
        initial={"order": next_order} if request.method == "GET" else None,
    )

    if request.method == "POST" and form.is_valid():
        level = form.save(commit=False)
        level.school = school
        level.save()
        messages.success(request, f"Niveau « {level.name} » créé.")
        return redirect(
            "school:structure",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    context = _form_context(
        school,
        "Nouveau niveau",
        "Le code du niveau est utilisé dans les imports et les URLs internes.",
        "school:structure",
    )
    context["form"] = form
    return render(request, "academics/structure_form.html", context)


@login_required
@tenant_scoped_view
def level_edit(request, org_slug, school_code, level_id):
    _ensure_structure_access(request)
    school = request.school
    level = get_object_or_404(Level, pk=level_id, school=school)
    form = LevelForm(request.POST or None, instance=level, school=school)

    if request.method == "POST" and form.is_valid():
        level = form.save(commit=False)
        level.school = school
        level.save()
        messages.success(request, f"Niveau « {level.name} » mis à jour.")
        return redirect(
            "school:structure",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    context = _form_context(
        school,
        f"Modifier le niveau {level.name}",
        "Modifier le code d'un niveau existant peut affecter les imports.",
        "school:structure",
    )
    context["form"] = form
    return render(request, "academics/structure_form.html", context)


@login_required
@tenant_scoped_view
def series_create(request, org_slug, school_code, level_id):
    _ensure_structure_access(request)
    school = request.school
    level = get_object_or_404(Level, pk=level_id, school=school)
    form = SeriesForm(request.POST or None, school=school, level=level)

    if request.method == "POST" and form.is_valid():
        series = form.save(commit=False)
        series.level = level
        series.save()
        messages.success(
            request,
            f"Série « {series.name} » créée pour {level.name}.",
        )
        return redirect(
            "school:structure",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    context = _form_context(
        school,
        f"Nouvelle série — {level.name}",
        (
            "La série est rattachée au niveau affiché et ne peut pas en être "
            "déplacée."
        ),
        "school:structure",
    )
    context["form"] = form
    context["level"] = level
    return render(request, "academics/structure_form.html", context)


@login_required
@tenant_scoped_view
def series_edit(request, org_slug, school_code, series_id):
    _ensure_structure_access(request)
    school = request.school
    series = get_object_or_404(
        Series, pk=series_id, level__school=school
    )
    form = SeriesForm(
        request.POST or None,
        instance=series,
        school=school,
        level=series.level,
    )

    if request.method == "POST" and form.is_valid():
        series = form.save(commit=False)
        series.save()
        messages.success(request, f"Série « {series.name} » mise à jour.")
        return redirect(
            "school:structure",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    context = _form_context(
        school,
        f"Modifier la série {series.name}",
        "Le niveau de la série ne peut pas être modifié.",
        "school:structure",
    )
    context["form"] = form
    context["level"] = series.level
    return render(request, "academics/structure_form.html", context)


@login_required
@tenant_scoped_view
def class_list(request, org_slug, school_code):
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
        classes = (
            SchoolClass.objects.filter(
                school=school, academic_year=selected_year
            )
            .select_related("academic_year", "level", "series", "site")
            .annotate(
                active_count=Count(
                    "enrollments",
                    filter=Q(enrollments__status=EnrollmentStatus.ACTIVE),
                )
            )
            .order_by("level__order", "series__code", "section")
        )

    context = {
        "school": school,
        "years": years,
        "selected_year": selected_year,
        "classes": classes,
    }
    return render(request, "academics/class_list.html", context)


@login_required
@tenant_scoped_view
def subject_list(request, org_slug, school_code):
    _ensure_structure_access(request)
    school = request.school
    subjects = (
        Subject.objects.filter(school=school)
        .annotate(usage_count=Count("curriculum_subjects"))
        .order_by("name")
    )
    return render(
        request,
        "academics/subject_list.html",
        {"school": school, "subjects": subjects},
    )


@login_required
@tenant_scoped_view
def subject_create(request, org_slug, school_code):
    _ensure_structure_access(request)
    school = request.school
    form = SubjectForm(request.POST or None, school=school)

    if request.method == "POST" and form.is_valid():
        subject = form.save()
        messages.success(request, f"Matière « {subject.name} » créée.")
        return redirect(
            "school:subject_list",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": "Nouvelle matière",
            "form_intro": (
                "Les matières sont ensuite associées aux séries avec un "
                "coefficient."
            ),
            "form": form,
            "submit_label": "Créer la matière",
            "cancel_url": reverse(
                "school:subject_list",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                },
            ),
        },
    )


@login_required
@tenant_scoped_view
def subject_edit(request, org_slug, school_code, subject_id):
    _ensure_structure_access(request)
    school = request.school
    subject = get_object_or_404(Subject, pk=subject_id, school=school)
    form = SubjectForm(request.POST or None, instance=subject, school=school)

    if request.method == "POST" and form.is_valid():
        subject = form.save()
        messages.success(request, "Matière mise à jour.")
        return redirect(
            "school:subject_list",
            org_slug=school.organization.slug,
            school_code=school.code,
        )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": f"Modifier la matière {subject.name}",
            "form_intro": (
                "Modifier le code d'une matière peut affecter les imports."
            ),
            "form": form,
            "submit_label": "Enregistrer",
            "cancel_url": reverse(
                "school:subject_list",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                },
            ),
        },
    )


def _curriculum_selection(request):
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    selected_year = None
    year_id = request.GET.get("annee")
    if year_id:
        try:
            selected_year = years.get(pk=year_id)
        except (AcademicYear.DoesNotExist, ValidationError, ValueError):
            selected_year = None
    selected_year = selected_year or current_academic_year(school) or years.first()

    levels = Level.objects.filter(school=school).order_by("order", "code")
    selected_level = None
    level_id = request.GET.get("niveau")
    if level_id:
        try:
            selected_level = levels.get(pk=level_id)
        except (Level.DoesNotExist, ValidationError, ValueError):
            selected_level = None
    selected_level = selected_level or levels.first()

    series_list = Series.objects.none()
    selected_series = None
    if selected_level is not None:
        series_list = (
            Series.objects.filter(level=selected_level)
            .select_related("level")
            .order_by("code")
        )
        series_id = request.GET.get("serie")
        if series_id:
            try:
                selected_series = series_list.get(pk=series_id)
            except (Series.DoesNotExist, ValidationError, ValueError):
                selected_series = None
        selected_series = selected_series or series_list.first()

    return {
        "years": years,
        "levels": levels,
        "series_list": series_list,
        "selected_year": selected_year,
        "selected_level": selected_level,
        "selected_series": selected_series,
    }


@login_required
@tenant_scoped_view
def curriculum_list(request, org_slug, school_code):
    _ensure_structure_access(request)
    school = request.school
    selection = _curriculum_selection(request)
    year = selection["selected_year"]
    level = selection["selected_level"]
    series = selection["selected_series"]

    curriculum = None
    if year and level and series:
        curriculum = Curriculum.objects.filter(
            school=school,
            academic_year=year,
            level=level,
            series=series,
        ).first()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create" and year and level and series:
            curriculum, created = Curriculum.objects.get_or_create(
                school=school,
                academic_year=year,
                level=level,
                series=series,
            )
            if created:
                messages.success(
                    request,
                    f"Programme {level.name} {series.name} créé pour "
                    f"{year.name}.",
                )
            else:
                messages.info(request, "Ce programme existe déjà.")
            return redirect(
                f"{reverse('school:curriculum_list', kwargs={'org_slug': school.organization.slug, 'school_code': school.code})}"
                f"?annee={year.pk}&niveau={level.pk}&serie={series.pk}"
            )
        if action == "add" and curriculum is not None:
            form = CurriculumSubjectForm(
                request.POST, curriculum=curriculum
            )
            if form.is_valid():
                item = form.save()
                messages.success(
                    request,
                    f"Coefficient de {item.subject.name} enregistré.",
                )
                return redirect(
                    f"{reverse('school:curriculum_list', kwargs={'org_slug': school.organization.slug, 'school_code': school.code})}"
                    f"?annee={year.pk}&niveau={level.pk}&serie={series.pk}"
                )
        else:
            form = None
    else:
        form = None

    items = CurriculumSubject.objects.none()
    if curriculum is not None:
        items = (
            CurriculumSubject.objects.filter(curriculum=curriculum)
            .select_related("subject")
            .order_by("subject__name")
        )

    subjects = Subject.objects.filter(school=school)
    available_subjects = subjects
    if curriculum is not None:
        available_subjects = subjects.exclude(
            id__in=items.values_list("subject_id", flat=True)
        )
    if form is None and curriculum is not None:
        form = CurriculumSubjectForm(curriculum=curriculum)

    context = {
        "school": school,
        **selection,
        "curriculum": curriculum,
        "items": items,
        "form": form,
        "has_subjects": subjects.exists(),
        "available_subjects": available_subjects,
        "query_string": (
            f"annee={year.pk}&niveau={level.pk}&serie={series.pk}"
            if year and level and series
            else ""
        ),
    }
    return render(request, "academics/curriculum_list.html", context)


@login_required
@tenant_scoped_view
def curriculum_subject_edit(
    request, org_slug, school_code, curriculum_subject_id
):
    _ensure_structure_access(request)
    school = request.school
    item = get_object_or_404(
        CurriculumSubject.objects.select_related(
            "curriculum", "subject", "curriculum__academic_year",
            "curriculum__level", "curriculum__series",
        ),
        pk=curriculum_subject_id,
        curriculum__school=school,
    )
    form = CurriculumSubjectForm(
        request.POST or None, instance=item, curriculum=item.curriculum, editing=True
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Coefficient mis à jour.")
        curriculum = item.curriculum
        return redirect(
            f"{reverse('school:curriculum_list', kwargs={'org_slug': school.organization.slug, 'school_code': school.code})}"
            f"?annee={curriculum.academic_year_id}"
            f"&niveau={curriculum.level_id}&serie={curriculum.series_id}"
        )

    return render(
        request,
        "generic_form.html",
        {
            "school": school,
            "form_title": f"Coefficient — {item.subject.name}",
            "form_intro": (
                f"{item.curriculum.academic_year.name} · "
                f"{item.curriculum.level.name} "
                f"{item.curriculum.series.name}"
            ),
            "form": form,
            "submit_label": "Enregistrer",
            "cancel_url": (
                f"{reverse('school:curriculum_list', kwargs={'org_slug': school.organization.slug, 'school_code': school.code})}"
                f"?annee={item.curriculum.academic_year_id}"
                f"&niveau={item.curriculum.level_id}"
                f"&serie={item.curriculum.series_id}"
            ),
        },
    )


@login_required
@tenant_scoped_view
def class_create(request, org_slug, school_code):
    _ensure_structure_access(request)
    school = request.school
    form = ClassForm(request.POST or None, school=school)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            school_class = form.save()
            curriculum = Curriculum.objects.filter(
                school=school,
                academic_year=school_class.academic_year,
                level=school_class.level,
                series=school_class.series,
            ).first()
            copied = 0
            if curriculum is not None:
                for item in curriculum.curriculum_subjects.all():
                    _, created = ClassSubject.objects.get_or_create(
                        school_class=school_class, subject=item.subject
                    )
                    copied += int(created)
        message = f"Classe « {school_class.display_name} » créée."
        if copied:
            message += f" {copied} matière(s) reprise(s) du programme."
        messages.success(request, message)
        return redirect(
            "school:class_detail",
            org_slug=school.organization.slug,
            school_code=school.code,
            class_id=school_class.id,
        )

    return render(
        request,
        "academics/class_form.html",
        {
            "school": school,
            "form_title": "Nouvelle classe",
            "form_intro": (
                "Une classe combine une année, un niveau, une série et une "
                "section. Les matières du programme sont reprises "
                "automatiquement."
            ),
            "form": form,
            "submit_label": "Créer la classe",
            "cancel_url": reverse(
                "school:class_list",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                },
            ),
        },
    )


@login_required
@tenant_scoped_view
def class_edit(request, org_slug, school_code, class_id):
    _ensure_structure_access(request)
    school = request.school
    school_class = get_object_or_404(
        SchoolClass, pk=class_id, school=school
    )
    form = ClassForm(
        request.POST or None, instance=school_class, school=school
    )

    if request.method == "POST" and form.is_valid():
        school_class = form.save()
        messages.success(request, "Classe mise à jour.")
        return redirect(
            "school:class_detail",
            org_slug=school.organization.slug,
            school_code=school.code,
            class_id=school_class.id,
        )

    return render(
        request,
        "academics/class_form.html",
        {
            "school": school,
            "form_title": f"Modifier {school_class.display_name}",
            "form_intro": (
                f"{school_class.academic_year.name} · "
                f"{school_class.level.name} · {school_class.series.name}"
            ),
            "form": form,
            "submit_label": "Enregistrer",
            "cancel_url": reverse(
                "school:class_detail",
                kwargs={
                    "org_slug": school.organization.slug,
                    "school_code": school.code,
                    "class_id": school_class.id,
                },
            ),
        },
    )


def _class_students(school_class):
    enrollments = list(
        school_class.enrollments.select_related("student").order_by(
            "student__last_name", "student__first_name"
        )
    )
    student_ids = [enrollment.student_id for enrollment in enrollments]
    primary_guardians = {
        link.student_id: link.guardian
        for link in StudentGuardian.objects.filter(
            student_id__in=student_ids, is_primary=True
        ).select_related("guardian")
    }
    for enrollment in enrollments:
        enrollment.primary_guardian = primary_guardians.get(
            enrollment.student_id
        )
    return enrollments


@login_required
@tenant_scoped_view
def class_detail(request, org_slug, school_code, class_id):
    school = request.school
    school_class = get_object_or_404(
        SchoolClass.objects.select_related(
            "academic_year", "level", "series", "site"
        ),
        pk=class_id,
        school=school,
    )
    enrollments = _class_students(school_class)
    active_count = sum(
        1
        for enrollment in enrollments
        if enrollment.status == EnrollmentStatus.ACTIVE
    )
    class_subjects = (
        ClassSubject.objects.filter(school_class=school_class)
        .select_related("subject", "teacher")
        .order_by("subject__name")
    )
    return render(
        request,
        "academics/class_detail.html",
        {
            "school": school,
            "school_class": school_class,
            "enrollments": enrollments,
            "active_count": active_count,
            "class_subjects": class_subjects,
        },
    )


@login_required
@tenant_scoped_view
def class_export(request, org_slug, school_code, class_id):
    school = request.school
    school_class = get_object_or_404(
        SchoolClass.objects.select_related(
            "academic_year", "level", "series"
        ),
        pk=class_id,
        school=school,
    )
    enrollments = [
        enrollment
        for enrollment in _class_students(school_class)
        if enrollment.status == EnrollmentStatus.ACTIVE
    ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Liste de classe"
    headers = [
        "Matricule",
        "Nom",
        "Prénoms",
        "Sexe",
        "Date de naissance",
        "Tuteur principal",
        "Téléphone tuteur",
    ]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for enrollment in enrollments:
        student = enrollment.student
        guardian = enrollment.primary_guardian
        sheet.append(
            [
                student.matricule,
                student.last_name,
                student.first_name,
                student.get_gender_display() or "",
                student.date_of_birth.strftime("%d/%m/%Y")
                if student.date_of_birth
                else "",
                guardian.full_name if guardian else "",
                guardian.phone if guardian else "",
            ]
        )

    widths = [18, 22, 24, 10, 16, 26, 20]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"

    filename = (
        slugify(
            f"liste-{school_class.academic_year.name}-"
            f"{school_class.display_name}-{school.code}"
        )
        or "liste-classe"
    ) + ".xlsx"
    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


@login_required
@tenant_scoped_view
def class_assignments(request, org_slug, school_code, class_id):
    _ensure_structure_access(request)
    school = request.school
    school_class = get_object_or_404(
        SchoolClass.objects.select_related(
            "academic_year", "level", "series"
        ),
        pk=class_id,
        school=school,
    )
    action = request.POST.get("action") if request.method == "POST" else None

    formset = ClassSubjectTeacherFormSet(
        request.POST if action == "save" else None,
        queryset=ClassSubject.objects.filter(
            school_class=school_class
        ).select_related("subject", "teacher"),
        form_kwargs={"school": school},
    )
    add_form = ClassSubjectAddForm(
        request.POST if action == "add" else None,
        school_class=school_class,
    )

    if request.method == "POST":
        if action == "save" and formset.is_valid():
            formset.save()
            messages.success(request, "Affectations enregistrées.")
            return redirect(
                "school:class_assignments",
                org_slug=school.organization.slug,
                school_code=school.code,
                class_id=school_class.id,
            )
        if action == "add" and add_form.is_valid():
            assignment = ClassSubject.objects.create(
                school_class=school_class,
                subject=add_form.cleaned_data["subject"],
                teacher=add_form.cleaned_data["teacher"],
            )
            messages.success(
                request,
                f"Matière « {assignment.subject.name} » ajoutée aux "
                "affectations.",
            )
            return redirect(
                "school:class_assignments",
                org_slug=school.organization.slug,
                school_code=school.code,
                class_id=school_class.id,
            )

    return render(
        request,
        "academics/class_assignments.html",
        {
            "school": school,
            "school_class": school_class,
            "formset": formset,
            "add_form": add_form,
            "has_teachers": add_form.fields["teacher"].queryset.exists(),
        },
    )

