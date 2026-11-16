from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.academics.models import AcademicYear, Level, Series
from apps.common.tenancy import TenantModel
from apps.students.models import Enrollment, Student
from apps.tenancy.models import School, Site

MONEY_MIN = Decimal("0.01")
ZERO = Decimal("0.00")


class Fee(TenantModel):
    """Frais scolaire applicable à une année, un niveau et/ou une série."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="fees"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="fees"
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.CASCADE,
        related_name="fees",
        null=True,
        blank=True,
    )
    series = models.ForeignKey(
        Series,
        on_delete=models.CASCADE,
        related_name="fees",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(MONEY_MIN)],
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_fees",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["academic_year__start_date", "level__order", "name"]
        verbose_name = "frais scolaire"
        verbose_name_plural = "frais scolaires"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="fee_amount_positive"
            )
        ]

    def clean(self):
        errors = {}
        self.name = (self.name or "").strip()
        if not self.name:
            errors["name"] = "Le libellé du frais est obligatoire."
        if self.school_id and self.academic_year_id:
            if self.academic_year.school_id != self.school_id:
                errors["academic_year"] = (
                    "L'année scolaire doit appartenir à la même école."
                )
        if self.level_id and self.school_id:
            if self.level.school_id != self.school_id:
                errors["level"] = "Le niveau doit appartenir à la même école."
        if self.series_id:
            if not self.level_id:
                errors["series"] = (
                    "Une série ne peut être définie sans niveau."
                )
            elif self.series.level_id != self.level_id:
                errors["series"] = "La série doit appartenir au niveau indiqué."
        if self.name and self.school_id and self.academic_year_id:
            duplicates = Fee.all_objects.filter(
                school_id=self.school_id,
                academic_year_id=self.academic_year_id,
                name__iexact=self.name,
                level_id=self.level_id,
                series_id=self.series_id,
            )
            if self.pk:
                duplicates = duplicates.exclude(pk=self.pk)
            if duplicates.exists():
                errors["name"] = (
                    "Un frais portant ce libellé existe déjà pour ce périmètre."
                )
        if errors:
            raise ValidationError(errors)

    def applies_to(self, school_class):
        if not self.is_active:
            return False
        if self.academic_year_id != school_class.academic_year_id:
            return False
        if self.level_id and self.level_id != school_class.level_id:
            return False
        if self.series_id and self.series_id != school_class.series_id:
            return False
        return True

    @property
    def scope_label(self):
        parts = []
        if self.level_id:
            parts.append(self.level.name)
        if self.series_id:
            parts.append(self.series.name)
        return " · ".join(parts) or "Toute l'école"

    def __str__(self):
        return f"{self.name} — {self.scope_label} ({self.academic_year.name})"


class PaymentPlan(TenantModel):
    """Échéancier de paiement, éventuellement propre à un niveau/série."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="payment_plans"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="payment_plans"
    )
    level = models.ForeignKey(
        Level,
        on_delete=models.CASCADE,
        related_name="payment_plans",
        null=True,
        blank=True,
    )
    series = models.ForeignKey(
        Series,
        on_delete=models.CASCADE,
        related_name="payment_plans",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_payment_plans",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["academic_year__start_date", "name"]
        verbose_name = "échéancier"
        verbose_name_plural = "échéanciers"

    def clean(self):
        errors = {}
        self.name = (self.name or "").strip()
        if not self.name:
            errors["name"] = "Le nom de l'échéancier est obligatoire."
        if self.school_id and self.academic_year_id:
            if self.academic_year.school_id != self.school_id:
                errors["academic_year"] = (
                    "L'année scolaire doit appartenir à la même école."
                )
        if self.level_id and self.school_id:
            if self.level.school_id != self.school_id:
                errors["level"] = "Le niveau doit appartenir à la même école."
        if self.series_id:
            if not self.level_id:
                errors["series"] = (
                    "Une série ne peut être définie sans niveau."
                )
            elif self.series.level_id != self.level_id:
                errors["series"] = "La série doit appartenir au niveau indiqué."
        if errors:
            raise ValidationError(errors)

    @property
    def scope_label(self):
        parts = []
        if self.level_id:
            parts.append(self.level.name)
        if self.series_id:
            parts.append(self.series.name)
        return " · ".join(parts) or "Toute l'école"

    @property
    def total_percentage(self):
        return sum(
            (
                line.percentage
                for line in PaymentPlanLine.all_objects.filter(plan=self)
            ),
            Decimal("0.00"),
        )

    def __str__(self):
        return f"{self.name} — {self.scope_label} ({self.academic_year.name})"


class PaymentPlanLine(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("plan__school__organization_id", "organization_id"),
        "school": ("plan__school_id", "school_id"),
    }

    plan = models.ForeignKey(
        PaymentPlan, on_delete=models.CASCADE, related_name="lines"
    )
    sequence = models.PositiveSmallIntegerField(default=1)
    label = models.CharField(max_length=80)
    due_date = models.DateField()
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(MONEY_MIN),
            MaxValueValidator(Decimal("100.00")),
        ],
    )

    class Meta:
        ordering = ["plan", "sequence", "due_date"]
        verbose_name = "ligne d'échéancier"
        verbose_name_plural = "lignes d'échéancier"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "sequence"],
                name="uniq_payment_plan_line_sequence",
            ),
            models.CheckConstraint(
                condition=Q(percentage__gt=0, percentage__lte=100),
                name="payment_plan_line_percentage_range",
            ),
        ]

    def clean(self):
        errors = {}
        self.label = (self.label or "").strip()
        if not self.label:
            errors["label"] = "Le libellé de l'échéance est obligatoire."
        if self.sequence is not None and self.sequence < 1:
            errors["sequence"] = "L'ordre doit être supérieur ou égal à 1."
        if self.percentage is not None:
            if self.percentage <= 0 or self.percentage > 100:
                errors["percentage"] = (
                    "Le pourcentage doit être compris entre 0 et 100."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.sequence}. {self.label} — {self.percentage} %"


