from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.forms import formset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academics.models import ClassSubject, SchoolClass
from apps.students.models import Enrollment, EnrollmentStatus
from apps.tenancy.access import (
    user_can_grade_class_subject,
    user_can_manage_grades,
    user_can_manage_grading_settings,
)
from apps.tenancy.selectors import tenant_scoped_view

from .forms import (
    AssessmentForm,
    CorrectionReasonForm,
    DeliberationForm,
    GradeEntryForm,
    GradingPeriodForm,
    PeriodReopenForm,
)
from .models import (
    Assessment,
    BulletinSnapshot,
    Deliberation,
    Grade,
    GradeRevision,
    GradingPeriod,
    GradingPeriodAction,
    PeriodActionType,
)
from .services import build_bulletins, capture_period_snapshots


def _ensure_grading_access(request):
    if not user_can_manage_grades(request.user, request.school):
        raise PermissionDenied("Vous n'avez pas accès aux notes de cette école.")


def _ensure_period_management(request):
    if not user_can_manage_grading_settings(request.user, request.school):
        raise PermissionDenied(
            "Seuls les responsables de l'école peuvent gérer les périodes."
        )


def _visible_classes(request):
    classes = SchoolClass.objects.filter(school=request.school).select_related(
        "academic_year", "level", "series"
    )
    if not user_can_manage_grading_settings(request.user, request.school):
        classes = classes.filter(class_subjects__teacher=request.user).distinct()
    return classes.order_by("-academic_year__start_date", "name", "section")


def _ensure_class_access(request, school_class):
    if user_can_manage_grading_settings(request.user, request.school):
        return
    if not ClassSubject.objects.filter(
        school_class=school_class, teacher=request.user
    ).exists():
        raise PermissionDenied("Cette classe ne fait pas partie de vos affectations.")


def _ensure_assessment_access(request, assessment):
    if not user_can_grade_class_subject(
        request.user, request.school, assessment.class_subject
    ):
        raise PermissionDenied(
            "Vous ne pouvez pas gérer les notes de cette matière."
        )


