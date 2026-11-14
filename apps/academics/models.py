from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.tenancy import TenantModel
from apps.tenancy.models import School, Site


class AcademicYear(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="academic_years"
    )
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"], name="uniq_academic_year_per_school"
            )
        ]

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError(
                {"end_date": "La date de fin doit être postérieure à la date de début."}
            )

    def __str__(self):
        return f"{self.school.code} — {self.name}"


class Level(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="levels")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uniq_level_code_per_school"
            )
        ]

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Series(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("level__school__organization_id", "organization_id"),
        "school": ("level__school_id", "school_id"),
    }

    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="series")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["level__order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["level", "code"], name="uniq_series_code_per_level"
            )
        ]

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Subject(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="subjects"
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "code"], name="uniq_subject_code_per_school"
            )
        ]

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Curriculum(TenantModel):
    """Programme d'un niveau/série pour une année scolaire."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="curricula"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="curricula"
    )
    level = models.ForeignKey(
        Level, on_delete=models.CASCADE, related_name="curricula"
    )
    series = models.ForeignKey(
        Series, on_delete=models.CASCADE, related_name="curricula"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["academic_year__name", "level__order", "series__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "level", "series"],
                name="uniq_curriculum_per_year_level_series",
            )
        ]

    def clean(self):
        if self.school_id and self.academic_year_id:
            if self.academic_year.school_id != self.school_id:
                raise ValidationError(
                    {"academic_year": "L'année doit appartenir à la même école."}
                )
        if self.school_id and self.level_id:
            if self.level.school_id != self.school_id:
                raise ValidationError(
                    {"level": "Le niveau doit appartenir à la même école."}
                )
        if self.level_id and self.series_id:
            if self.series.level_id != self.level_id:
                raise ValidationError(
                    {"series": "La série doit appartenir au niveau indiqué."}
                )

    def __str__(self):
        return f"{self.academic_year.name} — {self.level.name} {self.series.name}"


class CurriculumSubject(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("curriculum__school__organization_id", "organization_id"),
        "school": ("curriculum__school_id", "school_id"),
    }

    curriculum = models.ForeignKey(
        Curriculum, on_delete=models.CASCADE, related_name="curriculum_subjects"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="curriculum_subjects"
    )
    coefficient = models.DecimalField(max_digits=5, decimal_places=2)
    weekly_hours = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )

    class Meta:
        ordering = ["subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["curriculum", "subject"],
                name="uniq_subject_per_curriculum",
            ),
            models.CheckConstraint(
                condition=models.Q(coefficient__gt=0),
                name="curriculum_subject_coefficient_positive",
            ),
        ]

    def clean(self):
        if self.curriculum_id and self.subject_id:
            if self.subject.school_id != self.curriculum.school_id:
                raise ValidationError(
                    {"subject": "La matière doit appartenir à la même école."}
                )

    def __str__(self):
        return f"{self.subject.name} (coef. {self.coefficient})"


class SchoolClass(TenantModel):
    """Classe : niveau + série + section, pour une année et une école."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="classes")
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="classes"
    )
    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="classes")
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="classes")
    section = models.CharField(max_length=5)
    name = models.CharField(max_length=50, blank=True)
    site = models.ForeignKey(
        Site,
        on_delete=models.SET_NULL,
        related_name="classes",
        null=True,
        blank=True,
    )
    capacity = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["academic_year__name", "level__order", "series__code", "section"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "level", "series", "section"],
                name="uniq_class_per_school_year_level_series_section",
            )
        ]

    def clean(self):
        if self.school_id and self.academic_year_id:
            if self.academic_year.school_id != self.school_id:
                raise ValidationError(
                    {"academic_year": "L'année doit appartenir à la même école."}
                )
        if self.school_id and self.level_id:
            if self.level.school_id != self.school_id:
                raise ValidationError(
                    {"level": "Le niveau doit appartenir à la même école."}
                )
        if self.level_id and self.series_id:
            if self.series.level_id != self.level_id:
                raise ValidationError(
                    {"series": "La série doit appartenir au niveau indiqué."}
                )
        if self.site_id and self.school_id:
            if self.site.school_id != self.school_id:
                raise ValidationError(
                    {"site": "Le site doit appartenir à la même école."}
                )
        if self.capacity <= 0:
            raise ValidationError({"capacity": "La capacité doit être positive."})

    def save(self, *args, **kwargs):
        self.section = (self.section or "").strip().upper()
        if not self.name:
            self.name = f"{self.level.name} {self.section}"
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.name or f"{self.level.name} {self.section}"

    @property
    def enrolled_count(self):
        return self.enrollments.model.all_objects.filter(
            school_class=self, status="active"
        ).count()

    @property
    def is_full(self):
        return self.enrolled_count >= self.capacity

    def __str__(self):
        return f"{self.school.code} — {self.display_name} ({self.academic_year.name})"


class ClassSubject(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school_class__school__organization_id", "organization_id"),
        "school": ("school_class__school_id", "school_id"),
    }

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="class_subjects"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="class_subjects"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="class_subjects",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["school_class__name", "subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "subject"],
                name="uniq_subject_per_class",
            )
        ]

    def clean(self):
        if self.school_class_id and self.subject_id:
            if self.subject.school_id != self.school_class.school_id:
                raise ValidationError(
                    {"subject": "La matière doit appartenir à la même école."}
                )

    def __str__(self):
        return f"{self.school_class.display_name} — {self.subject.name}"
