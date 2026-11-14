import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicYear, SchoolClass
from apps.common.tenancy import TenantModel
from apps.tenancy.models import Organization, School


class Gender(models.TextChoices):
    MALE = "M", "Masculin"
    FEMALE = "F", "Féminin"


class StudentStatus(models.TextChoices):
    ACTIVE = "active", "Actif"
    INACTIVE = "inactive", "Inactif"
    GRADUATED = "graduated", "Diplômé"
    TRANSFERRED = "transferred", "Transféré"
    ARCHIVED = "archived", "Archivé"


class Student(TenantModel):
    """Élève rattaché à une école. Le matricule est unique par école."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="students"
    )
    matricule = models.CharField(
        max_length=40,
        blank=True,
        help_text="Laisser vide pour générer automatiquement un matricule.",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=StudentStatus.choices,
        default=StudentStatus.ACTIVE,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name", "matricule"]
        verbose_name = "élève"
        verbose_name_plural = "élèves"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "matricule"],
                name="uniq_student_matricule_per_school",
            ),
            models.CheckConstraint(
                condition=~models.Q(matricule=""),
                name="student_matricule_not_empty",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "last_name", "first_name"],
                name="student_school_name_idx",
            ),
            models.Index(
                fields=["school", "status"],
                name="student_school_status_idx",
            ),
        ]

    def _generate_matricule(self):
        prefix = f"{self.school.code}-{timezone.localdate().year}"
        for _ in range(10):
            candidate = f"{prefix}-{uuid.uuid4().hex[:5].upper()}"
            if not Student.all_objects.filter(
                school=self.school, matricule=candidate
            ).exists():
                return candidate
        return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"

    def clean(self):
        super().clean()
        errors = {}
        if self.date_of_birth and self.date_of_birth > date.today():
            errors["date_of_birth"] = (
                "La date de naissance ne peut pas être dans le futur."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.matricule = (self.matricule or "").strip().upper()
        if not self.matricule:
            self.matricule = self._generate_matricule()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.matricule} — {self.full_name}"


class Guardian(TenantModel):
    """Parent ou tuteur. Rattaché à l'organisation, pas à une seule école."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("organization_id", "organization_id"),
        "school": ("organization_id", "organization_id"),
    }

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="guardians"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30)
    secondary_phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "tuteur"
        verbose_name_plural = "tuteurs"
        indexes = [
            models.Index(
                fields=["organization", "phone"],
                name="guardian_org_phone_idx",
            ),
            models.Index(
                fields=["organization", "last_name", "first_name"],
                name="guardian_org_name_idx",
            ),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.full_name} ({self.phone})"


class GuardianRelationship(models.TextChoices):
    FATHER = "father", "Père"
    MOTHER = "mother", "Mère"
    TUTOR = "tutor", "Tuteur"
    OTHER = "other", "Autre"


class StudentGuardian(TenantModel):
    """Lien entre un élève et un parent/tuteur."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("student__school__organization_id", "organization_id"),
        "school": ("student__school_id", "school_id"),
    }

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="guardianships"
    )
    guardian = models.ForeignKey(
        Guardian, on_delete=models.CASCADE, related_name="studentships"
    )
    relationship = models.CharField(
        max_length=20, choices=GuardianRelationship.choices
    )
    is_primary = models.BooleanField(default=False)
    is_financial_responsible = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "guardian__last_name", "guardian__first_name"]
        verbose_name = "lien élève-tuteur"
        verbose_name_plural = "liens élèves-tuteurs"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "guardian"],
                name="uniq_guardian_per_student",
            ),
            models.UniqueConstraint(
                fields=["student"],
                condition=models.Q(is_primary=True),
                name="uniq_primary_guardian_per_student",
            ),
        ]

    def clean(self):
        super().clean()
        if self.student_id and self.guardian_id:
            if (
                self.student.school.organization_id
                != self.guardian.organization_id
            ):
                raise ValidationError(
                    {
                        "guardian": (
                            "Le tuteur doit appartenir à la même organisation "
                            "que l'élève."
                        )
                    }
                )

    def __str__(self):
        return (
            f"{self.student.full_name} — {self.guardian.full_name} "
            f"({self.get_relationship_display()})"
        )


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "Actif"
    WITHDRAWN = "withdrawn", "Retiré"
    TRANSFERRED = "transferred", "Transféré"
    COMPLETED = "completed", "Terminé"


class Enrollment(TenantModel):
    """Inscription d'un élève dans une classe pour une année scolaire."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="enrollments"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="enrollments"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="enrollments"
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="enrollments"
    )
    status = models.CharField(
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE,
    )
    enrolled_on = models.DateField(default=date.today)
    exited_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-academic_year__start_date", "student__last_name"]
        verbose_name = "inscription"
        verbose_name_plural = "inscriptions"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                name="uniq_enrollment_per_student_year",
            )
        ]
        indexes = [
            models.Index(
                fields=["school", "academic_year", "school_class"],
                name="enrollment_class_idx",
            ),
            models.Index(
                fields=["school", "status"],
                name="enrollment_status_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.student_id
            and self.school_id
            and self.student.school_id != self.school_id
        ):
            errors["student"] = (
                "L'élève n'appartient pas à l'école de l'inscription."
            )
        if (
            self.academic_year_id
            and self.school_id
            and self.academic_year.school_id != self.school_id
        ):
            errors["academic_year"] = (
                "L'année scolaire doit appartenir à la même école."
            )
        if (
            self.school_class_id
            and self.school_id
            and self.school_class.school_id != self.school_id
        ):
            errors["school_class"] = "La classe doit appartenir à la même école."
        if (
            self.school_class_id
            and self.academic_year_id
            and self.school_class.academic_year_id != self.academic_year_id
        ):
            errors["school_class"] = (
                "La classe doit appartenir à l'année scolaire indiquée."
            )
        if self.exited_on:
            if self.enrolled_on and self.exited_on < self.enrolled_on:
                errors["exited_on"] = (
                    "La date de sortie ne peut pas précéder la date d'inscription."
                )
            elif self.status == EnrollmentStatus.ACTIVE:
                errors["exited_on"] = (
                    "Un élève actif ne peut pas avoir de date de sortie."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Le champ school est dénormalisé : il est toujours dérivé de l'élève.
        if self.student_id:
            self.school_id = self.student.school_id
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status == EnrollmentStatus.ACTIVE

    def __str__(self):
        return (
            f"{self.student.full_name} — {self.school_class.display_name} "
            f"({self.academic_year.name})"
        )
