from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from apps.academics.models import AcademicYear, SchoolClass
from apps.academics.utils import current_academic_year

from .models import (
    Enrollment,
    Guardian,
    GuardianRelationship,
    Student,
    StudentGuardian,
)


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "matricule",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "place_of_birth",
            "address",
            "phone",
            "email",
            "status",
            "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "matricule": (
                "Laisser vide pour générer un matricule automatiquement. "
                "Le matricule est unique dans l'école."
            ),
            "status": "Un élève inactif reste visible mais n'est plus inscrit.",
        }

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.instance.school = school
        self.fields["matricule"].required = False
        if not self.instance._state.adding:
            self.fields["matricule"].help_text = (
                "Identifiant stable de l'élève dans l'école."
            )

    def clean_matricule(self):
        matricule = (self.cleaned_data.get("matricule") or "").strip().upper()
        if not matricule:
            if not self.instance._state.adding:
                raise ValidationError(
                    "Le matricule d'un élève existant est obligatoire."
                )
            return self.instance._generate_matricule()
        duplicates = Student.all_objects.filter(
            school=self.school, matricule=matricule
        )
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "Un élève porte déjà ce matricule dans l'école."
            )
        return matricule


class GuardianForm(forms.ModelForm):
    class Meta:
        model = Guardian
        fields = [
            "first_name",
            "last_name",
            "phone",
            "secondary_phone",
            "email",
            "address",
            "occupation",
            "notes",
        ]
        widgets = {
            "address": forms.TextInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "phone": "Numéro principal, par exemple +223 70 00 00 00.",
            "secondary_phone": "Deuxième numéro joignable, facultatif.",
        }

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        self.instance.organization = organization

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            raise ValidationError("Le téléphone du tuteur est obligatoire.")
        return phone


class GuardianCreateLinkForm(GuardianForm):
    relationship = forms.ChoiceField(
        label="Lien avec l'élève",
        choices=GuardianRelationship.choices,
    )
    is_primary = forms.BooleanField(
        label="Tuteur principal",
        required=False,
        help_text="Le tuteur principal est contacté en premier.",
    )
    is_financial_responsible = forms.BooleanField(
        label="Responsable financier",
        required=False,
        help_text="Reçoit les avis de paiement.",
    )


class GuardianLinkForm(forms.Form):
    guardian = forms.ModelChoiceField(
        label="Tuteur existant",
        queryset=Guardian.objects.none(),
    )
    relationship = forms.ChoiceField(
        label="Lien avec l'élève",
        choices=GuardianRelationship.choices,
    )
    is_primary = forms.BooleanField(label="Tuteur principal", required=False)
    is_financial_responsible = forms.BooleanField(
        label="Responsable financier", required=False
    )

    def __init__(self, *args, student=None, **kwargs):
        self.student = student
        super().__init__(*args, **kwargs)
        self.fields["guardian"].queryset = Guardian.all_objects.filter(
            organization=student.school.organization
        ).order_by("last_name", "first_name")
        self.fields["guardian"].label_from_instance = lambda guardian: (
            f"{guardian.full_name} — {guardian.phone}"
        )

    def clean_guardian(self):
        guardian = self.cleaned_data.get("guardian")
        if guardian and StudentGuardian.all_objects.filter(
            student=self.student, guardian=guardian
        ).exists():
            raise ValidationError("Ce tuteur est déjà lié à cet élève.")
        return guardian


class GuardianLinkEditForm(forms.ModelForm):
    class Meta:
        model = StudentGuardian
        fields = ["relationship", "is_primary", "is_financial_responsible"]


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = [
            "student",
            "academic_year",
            "school_class",
            "status",
            "enrolled_on",
            "exited_on",
            "notes",
        ]
        widgets = {
            "enrolled_on": forms.DateInput(attrs={"type": "date"}),
            "exited_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "status": (
                "Une inscription active ne peut pas avoir de date de sortie."
            ),
            "exited_on": "Obligatoire pour un élève retiré ou transféré.",
        }

    def __init__(
        self,
        *args,
        school=None,
        lock_identity=False,
        **kwargs,
    ):
        self.school = school
        self.lock_identity = lock_identity
        super().__init__(*args, **kwargs)
        self.instance.school = school

        self.fields["student"].queryset = Student.all_objects.filter(
            school=school
        ).order_by("last_name", "first_name")
        self.fields["student"].label_from_instance = lambda student: (
            f"{student.full_name} — {student.matricule}"
        )

        years = AcademicYear.all_objects.filter(school=school).order_by(
            "-start_date"
        )
        self.fields["academic_year"].queryset = years

        classes = (
            SchoolClass.all_objects.filter(school=school)
            .select_related("academic_year", "level", "series")
            .order_by(
                "-academic_year__start_date",
                "level__order",
                "series__code",
                "section",
            )
        )
        if lock_identity and self.instance.academic_year_id:
            classes = classes.filter(
                academic_year_id=self.instance.academic_year_id
            )
            self.fields["student"].disabled = True
            self.fields["academic_year"].disabled = True
            self.fields["school_class"].help_text = (
                "La classe doit appartenir à l'année scolaire de l'inscription."
            )
        elif not self.is_bound and self.instance._state.adding:
            current = current_academic_year(school)
            if current is not None and not self.initial.get("academic_year"):
                self.initial["academic_year"] = current.pk
            if not self.initial.get("enrolled_on"):
                self.initial["enrolled_on"] = date.today()

        self.fields["school_class"].queryset = classes
        self.fields["school_class"].label_from_instance = lambda school_class: (
            f"{school_class.academic_year.name} · "
            f"{school_class.display_name}"
        )

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        year = cleaned_data.get("academic_year")
        if student and year:
            duplicates = Enrollment.all_objects.filter(
                student=student, academic_year=year
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "academic_year",
                    "Cet élève est déjà inscrit pour cette année scolaire.",
                )
        return cleaned_data