class DiscountKind(models.TextChoices):
    PERCENTAGE = "percentage", "Pourcentage"
    FIXED = "fixed", "Montant fixe"


class Discount(TenantModel):
    """Remise ou bourse accordée à un élève pour une année scolaire."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="discounts"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="discounts"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="discounts"
    )
    label = models.CharField(max_length=120)
    kind = models.CharField(
        max_length=20,
        choices=DiscountKind.choices,
        default=DiscountKind.PERCENTAGE,
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(MONEY_MIN)],
    )
    reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_discounts",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["academic_year__start_date", "student__last_name", "label"]
        verbose_name = "remise"
        verbose_name_plural = "remises"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year", "label"],
                name="uniq_discount_label_per_student_year",
            ),
            models.CheckConstraint(
                condition=Q(value__gt=0), name="discount_value_positive"
            ),
        ]

    def clean(self):
        errors = {}
        self.label = (self.label or "").strip()
        if not self.label:
            errors["label"] = "Le libellé de la remise est obligatoire."
        if self.student_id and self.school_id:
            if self.student.school_id != self.school_id:
                errors["student"] = (
                    "L'élève doit appartenir à la même école."
                )
        if self.academic_year_id and self.school_id:
            if self.academic_year.school_id != self.school_id:
                errors["academic_year"] = (
                    "L'année scolaire doit appartenir à la même école."
                )
        if self.kind == DiscountKind.PERCENTAGE and self.value is not None:
            if self.value > 100:
                errors["value"] = (
                    "Une remise en pourcentage ne peut pas dépasser 100 %."
                )
        if errors:
            raise ValidationError(errors)

    def compute_amount(self, subtotal):
        if self.kind == DiscountKind.PERCENTAGE:
            return (subtotal * self.value / Decimal("100")).quantize(
                Decimal("0.01")
            )
        return min(self.value, subtotal)

    @property
    def value_label(self):
        if self.kind == DiscountKind.PERCENTAGE:
            return f"{self.value} %"
        return f"{self.value} FCFA"

    def __str__(self):
        return f"{self.label} — {self.student.full_name} ({self.academic_year.name})"


class DocumentSequence(TenantModel):
    """Compteur de numérotation continue par école et année."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    DOCUMENT_INVOICE = "invoice"
    DOCUMENT_RECEIPT = "receipt"
    DOCUMENT_TYPE_CHOICES = [
        (DOCUMENT_INVOICE, "Facture"),
        (DOCUMENT_RECEIPT, "Reçu"),
    ]

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="document_sequences"
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="document_sequences",
    )
    document_type = models.CharField(
        max_length=20, choices=DOCUMENT_TYPE_CHOICES
    )
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "compteur de documents"
        verbose_name_plural = "compteurs de documents"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "document_type"],
                name="uniq_document_sequence_per_year",
            )
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} {self.academic_year.name} : {self.last_value}"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Brouillon"
    ISSUED = "issued", "Émise"
    PARTIAL = "partial", "Partiellement payée"
    PAID = "paid", "Payée"
    CANCELLED = "cancelled", "Annulée"


