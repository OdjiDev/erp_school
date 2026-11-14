from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.academics.models import AcademicYear, ClassSubject, SchoolClass
from apps.common.tenancy import TenantModel
from apps.students.models import Enrollment
from apps.tenancy.models import School


class GradingPeriod(TenantModel):
    """Période de résultats configurable par école et année scolaire."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="grading_periods"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="grading_periods"
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=80)
    sequence = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="closed_grading_periods",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["academic_year__start_date", "sequence", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "code"],
                name="uniq_grading_period_code_per_year",
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__gt=0),
                name="grading_period_sequence_positive",
            ),
        ]
        verbose_name = "période d'évaluation"
        verbose_name_plural = "périodes d'évaluation"

    def clean(self):
        errors = {}
        self.code = (self.code or "").strip().upper()
        if self.school_id and self.academic_year_id:
            if self.academic_year.school_id != self.school_id:
                errors["academic_year"] = (
                    "L'année doit appartenir à la même école."
                )
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors["end_date"] = (
                "La date de fin doit être égale ou postérieure à la date de début."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} — {self.academic_year.name}"


class AssessmentType(models.TextChoices):
    HOMEWORK = "homework", "Devoir"
    QUIZ = "quiz", "Interrogation"
    ORAL = "oral", "Oral"
    PRACTICAL = "practical", "Travail pratique"
    COMPOSITION = "composition", "Composition"
    OTHER = "other", "Autre"


class Assessment(TenantModel):
    """Une évaluation d'une matière, pour une classe et une période."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="assessments"
    )
    class_subject = models.ForeignKey(
        ClassSubject, on_delete=models.CASCADE, related_name="assessments"
    )
    period = models.ForeignKey(
        GradingPeriod, on_delete=models.CASCADE, related_name="assessments"
    )
    title = models.CharField(max_length=120)
    assessment_type = models.CharField(
        max_length=20,
        choices=AssessmentType.choices,
        default=AssessmentType.QUIZ,
    )
    held_on = models.DateField(null=True, blank=True)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=20)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_assessments",
        null=True,
        blank=True,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="published_assessments",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["held_on", "created_at", "title"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_score__gt=0),
                name="assessment_max_score_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(weight__gt=0),
                name="assessment_weight_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "period", "is_published"]),
        ]
        verbose_name = "évaluation"
        verbose_name_plural = "évaluations"

    def clean(self):
        errors = {}
        if self.class_subject_id and self.school_id:
            if self.class_subject.school_class.school_id != self.school_id:
                errors["class_subject"] = (
                    "La matière doit appartenir à une classe de cette école."
                )
        if self.period_id and self.school_id:
            if self.period.school_id != self.school_id:
                errors["period"] = "La période doit appartenir à cette école."
        if self.class_subject_id and self.period_id:
            school_class = self.class_subject.school_class
            if school_class.academic_year_id != self.period.academic_year_id:
                errors["period"] = (
                    "La période doit appartenir à l'année de la classe."
                )
        if self.max_score is not None and self.max_score <= 0:
            errors["max_score"] = "Le barème doit être supérieur à zéro."
        if self.weight is not None and self.weight <= 0:
            errors["weight"] = "Le poids doit être supérieur à zéro."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.class_subject_id:
            self.school_id = self.class_subject.school_class.school_id
        super().save(*args, **kwargs)

    @property
    def school_class(self):
        return self.class_subject.school_class

    def __str__(self):
        return f"{self.title} — {self.class_subject.subject.name}"


class GradeStatus(models.TextChoices):
    GRADED = "graded", "Note saisie"
    ABSENT = "absent", "Absent"
    EXCUSED = "excused", "Dispensé"


class Grade(TenantModel):
    """Résultat d'un élève à une évaluation; un statut sans note reste distinct."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="grades"
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="grades"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="grades"
    )
    score = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=12, choices=GradeStatus.choices, default=GradeStatus.GRADED
    )
    comment = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["enrollment__student__last_name", "enrollment__student__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "enrollment"],
                name="uniq_grade_per_assessment_enrollment",
            ),
            models.CheckConstraint(
                condition=models.Q(score__isnull=True) | models.Q(score__gte=0),
                name="grade_score_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "assessment", "enrollment"]),
        ]
        verbose_name = "note"
        verbose_name_plural = "notes"

    def clean(self):
        errors = {}
        if self.assessment_id and self.enrollment_id:
            if self.assessment.school_id != self.enrollment.school_id:
                errors["enrollment"] = (
                    "L'inscription doit appartenir à la même école."
                )
            elif (
                self.assessment.class_subject.school_class_id
                != self.enrollment.school_class_id
            ):
                errors["enrollment"] = (
                    "L'élève doit être inscrit dans la classe de l'évaluation."
                )
        if self.score is not None and self.assessment_id:
            if self.score < 0 or self.score > self.assessment.max_score:
                errors["score"] = (
                    f"La note doit être comprise entre 0 et "
                    f"{self.assessment.max_score}."
                )
        if self.status == GradeStatus.GRADED and self.score is None:
            errors["score"] = "Saisir une note ou choisir un statut d'absence."
        if self.status != GradeStatus.GRADED and self.score is not None:
            errors["score"] = (
                "Une note chiffrée ne peut pas être associée à ce statut."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.assessment_id:
            self.school_id = self.assessment.school_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.enrollment.student} — {self.assessment}"


class GradeRevision(TenantModel):
    """Historique append-only des corrections de notes déjà publiées."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="grade_revisions"
    )
    grade = models.ForeignKey(
        Grade, on_delete=models.PROTECT, related_name="revisions"
    )
    previous_score = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    previous_status = models.CharField(
        max_length=12, choices=GradeStatus.choices, blank=True
    )
    previous_comment = models.CharField(max_length=240, blank=True)
    new_score = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    new_status = models.CharField(max_length=12, choices=GradeStatus.choices)
    new_comment = models.CharField(max_length=240, blank=True)
    reason = models.CharField(max_length=500)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="grade_revisions",
        null=True,
        blank=True,
    )
    changed_by_label = models.CharField(max_length=150)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "correction de note"
        verbose_name_plural = "historique des corrections de notes"

    def clean(self):
        if self.grade_id and self.school_id:
            if self.grade.school_id != self.school_id:
                raise ValidationError(
                    {"grade": "La note doit appartenir à cette école."}
                )
        if not (self.reason or "").strip():
            raise ValidationError({"reason": "Le motif est obligatoire."})

    def __str__(self):
        return f"Correction {self.grade} — {self.created_at:%Y-%m-%d %H:%M}"


