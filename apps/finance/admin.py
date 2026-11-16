from django.contrib import admin

from apps.common.admin import TenantModelAdmin, TenantTabularInline

from .models import (
    CashSession,
    Discount,
    DocumentSequence,
    Fee,
    Invoice,
    InvoiceDiscount,
    InvoiceInstallment,
    InvoiceLine,
    Payment,
    PaymentAllocation,
    PaymentPlan,
    PaymentPlanLine,
)


class PaymentPlanLineInline(TenantTabularInline):
    model = PaymentPlanLine
    extra = 0


@admin.register(Fee)
class FeeAdmin(TenantModelAdmin):
    list_display = (
        "name",
        "school",
        "academic_year",
        "level",
        "series",
        "amount",
        "is_active",
    )
    list_filter = ("school", "academic_year", "level", "is_active")
    search_fields = ("name", "school__name", "school__code")


@admin.register(PaymentPlan)
class PaymentPlanAdmin(TenantModelAdmin):
    list_display = (
        "name",
        "school",
        "academic_year",
        "level",
        "series",
        "is_active",
    )
    list_filter = ("school", "academic_year", "level", "is_active")
    search_fields = ("name", "school__name", "school__code")
    inlines = [PaymentPlanLineInline]


@admin.register(PaymentPlanLine)
class PaymentPlanLineAdmin(TenantModelAdmin):
    list_display = ("plan", "sequence", "label", "due_date", "percentage")
    list_filter = ("plan__school", "plan__academic_year")
    search_fields = ("label", "plan__name")


@admin.register(Discount)
class DiscountAdmin(TenantModelAdmin):
    list_display = (
        "label",
        "student",
        "school",
        "academic_year",
        "kind",
        "value",
        "is_active",
    )
    list_filter = ("school", "academic_year", "kind", "is_active")
    search_fields = (
        "label",
        "student__first_name",
        "student__last_name",
        "student__matricule",
    )


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(TenantModelAdmin):
    list_display = (
        "school",
        "academic_year",
        "document_type",
        "last_value",
    )
    list_filter = ("school", "academic_year", "document_type")


class InvoiceLineInline(TenantTabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ("fee",)


class InvoiceDiscountInline(TenantTabularInline):
    model = InvoiceDiscount
    extra = 0
    readonly_fields = ("discount", "label", "kind", "value", "amount")


class InvoiceInstallmentInline(TenantTabularInline):
    model = InvoiceInstallment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(TenantModelAdmin):
    list_display = (
        "number",
        "student",
        "school",
        "academic_year",
        "status",
        "total",
        "paid_total",
        "issue_date",
    )
    list_filter = ("school", "academic_year", "status")
    search_fields = (
        "number",
        "student__first_name",
        "student__last_name",
        "student__matricule",
    )
    date_hierarchy = "issue_date"
    inlines = [
        InvoiceLineInline,
        InvoiceDiscountInline,
        InvoiceInstallmentInline,
    ]


@admin.register(InvoiceLine)
class InvoiceLineAdmin(TenantModelAdmin):
    list_display = ("invoice", "description", "amount")
    list_filter = ("invoice__school", "invoice__academic_year")
    search_fields = ("description", "invoice__number")


@admin.register(InvoiceDiscount)
class InvoiceDiscountAdmin(TenantModelAdmin):
    list_display = ("invoice", "label", "kind", "value", "amount")
    list_filter = ("invoice__school", "invoice__academic_year", "kind")


@admin.register(InvoiceInstallment)
class InvoiceInstallmentAdmin(TenantModelAdmin):
    list_display = (
        "invoice",
        "sequence",
        "label",
        "due_date",
        "amount",
        "paid_amount",
    )
    list_filter = ("invoice__school", "invoice__academic_year")
    search_fields = ("label", "invoice__number")


class PaymentAllocationInline(TenantTabularInline):
    model = PaymentAllocation
    extra = 0


@admin.register(Payment)
class PaymentAdmin(TenantModelAdmin):
    list_display = (
        "receipt_number",
        "invoice",
        "school",
        "amount",
        "method",
        "paid_at",
        "cancelled_at",
    )
    list_filter = ("school", "method", "paid_at", "cancelled_at")
    search_fields = (
        "receipt_number",
        "reference",
        "invoice__number",
        "invoice__student__last_name",
    )
    date_hierarchy = "paid_at"
    inlines = [PaymentAllocationInline]


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(TenantModelAdmin):
    list_display = ("payment", "installment", "amount")
    list_filter = ("payment__school",)
    search_fields = ("payment__receipt_number", "installment__label")


@admin.register(CashSession)
class CashSessionAdmin(TenantModelAdmin):
    list_display = (
        "school",
        "status",
        "opened_at",
        "opened_by",
        "closed_at",
        "opening_float",
        "expected_cash",
        "counted_cash",
        "difference",
    )
    list_filter = ("school", "status")
    search_fields = ("school__name", "school__code")
    date_hierarchy = "opened_at"
