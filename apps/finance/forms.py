from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.academics.forms import SeriesSelect
from apps.academics.models import AcademicYear, Level, SchoolClass, Series
from apps.students.models import Enrollment, EnrollmentStatus, Student
from apps.tenancy.models import Site

from .models import (
    Discount,
    Fee,
    Invoice,
    PaymentMethod,
    PaymentPlan,
    PaymentPlanLine,
)


class FeeForm(forms.ModelForm):
    class Meta:
        model = Fee
        fields = [
            "academic_year",
            "level",
            "series",
            "name",
            "amount",
            "description",
            "is_active",
        ]
        labels = {
            "academic_year": "Année scolaire",
            "level": "Niveau",
            "series": "Série",
            "name": "Libellé du frais",
            "amount": "Montant (FCFA)",
            "description": "Description",
            "is_active": "Frais actif",
        }
        help_texts = {
            "level": "Laisser vide pour appliquer à tous les niveaux.",
            "series": "Laisser vide pour appliquer à toutes les séries du niveau.",
            "amount": "Montant strictement positif, en francs CFA.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "amount": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}
            ),
            "series": SeriesSelect,
        }

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.instance.school = school
        years = AcademicYear.all_objects.filter(school=school).order_by(
            "-start_date"
        )
        self.fields["academic_year"].queryset = years
        if not self.instance.pk and not self.initial.get("academic_year"):
            self.fields["academic_year"].initial = years.first()
        self.fields["level"].queryset = Level.all_objects.filter(
            school=school
        ).order_by("order", "code")
        self.fields["level"].required = False
        self.fields["level"].empty_label = "Tous les niveaux"
        self.fields["series"].queryset = (
            Series.all_objects.filter(level__school=school)
            .select_related("level")
            .order_by("level__order", "code")
        )
        self.fields["series"].required = False
        self.fields["series"].empty_label = "Toutes les séries"
        self.fields["series"].label_from_instance = lambda series: (
            f"{series.level.name} — {series.name} ({series.code})"
        )

    def clean(self):
        cleaned = super().clean()
        level = cleaned.get("level")
        series = cleaned.get("series")
        if series and not level:
            self.add_error(
                "series", "Choisissez d'abord un niveau pour cette série."
            )
        elif series and level and series.level_id != level.pk:
            self.add_error(
                "series", "La série sélectionnée n'appartient pas à ce niveau."
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.school = self.school
        if commit:
            instance.save()
        return instance


class PaymentPlanForm(forms.ModelForm):
    class Meta:
        model = PaymentPlan
        fields = ["academic_year", "level", "series", "name", "is_active"]
        labels = {
            "academic_year": "Année scolaire",
            "level": "Niveau",
            "series": "Série",
            "name": "Nom de l'échéancier",
            "is_active": "Échéancier actif",
        }
        help_texts = {
            "level": "Laisser vide pour proposer l'échéancier à toute l'école.",
            "series": "Laisser vide pour toutes les séries du niveau.",
        }
        widgets = {"series": SeriesSelect}

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.instance.school = school
        years = AcademicYear.all_objects.filter(school=school).order_by(
            "-start_date"
        )
        self.fields["academic_year"].queryset = years
        if not self.instance.pk and not self.initial.get("academic_year"):
            self.fields["academic_year"].initial = years.first()
        self.fields["level"].queryset = Level.all_objects.filter(
            school=school
        ).order_by("order", "code")
        self.fields["level"].required = False
        self.fields["level"].empty_label = "Toute l'école"
        self.fields["series"].queryset = (
            Series.all_objects.filter(level__school=school)
            .select_related("level")
            .order_by("level__order", "code")
        )
        self.fields["series"].required = False
        self.fields["series"].empty_label = "Toutes les séries"
        self.fields["series"].label_from_instance = lambda series: (
            f"{series.level.name} — {series.name} ({series.code})"
        )

    def clean(self):
        cleaned = super().clean()
        level = cleaned.get("level")
        series = cleaned.get("series")
        if series and not level:
            self.add_error(
                "series", "Choisissez d'abord un niveau pour cette série."
            )
        elif series and level and series.level_id != level.pk:
            self.add_error(
                "series", "La série sélectionnée n'appartient pas à ce niveau."
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.school = self.school
        if commit:
            instance.save()
        return instance


class PaymentPlanLineForm(forms.ModelForm):
    class Meta:
        model = PaymentPlanLine
        fields = ["sequence", "label", "due_date", "percentage"]
        labels = {
            "sequence": "Ordre",
            "label": "Libellé",
            "due_date": "Date d'échéance",
            "percentage": "Pourcentage (%)",
        }
        widgets = {
            "sequence": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "percentage": forms.NumberInput(
                attrs={"min": "0.01", "max": "100", "step": "0.01"}
            ),
        }


class BasePaymentPlanLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        total = sum(
            (
                line.get("percentage") or Decimal("0.00")
                for line in self.cleaned_data
                if line and not line.get("DELETE")
            ),
            Decimal("0.00"),
        )
        if total != Decimal("100.00"):
            raise ValidationError(
                "Le total des pourcentages de l'échéancier doit être "
                f"égal à 100 % (actuellement {total} %)."
            )


PaymentPlanLineFormSet = forms.inlineformset_factory(
    PaymentPlan,
    PaymentPlanLine,
    form=PaymentPlanLineForm,
    formset=BasePaymentPlanLineFormSet,
    extra=3,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class DiscountForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = [
            "academic_year",
            "student",
            "label",
            "kind",
            "value",
            "reason",
            "is_active",
        ]
        labels = {
            "academic_year": "Année scolaire",
            "student": "Élève",
            "label": "Libellé de la remise",
            "kind": "Type de remise",
            "value": "Valeur",
            "reason": "Motif",
            "is_active": "Remise active",
        }
        help_texts = {
            "value": (
                "Pourcentage entre 0 et 100, ou montant fixe en FCFA. "
                "La remise sera appliquée à la prochaine facture."
            ),
            "reason": "Bourse, fratrie, personnel, geste commercial…",
        }
        widgets = {
            "reason": forms.Textarea(attrs={"rows": 3}),
            "value": forms.NumberInput(
                attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}
            ),
        }

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.instance.school = school
        years = AcademicYear.all_objects.filter(school=school).order_by(
            "-start_date"
        )
        self.fields["academic_year"].queryset = years
        if not self.instance.pk and not self.initial.get("academic_year"):
            self.fields["academic_year"].initial = years.first()
        self.fields["student"].queryset = Student.all_objects.filter(
            school=school
        ).order_by("last_name", "first_name")
        self.fields["student"].label_from_instance = lambda student: (
            f"{student.last_name} {student.first_name} ({student.matricule})"
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.school = self.school
        if commit:
            instance.save()
        return instance


class InvoiceGenerateForm(forms.Form):
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.all_objects.none(),
        label="Année scolaire",
    )
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.all_objects.none(),
        required=False,
        label="Classe (facturation en lot)",
        empty_label="— Choisir une classe —",
    )
    student = forms.ModelChoiceField(
        queryset=Student.all_objects.none(),
        required=False,
        label="Élève (facturation individuelle)",
        empty_label="— Choisir un élève —",
    )
    payment_plan = forms.ModelChoiceField(
        queryset=PaymentPlan.all_objects.none(),
        required=False,
        label="Échéancier imposé",
        empty_label="— Échéancier automatique —",
        help_text=(
            "Laisser vide pour utiliser l'échéancier le plus spécifique "
            "correspondant à la classe."
        ),
    )
    issue_date = forms.DateField(
        label="Date d'émission",
        initial=date.today,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        years = AcademicYear.all_objects.filter(school=school).order_by(
            "-start_date"
        )
        self.fields["academic_year"].queryset = years
        if not self.initial.get("academic_year"):
            self.fields["academic_year"].initial = years.first()
        self.fields["school_class"].queryset = (
            SchoolClass.all_objects.filter(school=school)
            .select_related("academic_year", "level", "series")
            .order_by("-academic_year__start_date", "level__order", "name")
        )
        self.fields["school_class"].label_from_instance = lambda school_class: (
            f"{school_class.display_name} — "
            f"{school_class.level.name} "
            f"{school_class.series.name} ({school_class.academic_year.name})"
        )
        self.fields["student"].queryset = (
            Student.all_objects.filter(
                school=school,
                enrollments__status=EnrollmentStatus.ACTIVE,
            )
            .distinct()
            .order_by("last_name", "first_name")
        )
        self.fields["student"].label_from_instance = lambda student: (
            f"{student.last_name} {student.first_name} "
            f"({student.matricule})"
        )
        self.fields["payment_plan"].queryset = (
            PaymentPlan.all_objects.filter(school=school, is_active=True)
            .select_related("academic_year", "level", "series")
            .order_by("-academic_year__start_date", "name")
        )
        self.fields["payment_plan"].label_from_instance = lambda plan: (
            f"{plan.name} — {plan.scope_label} ({plan.academic_year.name})"
        )

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get("academic_year")
        school_class = cleaned.get("school_class")
        student = cleaned.get("student")
        plan = cleaned.get("payment_plan")

        if bool(school_class) == bool(student):
            raise ValidationError(
                "Choisissez soit une classe pour facturer en lot, soit un "
                "élève pour facturer individuellement."
            )
        if school_class and year:
            if school_class.academic_year_id != year.pk:
                self.add_error(
                    "school_class",
                    "La classe sélectionnée n'appartient pas à cette année.",
                )
        if plan:
            if plan.school_id != self.school.pk:
                self.add_error("payment_plan", "Échéancier d'une autre école.")
            elif year and plan.academic_year_id != year.pk:
                self.add_error(
                    "payment_plan",
                    "L'échéancier sélectionné n'appartient pas à cette année.",
                )
        if student and year:
            enrollment = (
                Enrollment.all_objects.filter(
                    school=self.school,
                    academic_year=year,
                    student=student,
                    status=EnrollmentStatus.ACTIVE,
                )
                .select_related("student", "school_class__level", "school_class__series")
                .first()
            )
            if enrollment is None:
                self.add_error(
                    "student",
                    "Cet élève n'a pas d'inscription active pour cette année.",
                )
            else:
                cleaned["enrollment"] = enrollment
        return cleaned


class PaymentForm(forms.Form):
    amount = forms.DecimalField(
        label="Montant encaissé (FCFA)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(
            attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}
        ),
    )
    method = forms.ChoiceField(
        label="Mode de paiement",
        choices=PaymentMethod.choices,
        initial=PaymentMethod.CASH,
    )
    reference = forms.CharField(
        label="Référence / transaction",
        required=False,
        max_length=120,
        help_text="Numéro de transaction Orange Money, Wave, chèque, virement…",
    )
    paid_at = forms.DateField(
        label="Date du paiement",
        initial=date.today,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(
        label="Observation",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, invoice=None, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)
        if invoice is not None:
            self.fields["amount"].initial = invoice.balance
            self.fields["amount"].widget.attrs["max"] = str(invoice.balance)
            self.fields["amount"].help_text = (
                f"Solde restant : {invoice.balance} FCFA."
            )

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if self.invoice is not None and amount > self.invoice.balance:
            raise ValidationError(
                "Le montant dépasse le solde de la facture "
                f"({self.invoice.balance} FCFA)."
            )
        return amount


class CashSessionOpenForm(forms.Form):
    site = forms.ModelChoiceField(
        queryset=Site.all_objects.none(),
        required=False,
        label="Site / caisse",
        empty_label="Caisse principale",
    )
    opening_float = forms.DecimalField(
        label="Fonds de caisse initial (FCFA)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}
        ),
    )
    notes = forms.CharField(
        label="Observation",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["site"].queryset = Site.all_objects.filter(
            school=school
        ).order_by("-is_primary", "name")


class CashSessionCloseForm(forms.Form):
    counted_cash = forms.DecimalField(
        label="Espèces réellement comptées (FCFA)",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(
            attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}
        ),
    )
    notes = forms.CharField(
        label="Observation de clôture",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class CancelForm(forms.Form):
    reason = forms.CharField(
        label="Motif de l'annulation",
        min_length=5,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": (
                    "Expliquez la raison de l'annulation. "
                    "Cette information reste dans l'historique."
                ),
            }
        ),
    )