class Invoice(TenantModel):
    """Facture d'un élève pour une année scolaire."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="invoices"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="invoices"
    )
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="invoices"
    )
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.SET_NULL,
        related_name="invoices",
        null=True,
        blank=True,
    )
    payment_plan = models.ForeignKey(
        PaymentPlan,
        on_delete=models.SET_NULL,
        related_name="invoices",
        null=True,
        blank=True,
    )
    number = models.CharField(max_length=30)
    issue_date = models.DateField(default=date.today)
    due_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.ISSUED,
    )
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    discount_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    paid_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    notes = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="cancelled_invoices",
        null=True,
        blank=True,
    )
    cancellation_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_invoices",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-issue_date", "-number"]
        verbose_name = "facture"
        verbose_name_plural = "factures"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "number"],
                name="uniq_invoice_number_per_school",
            ),
            models.UniqueConstraint(
                fields=["school", "academic_year", "student"],
                condition=~Q(status=InvoiceStatus.CANCELLED),
                name="uniq_active_invoice_per_student_year",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0), name="invoice_subtotal_positive"
            ),
            models.CheckConstraint(
                condition=Q(discount_total__gte=0),
                name="invoice_discount_positive",
            ),
            models.CheckConstraint(
                condition=Q(total__gte=0), name="invoice_total_positive"
            ),
            models.CheckConstraint(
                condition=Q(paid_total__gte=0),
                name="invoice_paid_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "academic_year", "status"],
                name="invoice_year_status_idx",
            ),
            models.Index(
                fields=["school", "student"], name="invoice_student_idx"
            ),
        ]

    def clean(self):
        errors = {}
        if self.student_id and self.school_id:
            if self.student.school_id != self.school_id:
                errors["student"] = (
                    "L'élève doit appartenir à la même école."
                )
        if self.academic_year_id and self.school_id:
            if self.academic_year.school_id != self.school_id:
                errors["academic_year"] = (
                    "L'année scolaire doit appartenir à la même école."
                )
        if self.enrollment_id:
            if self.student_id and self.enrollment.student_id != self.student_id:
                errors["enrollment"] = (
                    "L'inscription ne correspond pas à l'élève."
                )
            if (
                self.academic_year_id
                and self.enrollment.academic_year_id != self.academic_year_id
            ):
                errors["enrollment"] = (
                    "L'inscription ne correspond pas à l'année scolaire."
                )
        if self.issue_date and self.due_date and self.due_date < self.issue_date:
            errors["due_date"] = (
                "La date d'échéance ne peut pas précéder la date d'émission."
            )
        if self.subtotal is not None and self.subtotal < 0:
            errors["subtotal"] = "Le sous-total ne peut pas être négatif."
        if self.discount_total is not None and self.discount_total < 0:
            errors["discount_total"] = "Le total des remises ne peut pas être négatif."
        if self.total is not None and self.total < 0:
            errors["total"] = "Le total ne peut pas être négatif."
        if self.paid_total is not None and self.paid_total < 0:
            errors["paid_total"] = "Le total payé ne peut pas être négatif."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.student_id:
            self.school_id = self.student.school_id
        super().save(*args, **kwargs)

    @property
    def balance(self):
        return max(self.total - self.paid_total, ZERO)

    @property
    def is_cancelled(self):
        return self.status == InvoiceStatus.CANCELLED

    @property
    def is_paid(self):
        return self.status == InvoiceStatus.PAID

    @property
    def is_overdue(self):
        return bool(self.overdue_amount)

    @property
    def overdue_amount(self):
        today = date.today()
        return sum(
            (
                installment.balance
                for installment in InvoiceInstallment.all_objects.filter(
                    invoice=self, due_date__lt=today
                )
                if installment.balance > 0
            ),
            ZERO,
        )

    def __str__(self):
        return f"{self.number} — {self.student.full_name}"


class InvoiceLine(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("invoice__school__organization_id", "organization_id"),
        "school": ("invoice__school_id", "school_id"),
    }

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="lines"
    )
    fee = models.ForeignKey(
        Fee,
        on_delete=models.SET_NULL,
        related_name="invoice_lines",
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=160)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(MONEY_MIN)],
    )

    class Meta:
        ordering = ["invoice", "id"]
        verbose_name = "ligne de facture"
        verbose_name_plural = "lignes de facture"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="invoice_line_amount_positive"
            )
        ]

    def clean(self):
        errors = {}
        if self.fee_id and self.invoice_id:
            if self.fee.school_id != self.invoice.school_id:
                errors["fee"] = (
                    "Le frais doit appartenir à l'école de la facture."
                )
        if not (self.description or "").strip():
            errors["description"] = "La description est obligatoire."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not (self.description or "").strip() and self.fee_id:
            self.description = self.fee.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} — {self.amount}"


class InvoiceDiscount(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("invoice__school__organization_id", "organization_id"),
        "school": ("invoice__school_id", "school_id"),
    }

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="discounts"
    )
    discount = models.ForeignKey(
        Discount,
        on_delete=models.SET_NULL,
        related_name="invoice_discounts",
        null=True,
        blank=True,
    )
    label = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=DiscountKind.choices)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )

    class Meta:
        ordering = ["invoice", "id"]
        verbose_name = "remise de facture"
        verbose_name_plural = "remises de facture"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="invoice_discount_amount_positive",
            )
        ]

    def __str__(self):
        return f"{self.label} — {self.amount}"


class InvoiceInstallment(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": ("invoice__school__organization_id", "organization_id"),
        "school": ("invoice__school_id", "school_id"),
    }

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="installments"
    )
    sequence = models.PositiveSmallIntegerField(default=1)
    label = models.CharField(max_length=80)
    due_date = models.DateField()
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
    )
    paid_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )

    class Meta:
        ordering = ["invoice", "sequence", "due_date"]
        verbose_name = "échéance de facture"
        verbose_name_plural = "échéances de facture"
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "sequence"],
                name="uniq_invoice_installment_sequence",
            ),
            models.CheckConstraint(
                condition=Q(paid_amount__gte=0),
                name="invoice_installment_paid_positive",
            ),
            models.CheckConstraint(
                condition=Q(paid_amount__lte=models.F("amount")),
                name="invoice_installment_paid_within_amount",
            ),
        ]

    @property
    def balance(self):
        return max(self.amount - self.paid_amount, ZERO)

    @property
    def is_overdue(self):
        return self.due_date < date.today() and self.balance > 0

    def __str__(self):
        return f"{self.label} — {self.due_date}"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Espèces"
    ORANGE_MONEY = "orange_money", "Orange Money"
    WAVE = "wave", "Wave"
    MOBICASH = "mobicash", "Mobicash"
    BANK_TRANSFER = "bank_transfer", "Virement bancaire"
    CHEQUE = "cheque", "Chèque"


class Payment(TenantModel):
    """Encaissement rattaché à une facture et à un reçu."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="payments"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    receipt_number = models.CharField(max_length=30)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(MONEY_MIN)],
    )
    method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    reference = models.CharField(max_length=120, blank=True)
    paid_at = models.DateField(default=date.today)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="received_payments",
        null=True,
        blank=True,
    )
    cash_session = models.ForeignKey(
        "CashSession",
        on_delete=models.SET_NULL,
        related_name="payments",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="cancelled_payments",
        null=True,
        blank=True,
    )
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-paid_at", "-created_at"]
        verbose_name = "encaissement"
        verbose_name_plural = "encaissements"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "receipt_number"],
                name="uniq_receipt_number_per_school",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="payment_amount_positive"
            ),
        ]
        indexes = [
            models.Index(
                fields=["school", "paid_at"], name="payment_paid_at_idx"
            ),
            models.Index(
                fields=["school", "method"], name="payment_method_idx"
            ),
        ]

    def clean(self):
        errors = {}
        if self.invoice_id and self.school_id:
            if self.invoice.school_id != self.school_id:
                errors["invoice"] = (
                    "La facture doit appartenir à la même école."
                )
        if self.cash_session_id and self.school_id:
            if self.cash_session.school_id != self.school_id:
                errors["cash_session"] = (
                    "La caisse doit appartenir à la même école."
                )
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "Le montant doit être positif."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.invoice_id:
            self.school_id = self.invoice.school_id
        super().save(*args, **kwargs)

    @property
    def is_cancelled(self):
        return self.cancelled_at is not None

    def __str__(self):
        return f"{self.receipt_number} — {self.amount}"