class DeliberationOutcome(models.TextChoices):
    PROMOTED = "promoted", "Admis / promu"
    CONDITIONAL = "conditional", "Admis sous réserve"
    RETAINED = "retained", "Redoublement"
    TRANSFERRED = "transferred", "Transfert"
    PENDING = "pending", "En attente"
    OTHER = "other", "Autre décision"


class Deliberation(TenantModel):
    """Décision humaine du conseil, sans seuil automatique de réussite."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="deliberations"
    )
    period = models.ForeignKey(
        GradingPeriod, on_delete=models.CASCADE, related_name="deliberations"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="deliberations"
    )
    outcome = models.CharField(max_length=20, choices=DeliberationOutcome.choices)
    comment = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="deliberations",
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["enrollment__student__last_name", "enrollment__student__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["period", "enrollment"],
                name="uniq_deliberation_per_enrollment_period",
            )
        ]
        indexes = [models.Index(fields=["school", "period", "outcome"])]
        verbose_name = "délibération"
        verbose_name_plural = "délibérations"

    def clean(self):
        errors = {}
        if self.period_id and self.school_id:
            if self.period.school_id != self.school_id:
                errors["period"] = "La période doit appartenir à cette école."
        if self.enrollment_id and self.school_id:
            if self.enrollment.school_id != self.school_id:
                errors["enrollment"] = (
                    "L'inscription doit appartenir à cette école."
                )
        if self.period_id and self.enrollment_id:
            if self.period.academic_year_id != self.enrollment.academic_year_id:
                errors["period"] = (
                    "La période et l'inscription doivent appartenir à la même année."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.enrollment.student.full_name} — "
            f"{self.get_outcome_display()} ({self.period.name})"
        )


class PeriodActionType(models.TextChoices):
    CLOSED = "closed", "Clôture"
    REOPENED = "reopened", "Réouverture"


class GradingPeriodAction(TenantModel):
    """Journal append-only des clôtures et réouvertures de périodes."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="grading_period_actions"
    )
    period = models.ForeignKey(
        GradingPeriod, on_delete=models.CASCADE, related_name="actions"
    )
    action = models.CharField(max_length=10, choices=PeriodActionType.choices)
    reason = models.CharField(max_length=500)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="grading_period_actions",
        null=True,
        blank=True,
    )
    performed_by_label = models.CharField(max_length=150)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "action sur une période de notes"
        verbose_name_plural = "historique des périodes de notes"

    def clean(self):
        if self.period_id and self.school_id:
            if self.period.school_id != self.school_id:
                raise ValidationError(
                    {"period": "La période doit appartenir à cette école."}
                )
        if not (self.reason or "").strip():
            raise ValidationError({"reason": "Le motif est obligatoire."})

    def save(self, *args, **kwargs):
        if self.pk and type(self).all_objects.filter(pk=self.pk).exists():
            raise ValidationError("L'historique d'une période est immuable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("L'historique d'une période ne peut pas être supprimé.")


class BulletinSnapshot(TenantModel):
    """Version figée d'un bulletin au moment de la clôture d'une période."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="bulletin_snapshots"
    )
    period = models.ForeignKey(
        GradingPeriod, on_delete=models.CASCADE, related_name="bulletin_snapshots"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="bulletin_snapshots"
    )
    version = models.PositiveSmallIntegerField(default=1)
    data = models.JSONField(default=dict)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="generated_bulletin_snapshots",
        null=True,
        blank=True,
    )
    generated_by_label = models.CharField(max_length=150)

    class Meta:
        ordering = ["period", "enrollment", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["period", "enrollment", "version"],
                name="uniq_bulletin_snapshot_version",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0),
                name="bulletin_snapshot_version_positive",
            ),
        ]
        indexes = [models.Index(fields=["school", "period", "enrollment", "version"])]
        verbose_name = "version de bulletin"
        verbose_name_plural = "versions de bulletins"

    def clean(self):
        errors = {}
        if self.period_id and self.school_id:
            if self.period.school_id != self.school_id:
                errors["period"] = "La période doit appartenir à cette école."
        if self.enrollment_id and self.school_id:
            if self.enrollment.school_id != self.school_id:
                errors["enrollment"] = "L'inscription doit appartenir à cette école."
        if self.period_id and self.enrollment_id:
            if self.period.academic_year_id != self.enrollment.academic_year_id:
                errors["period"] = (
                    "La période et l'inscription doivent appartenir à la même année."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk and type(self).all_objects.filter(pk=self.pk).exists():
            raise ValidationError("Une version de bulletin est immuable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Une version de bulletin ne peut pas être supprimée.")

    def __str__(self):
        return (
            f"{self.enrollment.student.full_name} — {self.period.name} "
            f"(v{self.version})"
        )