class FinanceExportForm(forms.Form):
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.all_objects.none(),
        label="Année scolaire à exporter",
    )

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        years = AcademicYear.all_objects.filter(school=school).order_by(
            "-start_date"
        )
        self.fields["academic_year"].queryset = years
        if not self.initial.get("academic_year"):
            self.fields["academic_year"].initial = years.first()


class InvoiceFilterForm(forms.Form):
    STATUTS = [("", "Tous les statuts"), *Invoice._meta.get_field("status").choices]
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.all_objects.none(),
        required=False,
        label="Année",
        empty_label="Toutes les années",
    )
    status = forms.ChoiceField(
        required=False, choices=STATUTS, label="Statut"
    )
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.all_objects.none(),
        required=False,
        label="Classe",
        empty_label="Toutes les classes",
    )
    q = forms.CharField(
        required=False,
        label="Recherche",
        widget=forms.TextInput(
            attrs={"placeholder": "Élève, matricule ou numéro de facture"}
        ),
    )
    overdue = forms.BooleanField(required=False, label="Uniquement les impayés")

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.all_objects.filter(
            school=school
        ).order_by("-start_date")
        self.fields["school_class"].queryset = (
            SchoolClass.all_objects.filter(school=school)
            .select_related("academic_year", "level", "series")
            .order_by("-academic_year__start_date", "level__order", "name")
        )
        self.fields["school_class"].label_from_instance = lambda school_class: (
            f"{school_class.display_name} ({school_class.academic_year.name})"
        )


class PaymentFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Recherche",
        widget=forms.TextInput(
            attrs={"placeholder": "Reçu, facture, élève ou référence"}
        ),
    )
    method = forms.ChoiceField(
        required=False,
        choices=[("", "Tous les modes"), *PaymentMethod.choices],
        label="Mode",
    )
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.all_objects.none(),
        required=False,
        label="Année",
        empty_label="Toutes les années",
    )
    include_cancelled = forms.BooleanField(
        required=False, label="Inclure les annulations"
    )

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.all_objects.filter(
            school=school
        ).order_by("-start_date")


class OverdueFilterForm(forms.Form):
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.all_objects.none(),
        required=False,
        label="Année",
        empty_label="Toutes les années",
    )
    school_class = forms.ModelChoiceField(
        queryset=SchoolClass.all_objects.none(),
        required=False,
        label="Classe",
        empty_label="Toutes les classes",
    )
    as_of = forms.DateField(
        required=False,
        label="À la date du",
        initial=date.today,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, school, **kwargs):
        self.school = school
        super().__init__(*args, **kwargs)
        self.fields["academic_year"].queryset = AcademicYear.all_objects.filter(
            school=school
        ).order_by("-start_date")
        self.fields["school_class"].queryset = (
            SchoolClass.all_objects.filter(school=school)
            .select_related("academic_year", "level", "series")
            .order_by("-academic_year__start_date", "level__order", "name")
        )
        self.fields["school_class"].label_from_instance = lambda school_class: (
            f"{school_class.display_name} ({school_class.academic_year.name})"
        )