class PaymentAllocation(TenantModel):
    TENANT_SCOPE_LOOKUPS = {
        "organization": (
            "payment__invoice__school__organization_id",
            "organization_id",
        ),
        "school": ("payment__invoice__school_id", "school_id"),
    }

    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="allocations"
    )
    installment = models.ForeignKey(
        InvoiceInstallment,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(MONEY_MIN)],
    )

    class Meta:
        verbose_name = "affectation de paiement"
        verbose_name_plural = "affectations de paiement"
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "installment"],
                name="uniq_payment_installment_allocation",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="payment_allocation_amount_positive",
            ),
        ]

    def clean(self):
        if self.payment_id and self.installment_id:
            if (
                self.payment.invoice_id
                != self.installment.invoice_id
            ):
                raise ValidationError(
                    {"installment": "L'échéance doit appartenir à la facture."}
                )

    def __str__(self):
        return f"{self.payment.receipt_number} → {self.installment.label}"


class CashSessionStatus(models.TextChoices):
    OPEN = "open", "Ouverte"
    CLOSED = "closed", "Clôturée"


class CashSession(TenantModel):
    """Session de caisse permettant de contrôler les espèces encaissées."""

    TENANT_SCOPE_LOOKUPS = {
        "organization": ("school__organization_id", "organization_id"),
        "school": ("school_id", "school_id"),
    }

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="cash_sessions"
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.SET_NULL,
        related_name="cash_sessions",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=CashSessionStatus.choices,
        default=CashSessionStatus.OPEN,
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="opened_cash_sessions",
        null=True,
        blank=True,
    )
    opened_at = models.DateTimeField(default=timezone.now)
    opening_float = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="closed_cash_sessions",
        null=True,
        blank=True,
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    counted_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO)],
    )
    expected_cash = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    difference = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]
        verbose_name = "session de caisse"
        verbose_name_plural = "sessions de caisse"
        constraints = [
            models.UniqueConstraint(
                fields=["school"],
                condition=Q(status=CashSessionStatus.OPEN),
                name="uniq_open_cash_session_per_school",
            ),
            models.CheckConstraint(
                condition=Q(opening_float__gte=0),
                name="cash_session_opening_positive",
            ),
        ]

    def clean(self):
        errors = {}
        if self.site_id and self.school_id:
            if self.site.school_id != self.school_id:
                errors["site"] = "Le site doit appartenir à la même école."
        if self.opening_float is not None and self.opening_float < 0:
            errors["opening_float"] = "Le fonds de caisse ne peut pas être négatif."
        if self.counted_cash is not None and self.counted_cash < 0:
            errors["counted_cash"] = "Le montant compté ne peut pas être négatif."
        if errors:
            raise ValidationError(errors)

    @property
    def is_open(self):
        return self.status == CashSessionStatus.OPEN

    def __str__(self):
        return f"Caisse {self.school.code} — {self.opened_at:%d/%m/%Y %H:%M}"