@login_required
@tenant_scoped_view
def grading_home(request, org_slug, school_code):
    _ensure_grading_access(request)
    school = request.school
    periods = GradingPeriod.objects.filter(school=school).select_related(
        "academic_year"
    )
    if not user_can_manage_grading_settings(request.user, school):
        periods = periods.filter(
            assessments__class_subject__teacher=request.user
        ).distinct()
    periods = periods.order_by(
        "-academic_year__start_date", "sequence", "name"
    )
    return render(
        request,
        "grading/home.html",
        {
            "school": school,
            "periods": periods,
            "can_manage_periods": user_can_manage_grading_settings(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def period_create(request, org_slug, school_code):
    _ensure_grading_access(request)
    _ensure_period_management(request)
    school = request.school
    form = GradingPeriodForm(
        request.POST or None,
        school=school,
        initial={"sequence": 1} if request.method == "GET" else None,
    )
    if request.method == "POST" and form.is_valid():
        period = form.save()
        messages.success(request, f"Période « {period.name} » créée.")
        return redirect("school:grading_home", org_slug=org_slug, school_code=school_code)
    return render(
        request,
        "grading/form.html",
        {
            "school": school,
            "form": form,
            "title": "Nouvelle période d'évaluation",
            "intro": (
                "Créez le trimestre, semestre ou autre période utilisé par "
                "votre établissement."
            ),
            "cancel_url": "school:grading_home",
        },
    )


@login_required
@require_POST
@tenant_scoped_view
def period_close(request, org_slug, school_code, period_id):
    _ensure_grading_access(request)
    _ensure_period_management(request)
    school = request.school
    period = get_object_or_404(GradingPeriod, pk=period_id, school=school)
    if period.is_closed:
        messages.info(request, "Cette période est déjà clôturée.")
        return redirect("school:grading_home", org_slug=org_slug, school_code=school_code)

    assessments = Assessment.objects.filter(period=period)
    draft_count = assessments.filter(is_published=False).count()
    published_count = assessments.filter(is_published=True).count()
    if draft_count:
        messages.error(
            request,
            f"Clôture refusée : {draft_count} évaluation(s) ne sont pas publiées.",
        )
        return redirect("school:assessment_list", org_slug=org_slug, school_code=school_code)
    if not published_count:
        messages.error(
            request,
            "Clôture refusée : publiez au moins une évaluation pour cette période.",
        )
        return redirect("school:grading_home", org_slug=org_slug, school_code=school_code)

    classes_without_results = 0
    active_classes = SchoolClass.objects.filter(
        school=school,
        academic_year=period.academic_year,
        enrollments__status=EnrollmentStatus.ACTIVE,
    ).distinct()
    for school_class in active_classes:
        if not Assessment.objects.filter(
            period=period,
            is_published=True,
            class_subject__school_class=school_class,
        ).exists():
            classes_without_results += 1
    if classes_without_results:
        messages.error(
            request,
            f"Clôture refusée : {classes_without_results} classe(s) active(s) "
            "n'ont aucune évaluation publiée pour cette période.",
        )
        return redirect("school:grading_home", org_slug=org_slug, school_code=school_code)

    version = (
        GradingPeriodAction.objects.filter(
            period=period, action=PeriodActionType.CLOSED
        ).count()
        + 1
    )
    with transaction.atomic():
        snapshot_count = capture_period_snapshots(period, request.user, version)
        period.is_closed = True
        period.closed_at = timezone.now()
        period.closed_by = request.user
        period.save(
            update_fields=["is_closed", "closed_at", "closed_by", "updated_at"]
        )
        action = GradingPeriodAction(
            school=school,
            period=period,
            action=PeriodActionType.CLOSED,
            reason=f"Clôture de période; {snapshot_count} bulletin(s) figé(s), version {version}.",
            performed_by=request.user,
            performed_by_label=str(request.user),
        )
        action.full_clean()
        action.save()
    messages.success(
        request,
        f"Période clôturée : {snapshot_count} bulletin(s) figé(s), version {version}.",
    )
    return redirect("school:grading_home", org_slug=org_slug, school_code=school_code)


@login_required
@tenant_scoped_view
def period_reopen(request, org_slug, school_code, period_id):
    _ensure_grading_access(request)
    _ensure_period_management(request)
    school = request.school
    period = get_object_or_404(GradingPeriod, pk=period_id, school=school)
    form = PeriodReopenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not period.is_closed:
            messages.info(request, "Cette période est déjà ouverte.")
            return redirect("school:grading_home", org_slug=org_slug, school_code=school_code)
        with transaction.atomic():
            period.is_closed = False
            period.closed_at = None
            period.closed_by = None
            period.save(
                update_fields=["is_closed", "closed_at", "closed_by", "updated_at"]
            )
            action = GradingPeriodAction(
                school=school,
                period=period,
                action=PeriodActionType.REOPENED,
                reason=form.cleaned_data["reason"],
                performed_by=request.user,
                performed_by_label=str(request.user),
            )
            action.full_clean()
            action.save()
        messages.success(
            request,
            "Période rouverte. La prochaine clôture créera une nouvelle version des bulletins.",
        )
        return redirect("school:grading_home", org_slug=org_slug, school_code=school_code)
    return render(
        request,
        "grading/period_reopen.html",
        {"school": school, "period": period, "form": form},
    )


@login_required
@tenant_scoped_view
def assessment_list(request, org_slug, school_code):
    _ensure_grading_access(request)
    school = request.school
    periods = GradingPeriod.objects.filter(school=school).select_related(
        "academic_year"
    )
    classes = _visible_classes(request)
    assessments = Assessment.objects.filter(school=school).select_related(
        "period", "period__academic_year", "class_subject__subject",
        "class_subject__school_class",
    )
    if not user_can_manage_grading_settings(request.user, school):
        assessments = assessments.filter(class_subject__teacher=request.user)

    period_id = request.GET.get("periode")
    class_id = request.GET.get("classe")
    selected_period = None
    selected_class = None
    if period_id:
        selected_period = get_object_or_404(periods, pk=period_id)
        assessments = assessments.filter(period=selected_period)
    if class_id:
        selected_class = get_object_or_404(classes, pk=class_id)
        assessments = assessments.filter(
            class_subject__school_class=selected_class
        )

    return render(
        request,
        "grading/assessment_list.html",
        {
            "school": school,
            "periods": periods,
            "classes": classes,
            "assessments": assessments.order_by(
                "-held_on", "period__sequence", "class_subject__school_class__name"
            ),
            "selected_period": selected_period,
            "selected_class": selected_class,
            "can_create_period": user_can_manage_grading_settings(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def assessment_create(request, org_slug, school_code):
    _ensure_grading_access(request)
    school = request.school
    initial = {}
    if request.method == "GET":
        if request.GET.get("periode"):
            initial["period"] = request.GET["periode"]
        if request.GET.get("classe"):
            selected_class = SchoolClass.objects.filter(
                school=school, pk=request.GET["classe"]
            ).first()
            if selected_class:
                class_subjects = ClassSubject.objects.filter(
                    school_class=selected_class
                )
                if not user_can_manage_grading_settings(request.user, school):
                    class_subjects = class_subjects.filter(teacher=request.user)
                if class_subjects.count() == 1:
                    initial["class_subject"] = class_subjects.first().pk
    form = AssessmentForm(
        request.POST or None,
        school=school,
        user=request.user,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        assessment = form.save()
        messages.success(
            request,
            f"Évaluation « {assessment.title} » créée. Saisissez les notes de la classe.",
        )
        return redirect(
            "school:gradebook",
            org_slug=org_slug,
            school_code=school_code,
            assessment_id=assessment.pk,
        )
    return render(
        request,
        "grading/form.html",
        {
            "school": school,
            "form": form,
            "title": "Nouvelle évaluation",
            "intro": "Choisissez la classe, la matière, la période et le barème.",
            "cancel_url": "school:assessment_list",
        },
    )


@login_required
@tenant_scoped_view
def gradebook(request, org_slug, school_code, assessment_id):
    _ensure_grading_access(request)
    school = request.school
    assessment = get_object_or_404(
        Assessment.objects.select_related(
            "period", "class_subject__school_class", "class_subject__subject"
        ),
        pk=assessment_id,
        school=school,
    )
    _ensure_assessment_access(request, assessment)
    can_correct = user_can_manage_grading_settings(request.user, school)
    correction_mode = (
        assessment.is_published and request.GET.get("corriger") == "1"
    )
    if correction_mode and assessment.period.is_closed:
        raise PermissionDenied(
            "Rouvrez la période avant de corriger une note clôturée."
        )
    if correction_mode and not can_correct:
        raise PermissionDenied(
            "Seuls les responsables peuvent corriger une note publiée."
        )
    can_edit = (
        not assessment.period.is_closed
        and (not assessment.is_published or correction_mode)
    )
    enrollments = list(
        Enrollment.objects.filter(
            school=school,
            school_class=assessment.class_subject.school_class,
            status=EnrollmentStatus.ACTIVE,
        )
        .select_related("student")
        .order_by("student__last_name", "student__first_name")
    )
    existing = {
        grade.enrollment_id: grade
        for grade in Grade.objects.filter(assessment=assessment)
    }
    initial = []
    for enrollment in enrollments:
        grade = existing.get(enrollment.pk)
        initial.append(
            {
                "enrollment_id": enrollment.pk,
                "status": grade.status if grade else "",
                "score": grade.score if grade else None,
                "comment": grade.comment if grade else "",
            }
        )

    EntryFormSet = formset_factory(
        GradeEntryForm, extra=0, max_num=2000, validate_max=True
    )
    formset = EntryFormSet(
        request.POST or None,
        initial=initial,
        prefix="notes",
        form_kwargs={"max_score": assessment.max_score},
    )
    correction_form = CorrectionReasonForm(
        request.POST if request.method == "POST" and correction_mode else None
    )
    for enrollment, form in zip(enrollments, formset.forms):
        form.enrollment = enrollment
        if not can_edit:
            for field in form.fields.values():
                field.disabled = True
    if request.method == "POST" and can_edit:
        formset_valid = formset.is_valid()
        reason_valid = True
        if correction_mode:
            reason_valid = correction_form.is_valid()
            if formset_valid:
                for form in formset.forms:
                    if not form.cleaned_data.get("status"):
                        form.add_error(
                            "status",
                            "Une correction doit conserver une note ou un statut.",
                        )
                        formset_valid = False

        if formset_valid and reason_valid:
            expected_ids = [enrollment.pk for enrollment in enrollments]
            posted_ids = [
                form.cleaned_data["enrollment_id"] for form in formset.forms
            ]
            if posted_ids != expected_ids:
                formset._non_form_errors = formset.error_class(
                    ["La liste des élèves a changé. Rechargez la page avant de réessayer."]
                )
            else:
                expected_id_set = set(expected_ids)
                action = request.POST.get("action", "save")
                correction_count = 0
                with transaction.atomic():
                    for form in formset.forms:
                        data = form.cleaned_data
                        enrollment_id = data["enrollment_id"]
                        status = data.get("status")
                        grade = existing.get(enrollment_id)
                        if not status:
                            if grade:
                                grade.delete()
                            continue
                        previous = (
                            (grade.score, grade.status, grade.comment)
                            if grade
                            else (None, "", "")
                        )
                        if grade is None:
                            grade = Grade(
                                school=school,
                                assessment=assessment,
                                enrollment_id=enrollment_id,
                            )
                        grade.status = status
                        grade.score = data.get("score")
                        grade.comment = data.get("comment") or ""
                        grade.full_clean()
                        grade.save()

                        current = (grade.score, grade.status, grade.comment)
                        if correction_mode and previous != current:
                            revision = GradeRevision(
                                school=school,
                                grade=grade,
                                previous_score=previous[0],
                                previous_status=previous[1],
                                previous_comment=previous[2],
                                new_score=current[0],
                                new_status=current[1],
                                new_comment=current[2],
                                reason=correction_form.cleaned_data["reason"],
                                changed_by=request.user,
                                changed_by_label=str(request.user),
                            )
                            revision.full_clean()
                            revision.save()
                            correction_count += 1

                    if correction_mode:
                        if correction_count:
                            messages.success(
                                request,
                                f"{correction_count} correction(s) enregistrée(s) avec leur motif.",
                            )
                        else:
                            messages.info(request, "Aucune note n'a été modifiée.")
                    elif action == "publish":
                        saved_enrollments = set(
                            Grade.objects.filter(assessment=assessment).values_list(
                                "enrollment_id", flat=True
                            )
                        )
                        missing_count = len(expected_id_set - saved_enrollments)
                        if missing_count:
                            messages.error(
                                request,
                                f"Publication impossible : {missing_count} élève(s) "
                                "n'ont ni note ni statut d'absence/dispense.",
                            )
                        elif not enrollments:
                            messages.error(
                                request,
                                "Publication impossible : la classe ne compte aucun élève actif.",
                            )
                        else:
                            assessment.is_published = True
                            assessment.published_at = timezone.now()
                            assessment.published_by = request.user
                            assessment.save(
                                update_fields=[
                                    "is_published",
                                    "published_at",
                                    "published_by",
                                    "updated_at",
                                ]
                            )
                            messages.success(
                                request,
                                "Notes publiées. Elles alimentent maintenant les bulletins.",
                            )
                    else:
                        messages.success(request, "Saisie des notes enregistrée.")
                return redirect(
                    "school:gradebook",
                    org_slug=org_slug,
                    school_code=school_code,
                    assessment_id=assessment.pk,
                )

    revisions = []
    if can_correct:
        revisions = GradeRevision.objects.filter(
            grade__assessment=assessment
        ).select_related("grade__enrollment__student", "changed_by")

    return render(
        request,
        "grading/gradebook.html",
        {
            "school": school,
            "assessment": assessment,
            "enrollments": enrollments,
            "formset": formset,
            "is_locked": assessment.is_published or assessment.period.is_closed,
            "period_closed": assessment.period.is_closed,
            "can_edit": can_edit,
            "can_correct": can_correct,
            "correction_mode": correction_mode,
            "correction_form": correction_form,
            "revisions": revisions,
            "missing_count": max(0, len(enrollments) - len(existing)),
        },
    )


@login_required
@tenant_scoped_view
def report_card_list(request, org_slug, school_code):
    _ensure_grading_access(request)
    school = request.school
    periods = GradingPeriod.objects.filter(school=school).select_related(
        "academic_year"
    )
    classes = _visible_classes(request)
    selected_period = None
    selected_class = None
    bulletins = []

    if request.GET.get("periode"):
        selected_period = get_object_or_404(periods, pk=request.GET["periode"])
    if request.GET.get("classe"):
        selected_class = get_object_or_404(classes, pk=request.GET["classe"])
    if selected_period and selected_class:
        if selected_period.academic_year_id != selected_class.academic_year_id:
            messages.error(
                request,
                "La période et la classe doivent appartenir à la même année scolaire.",
            )
            selected_class = None
        else:
            _ensure_class_access(request, selected_class)
            bulletins = build_bulletins(selected_class, selected_period)
            snapshot_versions = {}
            enrollment_ids = [item["enrollment"].pk for item in bulletins]
            for snapshot in BulletinSnapshot.objects.filter(
                period=selected_period, enrollment_id__in=enrollment_ids
            ).order_by("enrollment_id", "-version"):
                snapshot_versions.setdefault(snapshot.enrollment_id, []).append(
                    snapshot.version
                )
            for bulletin in bulletins:
                bulletin["snapshot_versions"] = snapshot_versions.get(
                    bulletin["enrollment"].pk, []
                )

    return render(
        request,
        "grading/report_card_list.html",
        {
            "school": school,
            "periods": periods,
            "classes": classes,
            "selected_period": selected_period,
            "selected_class": selected_class,
            "bulletins": bulletins,
        },
    )


@login_required
@tenant_scoped_view
def deliberation_edit(
    request, org_slug, school_code, enrollment_id, period_id
):
    _ensure_grading_access(request)
    school = request.school
    if not user_can_manage_grading_settings(request.user, school):
        raise PermissionDenied(
            "Seuls les responsables de l'école peuvent saisir les décisions du conseil."
        )
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("academic_year", "school_class"),
        pk=enrollment_id,
        school=school,
        status=EnrollmentStatus.ACTIVE,
    )
    period = get_object_or_404(GradingPeriod, pk=period_id, school=school)
    if period.academic_year_id != enrollment.academic_year_id:
        from django.http import Http404

        raise Http404("La période et l'inscription ne correspondent pas.")
    if period.is_closed:
        raise PermissionDenied(
            "Rouvrez la période avant de modifier une décision du conseil."
        )

    deliberation = Deliberation.objects.filter(
        period=period, enrollment=enrollment
    ).first()
    if deliberation is None:
        deliberation = Deliberation(
            school=school, period=period, enrollment=enrollment
        )
    form = DeliberationForm(request.POST or None, instance=deliberation)
    if request.method == "POST" and form.is_valid():
        deliberation = form.save(commit=False)
        deliberation.school = school
        deliberation.period = period
        deliberation.enrollment = enrollment
        deliberation.decided_by = request.user
        deliberation.full_clean()
        deliberation.save()
        messages.success(request, "Décision du conseil enregistrée.")
        return redirect(
            f"{reverse('school:report_card_list', kwargs={'org_slug': org_slug, 'school_code': school_code})}"
            f"?periode={period.pk}&classe={enrollment.school_class_id}"
        )

    return render(
        request,
        "grading/deliberation_form.html",
        {
            "school": school,
            "period": period,
            "enrollment": enrollment,
            "form": form,
        },
    )


@login_required
@tenant_scoped_view
def report_card_print(request, org_slug, school_code, enrollment_id, period_id):
    _ensure_grading_access(request)
    school = request.school
    enrollment = get_object_or_404(
        Enrollment.objects.select_related(
            "student", "school_class", "academic_year", "school_class__level",
            "school_class__series", "school__organization",
        ),
        pk=enrollment_id,
        school=school,
        status=EnrollmentStatus.ACTIVE,
    )
    period = get_object_or_404(GradingPeriod.objects.select_related("academic_year"),
                               pk=period_id, school=school)
    if period.academic_year_id != enrollment.academic_year_id:
        from django.http import Http404

        raise Http404("La période et l'inscription ne correspondent pas.")
    _ensure_class_access(request, enrollment.school_class)
    version = None
    if request.GET.get("version"):
        try:
            version = int(request.GET["version"])
        except ValueError:
            from django.http import Http404

            raise Http404("Version de bulletin invalide.")
        if version <= 0:
            from django.http import Http404

            raise Http404("Version de bulletin invalide.")
        if not BulletinSnapshot.objects.filter(
            period=period, enrollment=enrollment, version=version
        ).exists():
            from django.http import Http404

            raise Http404("Cette version de bulletin n'existe pas.")
    bulletins = build_bulletins(
        enrollment.school_class, period, snapshot_version=version
    )
    bulletin = next(
        (item for item in bulletins if item["enrollment"].pk == enrollment.pk), None
    )
    if bulletin is None:
        from django.http import Http404

        raise Http404("Aucun bulletin disponible pour cette inscription.")
    snapshot_versions = list(
        BulletinSnapshot.objects.filter(period=period, enrollment=enrollment)
        .order_by("-version")
        .values_list("version", flat=True)
    )
    return render(
        request,
        "grading/report_card_print.html",
        {
            "school": school,
            "period": period,
            "bulletin": bulletin,
            "class_size": len(bulletins),
            "today": timezone.localdate(),
            "snapshot_versions": snapshot_versions,
        },
    )
