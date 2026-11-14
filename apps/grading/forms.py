from django import forms

from apps.academics.models import AcademicYear, ClassSubject
from apps.tenancy.access import user_can_manage_grading_settings

from .models import Assessment, Deliberation, GradingPeriod, GradeStatus


class GradingPeriodForm(forms.ModelForm):
    class Meta:
        model = GradingPeriod
        fields = [
            "academic_year",
            "code",
            "name",
            "sequence",
            "start_date",
            "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.fields["academic_year"].queryset = AcademicYear.objects.filter(
            school=school
        )

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get("academic_year")
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if year and year.school_id != self.school.pk:
            self.add_error("academic_year", "Choisir une année de cette école.")
        if start and end and start > end:
            self.add_error("end_date", "La fin précède le début de la période.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.school = self.school
        if commit:
            instance.save()
        return instance


class AssessmentForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = [
            "class_subject",
            "period",
            "title",
            "assessment_type",
            "held_on",
            "max_score",
            "weight",
        ]
        widgets = {"held_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, school, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.user = user
        class_subjects = ClassSubject.objects.filter(
            school_class__school=school
        ).select_related("school_class", "subject")
        if not user_can_manage_grading_settings(user, school):
            class_subjects = class_subjects.filter(teacher=user)
        self.fields["class_subject"].queryset = class_subjects
        self.fields["period"].queryset = GradingPeriod.objects.filter(
            school=school, is_closed=False
        )

    def clean(self):
        cleaned = super().clean()
        class_subject = cleaned.get("class_subject")
        period = cleaned.get("period")
        if class_subject and period:
            if class_subject.school_class.academic_year_id != period.academic_year_id:
                self.add_error(
                    "period", "La période doit être celle de l'année de la classe."
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.school = self.school
        instance.created_by = self.user
        if commit:
            instance.save()
        return instance


class GradeEntryForm(forms.Form):
    enrollment_id = forms.UUIDField(widget=forms.HiddenInput)
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Non saisie"), *GradeStatus.choices],
        label="Statut",
    )
    score = forms.DecimalField(
        required=False,
        max_digits=7,
        decimal_places=2,
        min_value=0,
        localize=False,
        label="Note",
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )
    comment = forms.CharField(
        required=False,
        max_length=240,
        label="Observation",
        widget=forms.TextInput(attrs={"placeholder": "Facultatif"}),
    )

    def __init__(self, *args, max_score, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_score = max_score
        self.fields["score"].widget.attrs["max"] = str(max_score)
        self.fields["score"].help_text = f"Barème : {max_score}"

    def clean(self):
        cleaned = super().clean()
        score = cleaned.get("score")
        status = cleaned.get("status")
        if not status and score is not None:
            self.add_error("status", "Choisir le statut « Note saisie ».")
        elif status == GradeStatus.GRADED:
            if score is None:
                self.add_error("score", "Saisir une note.")
            elif score > self.max_score:
                self.add_error(
                    "score", f"La note ne peut pas dépasser {self.max_score}."
                )
        elif status in {GradeStatus.ABSENT, GradeStatus.EXCUSED} and score is not None:
            self.add_error("score", "Laisser la note vide pour ce statut.")
        return cleaned


class DeliberationForm(forms.ModelForm):
    class Meta:
        model = Deliberation
        fields = ["outcome", "comment"]
        labels = {"comment": "Motivation / commentaire du conseil"}
        widgets = {"comment": forms.Textarea(attrs={"rows": 4})}


class CorrectionReasonForm(forms.Form):
    reason = forms.CharField(
        label="Motif de correction",
        min_length=10,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Expliquez la pièce ou la décision qui justifie la correction.",
            }
        ),
        help_text="Obligatoire pour conserver une trace de la correction.",
    )


class PeriodReopenForm(forms.Form):
    reason = forms.CharField(
        label="Motif de réouverture",
        min_length=10,
        max_length=500,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Indiquez pourquoi la période est rouverte."}
        ),
        help_text="La réouverture sera consignée dans l'historique de la période.",
    )
