from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import modelformset_factory
from django.utils import timezone

from apps.tenancy.models import Membership, Role

from .models import (
    AcademicYear,
    ClassSubject,
    CurriculumSubject,
    Level,
    SchoolClass,
    Series,
    Site,
    Subject,
)

User = get_user_model()


def teacher_queryset(school):
    """Enseignants actifs de l'école, y compris les membres de l'organisation."""
    user_ids = (
        Membership.all_objects.filter(
            organization=school.organization,
            role=Role.TEACHER,
            is_active=True,
        )
        .filter(Q(school__isnull=True) | Q(school=school))
        .values_list("user_id", flat=True)
    )
    return User.objects.filter(id__in=user_ids).order_by(
        "last_name", "first_name", "username"
    )


def default_academic_year():
    """Propose l'année scolaire en cours au format malien 2026-2027."""
    today = timezone.localdate()
    start_year = today.year if today.month >= 10 else today.year - 1
    return {
        "name": f"{start_year}-{start_year + 1}",
        "start_date": date(start_year, 10, 1),
        "end_date": date(start_year + 1, 6, 30),
    }


class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ["name", "start_date", "end_date", "is_current"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["name"].help_text = "Format attendu : 2026-2027."
        if (
            school is not None
            and not self.is_bound
            and self.instance._state.adding
        ):
            self.fields["is_current"].initial = not AcademicYear.objects.filter(
                school=school, is_current=True
            ).exists()

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if not name:
            raise ValidationError("Le nom de l'année est obligatoire.")
        if self.school is not None:
            duplicates = AcademicYear.objects.filter(
                school=self.school, name__iexact=name
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError(
                    "Une année scolaire portant ce nom existe déjà."
                )
        return name


class LevelForm(forms.ModelForm):
    class Meta:
        model = Level
        fields = ["code", "name", "order"]
        help_texts = {
            "code": "Code court et stable, par exemple 10, 11 ou TLE.",
            "order": "Ordre d'affichage, 1 pour le premier niveau.",
        }

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise ValidationError("Le code du niveau est obligatoire.")
        if self.school is not None:
            duplicates = Level.objects.filter(school=self.school, code=code)
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError(
                    "Un niveau avec ce code existe déjà dans l'école."
                )
        return code


class SeriesForm(forms.ModelForm):
    class Meta:
        model = Series
        fields = ["level", "code", "name"]
        help_texts = {
            "code": "Code court et stable, par exemple LET, SCI ou TSE.",
        }

    def __init__(self, *args, school=None, level=None, **kwargs):
        self.school = school
        self.fixed_level = level
        super().__init__(*args, **kwargs)
        self.fields["level"].queryset = Level.objects.filter(
            school=school
        ).order_by("order", "code")
        if level is not None:
            self.fields["level"].initial = level
            self.fields["level"].disabled = True
            self.fields["level"].help_text = (
                "Le niveau d'une série ne peut pas être modifié."
            )

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise ValidationError("Le code de la série est obligatoire.")

        level = (
            self.fixed_level
            or self.cleaned_data.get("level")
            or (
                self.instance.level
                if not self.instance._state.adding
                else None
            )
        )
        if level is None:
            raise ValidationError("Le niveau de la série est obligatoire.")

        duplicates = Series.objects.filter(level=level, code=code)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "Une série avec ce code existe déjà pour ce niveau."
            )
        return code


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["code", "name"]
        help_texts = {
            "code": "Code court et stable, par exemple FR, MATH ou HG.",
        }

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.instance.school = school

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise ValidationError("Le code de la matière est obligatoire.")
        duplicates = Subject.all_objects.filter(school=self.school, code=code)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError(
                "Une matière avec ce code existe déjà dans l'école."
            )
        return code


class ClassForm(forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = [
            "academic_year",
            "level",
            "series",
            "section",
            "name",
            "site",
            "capacity",
        ]
        help_texts = {
            "section": "Section ou parallèle, par exemple A, B ou C.",
            "name": "Laisser vide pour générer « Niveau Section ».",
            "capacity": "Capacité d'accueil, 100 par défaut.",
        }

    def __init__(self, *args, school=None, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.instance.school = school

        self.fields["academic_year"].queryset = AcademicYear.all_objects.filter(
            school=school
        ).order_by("-start_date")
        self.fields["level"].queryset = Level.all_objects.filter(
            school=school
        ).order_by("order", "code")
        self.fields["series"].queryset = (
            Series.all_objects.filter(level__school=school)
            .select_related("level")
            .order_by("level__order", "code")
        )
        self.fields["series"].label_from_instance = lambda series: (
            f"{series.level.name} — {series.name} ({series.code})"
        )
        self.fields["site"].queryset = Site.all_objects.filter(
            school=school
        ).order_by("name")
        self.fields["site"].required = False
        self.fields["site"].empty_label = "Aucun site"

        if self.instance._state.adding and not self.initial.get(
            "academic_year"
        ):
            current = AcademicYear.all_objects.filter(
                school=school, is_current=True
            ).first()
            if current is None:
                current = (
                    AcademicYear.all_objects.filter(school=school)
                    .order_by("-start_date")
                    .first()
                )
            if current is not None:
                self.fields["academic_year"].initial = current.pk

        if (
            not self.instance._state.adding
            and self.instance.enrollments.exists()
        ):
            for field_name in (
                "academic_year",
                "level",
                "series",
                "section",
            ):
                self.fields[field_name].disabled = True
                self.fields[field_name].help_text = (
                    "Des élèves sont inscrits : ce champ est verrouillé."
                )

    def clean(self):
        cleaned_data = super().clean()
        section = (cleaned_data.get("section") or "").strip().upper()
        if section:
            cleaned_data["section"] = section

        year = cleaned_data.get("academic_year")
        level = cleaned_data.get("level")
        series = cleaned_data.get("series")
        if self.school and year and level and series and section:
            duplicates = SchoolClass.all_objects.filter(
                school=self.school,
                academic_year=year,
                level=level,
                series=series,
                section=section,
            )
            if not self.instance._state.adding:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "section",
                    "Une classe identique existe déjà pour cette année, "
                    "ce niveau et cette série.",
                )
        return cleaned_data


class CurriculumSubjectForm(forms.ModelForm):
    class Meta:
        model = CurriculumSubject
        fields = ["subject", "coefficient", "weekly_hours"]
        widgets = {
            "coefficient": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01"}
            ),
            "weekly_hours": forms.NumberInput(
                attrs={"step": "0.1", "min": "0"}
            ),
        }
        help_texts = {
            "coefficient": "Coefficient utilisé pour la moyenne de la série.",
            "weekly_hours": "Volume horaire hebdomadaire, facultatif.",
        }

    def __init__(self, *args, curriculum=None, editing=False, **kwargs):
        self.curriculum = curriculum
        super().__init__(*args, **kwargs)
        self.instance.curriculum = curriculum

        subjects = Subject.all_objects.filter(
            school=curriculum.school
        ).order_by("name")
        if not editing:
            subjects = subjects.exclude(
                id__in=CurriculumSubject.all_objects.filter(
                    curriculum=curriculum
                ).values_list("subject_id", flat=True)
            )
        else:
            self.fields["subject"].disabled = True
            self.fields["subject"].help_text = (
                "La matière d'un coefficient ne peut pas être modifiée."
            )
        self.fields["subject"].queryset = subjects
        self.fields["coefficient"].min_value = 0.01


class ClassSubjectAddForm(forms.Form):
    subject = forms.ModelChoiceField(
        label="Matière",
        queryset=Subject.objects.none(),
    )
    teacher = forms.ModelChoiceField(
        label="Enseignant",
        queryset=None,
        required=False,
        empty_label="Non affecté",
    )

    def __init__(self, *args, school_class=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school_class = school_class
        assigned = ClassSubject.all_objects.filter(
            school_class=school_class
        ).values_list("subject_id", flat=True)
        self.fields["subject"].queryset = Subject.all_objects.filter(
            school=school_class.school
        ).exclude(id__in=assigned).order_by("name")
        self.fields["teacher"].queryset = teacher_queryset(
            school_class.school
        )


class ClassSubjectTeacherForm(forms.ModelForm):
    class Meta:
        model = ClassSubject
        fields = ["teacher"]
        help_texts = {
            "teacher": "Laisser vide pour retirer l'affectation.",
        }

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = teacher_queryset(school)
        self.fields["teacher"].required = False
        self.fields["teacher"].empty_label = "Non affecté"


ClassSubjectTeacherFormSet = modelformset_factory(
    ClassSubject,
    form=ClassSubjectTeacherForm,
    extra=0,
    can_delete=False,
)
