from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify

from apps.academics.models import AcademicYear
from apps.academics.utils import current_academic_year
from apps.tenancy.access import (
    user_can_collect_payments,
    user_can_manage_finance,
    user_can_view_finance,
)
from apps.tenancy.selectors import tenant_scoped_view

from .exports import build_finance_workbook
from .forms import (
    CancelForm,
    CashSessionCloseForm,
    CashSessionOpenForm,
    DiscountForm,
    FeeForm,
    FinanceExportForm,
    InvoiceFilterForm,
    InvoiceGenerateForm,
    OverdueFilterForm,
    PaymentFilterForm,
    PaymentForm,
    PaymentPlanForm,
    PaymentPlanLineFormSet,
)
from .models import (
    CashSession,
    CashSessionStatus,
    Discount,
    Fee,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentPlan,
)
from .services import (
    cancel_invoice,
    cancel_payment,
    cash_session_summary,
    close_cash_session,
    generate_invoice_for_enrollment,
    generate_invoices_for_class,
    open_cash_session,
    overdue_installments,
    record_payment,
)

ZERO = Decimal("0.00")


def _school_kwargs(school):
    return {
        "org_slug": school.organization.slug,
        "school_code": school.code,
    }


def _finance_url(school, name, **kwargs):
    return reverse(f"school:{name}", kwargs={**_school_kwargs(school), **kwargs})


def _ensure_finance_view(request):
    if not user_can_view_finance(request.user, request.school):
        raise PermissionDenied(
            "Vous n'avez pas accès aux finances de cette école."
        )


def _ensure_finance_management(request):
    if not user_can_manage_finance(request.user, request.school):
        raise PermissionDenied(
            "Seuls la direction et le comptable peuvent gérer les finances."
        )


def _ensure_payment_collection(request):
    if not user_can_collect_payments(request.user, request.school):
        raise PermissionDenied(
            "Vous n'avez pas le droit d'encaisser un paiement dans cette école."
        )


def _selected_year(request, years, param="annee"):
    year_id = request.GET.get(param)
    selected = None
    if year_id:
        try:
            selected = years.get(pk=year_id)
        except (AcademicYear.DoesNotExist, ValidationError, ValueError):
            selected = None
    return selected or current_academic_year(request.school) or years.first()


def _add_validation_error(form, error):
    """Report a service ValidationError on the most relevant form field."""
    if hasattr(error, "message_dict"):
        for field, messages_list in error.message_dict.items():
            target = field if field in form.fields else None
            for message in messages_list:
                form.add_error(target, message)
    elif hasattr(error, "messages"):
        for message in error.messages:
            form.add_error(None, message)
    else:
        form.add_error(None, str(error))


def _form_context(school, title, intro, cancel_url):
    return {
        "school": school,
        "form_title": title,
        "form_intro": intro,
        "cancel_url": cancel_url,
    }


@login_required
@tenant_scoped_view
def finance_home(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    year = _selected_year(request, years)

    invoices = Invoice.objects.filter(school=school)
    payments = Payment.objects.filter(school=school)
    if year:
        invoices = invoices.filter(academic_year=year)
        payments = payments.filter(invoice__academic_year=year)

    active_invoices = invoices.exclude(status=InvoiceStatus.CANCELLED)
    totals = active_invoices.aggregate(
        billed=Sum("total"),
        discounted=Sum("discount_total"),
        collected=Sum("paid_total"),
    )
    billed = totals["billed"] or ZERO
    collected = totals["collected"] or ZERO
    balance = max(billed - collected, ZERO)
    overdue = list(overdue_installments(school, academic_year=year))
    overdue_total = sum(
        (installment.balance for installment in overdue), ZERO
    )
    open_session = CashSession.objects.filter(
        school=school, status=CashSessionStatus.OPEN
    ).first()
    cash_total = ZERO
    if open_session:
        cash_total = cash_session_summary(open_session)["cash_total"]

    recent_invoices = (
        active_invoices.select_related("student", "enrollment__school_class")
        .order_by("-issue_date", "-number")[:8]
    )
    recent_payments = (
        payments.filter(cancelled_at__isnull=True)
        .select_related("invoice__student")
        .order_by("-paid_at", "-created_at")[:8]
    )

    context = {
        "school": school,
        "years": years,
        "selected_year": year,
        "billed": billed,
        "discounted": totals["discounted"] or ZERO,
        "collected": collected,
        "balance": balance,
        "overdue_total": overdue_total,
        "overdue_count": len(overdue),
        "invoice_count": active_invoices.count(),
        "paid_count": active_invoices.filter(
            status=InvoiceStatus.PAID
        ).count(),
        "partial_count": active_invoices.filter(
            status=InvoiceStatus.PARTIAL
        ).count(),
        "open_session": open_session,
        "cash_total": cash_total,
        "recent_invoices": recent_invoices,
        "recent_payments": recent_payments,
        "can_manage_finance": user_can_manage_finance(
            request.user, school
        ),
        "can_collect_payments": user_can_collect_payments(
            request.user, school
        ),
    }
    return render(request, "finance/home.html", context)


# ---------------------------------------------------------------------------
# Frais scolaires
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def fee_list(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    year = _selected_year(request, years)
    fees = Fee.objects.filter(school=school).select_related(
        "academic_year", "level", "series"
    )
    if year:
        fees = fees.filter(academic_year=year)
    fees = fees.order_by(
        "-academic_year__start_date", "level__order", "name"
    )
    return render(
        request,
        "finance/fee_list.html",
        {
            "school": school,
            "years": years,
            "selected_year": year,
            "fees": fees,
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def fee_create(request, org_slug, school_code):
    _ensure_finance_management(request)
    school = request.school
    form = FeeForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        fee = form.save(commit=False)
        fee.created_by = request.user
        fee.save()
        messages.success(
            request, f"Frais « {fee.name} » enregistré pour {fee.academic_year.name}."
        )
        return redirect(_finance_url(school, "finance_fee_list"))
    context = _form_context(
        school,
        "Nouveau frais scolaire",
        "Définissez un montant par année, niveau et série. "
        "Les frais actifs sont repris automatiquement sur les factures.",
        _finance_url(school, "finance_fee_list"),
    )
    context["form"] = form
    context["submit_label"] = "Enregistrer le frais"
    return render(request, "generic_form.html", context)


@login_required
@tenant_scoped_view
def fee_edit(request, org_slug, school_code, fee_id):
    _ensure_finance_management(request)
    school = request.school
    fee = get_object_or_404(Fee, pk=fee_id, school=school)
    form = FeeForm(request.POST or None, instance=fee, school=school)
    if request.method == "POST" and form.is_valid():
        fee = form.save()
        messages.success(request, f"Frais « {fee.name} » mis à jour.")
        return redirect(_finance_url(school, "finance_fee_list"))
    context = _form_context(
        school,
        "Modifier un frais scolaire",
        f"Frais « {fee.name} » — {fee.academic_year.name}.",
        _finance_url(school, "finance_fee_list"),
    )
    context["form"] = form
    context["submit_label"] = "Mettre à jour"
    return render(request, "generic_form.html", context)


# ---------------------------------------------------------------------------
# Échéanciers
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def plan_list(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    year = _selected_year(request, years)
    plans = (
        PaymentPlan.objects.filter(school=school)
        .select_related("academic_year", "level", "series")
        .prefetch_related("lines")
    )
    if year:
        plans = plans.filter(academic_year=year)
    plans = plans.order_by("-academic_year__start_date", "name")
    return render(
        request,
        "finance/plan_list.html",
        {
            "school": school,
            "years": years,
            "selected_year": year,
            "plans": plans,
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


def _plan_form_context(school, plan, form, formset, title, submit_label):
    return {
        "school": school,
        "plan": plan,
        "form": form,
        "formset": formset,
        "form_title": title,
        "form_intro": (
            "Les pourcentages des échéances doivent totaliser exactement 100 %. "
            "Les échéances sont figées sur la facture au moment de sa génération."
        ),
        "cancel_url": _finance_url(school, "finance_plan_list"),
        "submit_label": submit_label,
    }


@login_required
@tenant_scoped_view
def plan_create(request, org_slug, school_code):
    _ensure_finance_management(request)
    school = request.school
    plan = PaymentPlan(school=school)
    form = PaymentPlanForm(request.POST or None, instance=plan, school=school)
    formset = PaymentPlanLineFormSet(
        request.POST or None,
        instance=plan,
        prefix="lignes",
        initial=[
            {"sequence": 1, "label": "1ère tranche"},
            {"sequence": 2, "label": "2ème tranche"},
            {"sequence": 3, "label": "3ème tranche"},
        ],
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            plan = form.save(commit=False)
            plan.created_by = request.user
            plan.save()
            formset.instance = plan
            formset.save()
        messages.success(
            request, f"Échéancier « {plan.name} » créé."
        )
        return redirect(_finance_url(school, "finance_plan_list"))
    return render(
        request,
        "finance/plan_form.html",
        _plan_form_context(
            school,
            plan,
            form,
            formset,
            "Nouvel échéancier",
            "Créer l'échéancier",
        ),
    )


@login_required
@tenant_scoped_view
def plan_edit(request, org_slug, school_code, plan_id):
    _ensure_finance_management(request)
    school = request.school
    plan = get_object_or_404(PaymentPlan, pk=plan_id, school=school)
    form = PaymentPlanForm(request.POST or None, instance=plan, school=school)
    formset = PaymentPlanLineFormSet(
        request.POST or None, instance=plan, prefix="lignes"
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            plan = form.save()
            formset.instance = plan
            formset.save()
        messages.success(
            request, f"Échéancier « {plan.name} » mis à jour."
        )
        return redirect(_finance_url(school, "finance_plan_list"))
    return render(
        request,
        "finance/plan_form.html",
        _plan_form_context(
            school,
            plan,
            form,
            formset,
            "Modifier un échéancier",
            "Mettre à jour",
        ),
    )


# ---------------------------------------------------------------------------
# Remises
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def discount_list(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    year = _selected_year(request, years)
    discounts = Discount.objects.filter(school=school).select_related(
        "academic_year", "student"
    )
    if year:
        discounts = discounts.filter(academic_year=year)
    query = request.GET.get("q", "").strip()
    if query:
        discounts = discounts.filter(
            Q(student__last_name__icontains=query)
            | Q(student__first_name__icontains=query)
            | Q(student__matricule__icontains=query)
            | Q(label__icontains=query)
        )
    discounts = discounts.order_by(
        "-academic_year__start_date", "student__last_name", "label"
    )
    return render(
        request,
        "finance/discount_list.html",
        {
            "school": school,
            "years": years,
            "selected_year": year,
            "discounts": discounts,
            "query": query,
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def discount_create(request, org_slug, school_code):
    _ensure_finance_management(request)
    school = request.school
    form = DiscountForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        discount = form.save(commit=False)
        discount.created_by = request.user
        discount.save()
        messages.success(
            request,
            f"Remise « {discount.label} » accordée à "
            f"{discount.student.full_name}.",
        )
        return redirect(_finance_url(school, "finance_discount_list"))
    context = _form_context(
        school,
        "Nouvelle remise",
        "Les remises actives sont appliquées à la prochaine facture de l'élève.",
        _finance_url(school, "finance_discount_list"),
    )
    context["form"] = form
    context["submit_label"] = "Accorder la remise"
    return render(request, "generic_form.html", context)


@login_required
@tenant_scoped_view
def discount_edit(request, org_slug, school_code, discount_id):
    _ensure_finance_management(request)
    school = request.school
    discount = get_object_or_404(Discount, pk=discount_id, school=school)
    form = DiscountForm(
        request.POST or None, instance=discount, school=school
    )
    if request.method == "POST" and form.is_valid():
        discount = form.save()
        messages.success(request, f"Remise « {discount.label} » mise à jour.")
        return redirect(_finance_url(school, "finance_discount_list"))
    context = _form_context(
        school,
        "Modifier une remise",
        f"{discount.student.full_name} — {discount.academic_year.name}.",
        _finance_url(school, "finance_discount_list"),
    )
    context["form"] = form
    context["submit_label"] = "Mettre à jour"
    return render(request, "generic_form.html", context)


# ---------------------------------------------------------------------------
# Factures
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def invoice_list(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    current = current_academic_year(school)
    form = InvoiceFilterForm(
        request.GET or None,
        school=school,
        initial={"academic_year": current} if current else None,
    )
    invoices = (
        Invoice.objects.filter(school=school)
        .select_related(
            "student",
            "enrollment__school_class",
            "enrollment__school_class__level",
            "enrollment__school_class__series",
        )
        .prefetch_related("installments")
    )
    year = None
    if form.is_valid():
        cleaned = form.cleaned_data
        year = cleaned.get("academic_year")
        if year is None and "academic_year" not in request.GET:
            year = current
        if year:
            invoices = invoices.filter(academic_year=year)
        if cleaned.get("status"):
            invoices = invoices.filter(status=cleaned["status"])
        if cleaned.get("school_class"):
            invoices = invoices.filter(
                enrollment__school_class=cleaned["school_class"]
            )
        if cleaned.get("q"):
            query = cleaned["q"]
            invoices = invoices.filter(
                Q(number__icontains=query)
                | Q(student__matricule__icontains=query)
                | Q(student__first_name__icontains=query)
                | Q(student__last_name__icontains=query)
            )
        if cleaned.get("overdue"):
            invoices = invoices.filter(
                status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIAL],
                installments__due_date__lt=date.today(),
                installments__amount__gt=F("installments__paid_amount"),
            ).distinct()
    else:
        year = current
        if year:
            invoices = invoices.filter(academic_year=year)

    invoices = invoices.order_by("-issue_date", "-number")
    totals = invoices.aggregate(
        subtotal=Sum("subtotal"),
        discount=Sum("discount_total"),
        total=Sum("total"),
        paid=Sum("paid_total"),
    )
    total = totals["total"] or ZERO
    paid = totals["paid"] or ZERO
    paginator = Paginator(invoices, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "finance/invoice_list.html",
        {
            "school": school,
            "form": form,
            "selected_year": year,
            "page_obj": page_obj,
            "invoices": page_obj.object_list,
            "total_count": paginator.count,
            "subtotal": totals["subtotal"] or ZERO,
            "discount_total": totals["discount"] or ZERO,
            "total": total,
            "paid": paid,
            "balance": max(total - paid, ZERO),
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def invoice_generate(request, org_slug, school_code):
    _ensure_finance_management(request)
    school = request.school
    form = InvoiceGenerateForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        plan = cleaned.get("payment_plan")
        issue_date = cleaned.get("issue_date")
        notes = cleaned.get("notes", "")
        try:
            if cleaned.get("school_class"):
                created, skipped = generate_invoices_for_class(
                    cleaned["school_class"],
                    user=request.user,
                    payment_plan=plan,
                    issue_date=issue_date,
                )
                messages.success(
                    request,
                    f"{len(created)} facture(s) créée(s), "
                    f"{len(skipped)} élève(s) déjà facturé(s).",
                )
                return redirect(
                    _finance_url(school, "finance_invoice_list")
                    + f"?academic_year={cleaned['academic_year'].pk}"
                )
            invoice, was_created = generate_invoice_for_enrollment(
                cleaned["enrollment"],
                user=request.user,
                payment_plan=plan,
                issue_date=issue_date,
                notes=notes,
            )
            if was_created:
                messages.success(
                    request, f"Facture {invoice.number} générée."
                )
            else:
                messages.info(
                    request,
                    f"Une facture active existe déjà pour cet élève "
                    f"({invoice.number}).",
                )
            return redirect(
                _finance_url(
                    school, "finance_invoice_detail", invoice_id=invoice.pk
                )
            )
        except ValidationError as error:
            _add_validation_error(form, error)
    return render(
        request,
        "finance/invoice_generate.html",
        {
            "school": school,
            "form": form,
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


def _invoice_queryset(school):
    return (
        Invoice.objects.filter(school=school)
        .select_related(
            "student",
            "student__school",
            "academic_year",
            "enrollment__school_class",
            "enrollment__school_class__level",
            "enrollment__school_class__series",
            "payment_plan",
            "created_by",
            "cancelled_by",
        )
        .prefetch_related(
            "lines",
            "discounts",
            "installments",
            "payments__received_by",
            "payments__cash_session",
        )
    )


@login_required
@tenant_scoped_view
def invoice_detail(request, org_slug, school_code, invoice_id):
    _ensure_finance_view(request)
    school = request.school
    invoice = get_object_or_404(
        _invoice_queryset(school), pk=invoice_id, school=school
    )
    payments = list(invoice.payments.all())
    active_payments = [payment for payment in payments if not payment.is_cancelled]
    open_session = CashSession.objects.filter(
        school=school, status=CashSessionStatus.OPEN
    ).first()
    return render(
        request,
        "finance/invoice_detail.html",
        {
            "school": school,
            "invoice": invoice,
            "lines": invoice.lines.all(),
            "discounts": invoice.discounts.all(),
            "installments": invoice.installments.all(),
            "payments": payments,
            "active_payments": active_payments,
            "open_session": open_session,
            "can_pay": (
                user_can_collect_payments(request.user, school)
                and invoice.status != InvoiceStatus.CANCELLED
                and invoice.balance > 0
            ),
            "can_cancel": (
                user_can_manage_finance(request.user, school)
                and invoice.status != InvoiceStatus.CANCELLED
                and not active_payments
            ),
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def invoice_print(request, org_slug, school_code, invoice_id):
    _ensure_finance_view(request)
    school = request.school
    invoice = get_object_or_404(
        _invoice_queryset(school), pk=invoice_id, school=school
    )
    return render(
        request,
        "finance/invoice_print.html",
        {
            "school": school,
            "invoice": invoice,
            "lines": invoice.lines.all(),
            "discounts": invoice.discounts.all(),
            "installments": invoice.installments.all(),
        },
    )


@login_required
@tenant_scoped_view
def invoice_cancel(request, org_slug, school_code, invoice_id):
    _ensure_finance_management(request)
    school = request.school
    invoice = get_object_or_404(
        _invoice_queryset(school), pk=invoice_id, school=school
    )
    if invoice.status == InvoiceStatus.CANCELLED:
        messages.info(request, "Cette facture est déjà annulée.")
        return redirect(
            _finance_url(
                school, "finance_invoice_detail", invoice_id=invoice.pk
            )
        )
    form = CancelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_invoice(invoice, request.user, form.cleaned_data["reason"])
        except ValidationError as error:
            _add_validation_error(form, error)
        else:
            messages.success(
                request, f"Facture {invoice.number} annulée."
            )
            return redirect(
                _finance_url(
                    school, "finance_invoice_detail", invoice_id=invoice.pk
                )
            )
    context = _form_context(
        school,
        f"Annuler la facture {invoice.number}",
        f"{invoice.student.full_name} — {invoice.total} FCFA. "
        "L'annulation est définitive et reste tracée.",
        _finance_url(
            school, "finance_invoice_detail", invoice_id=invoice.pk
        ),
    )
    context["form"] = form
    context["submit_label"] = "Confirmer l'annulation"
    return render(request, "generic_form.html", context)


# ---------------------------------------------------------------------------
# Encaissements et reçus
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def payment_create(request, org_slug, school_code, invoice_id):
    _ensure_payment_collection(request)
    school = request.school
    invoice = get_object_or_404(
        _invoice_queryset(school), pk=invoice_id, school=school
    )
    if invoice.status == InvoiceStatus.CANCELLED:
        messages.error(request, "Impossible d'encaisser une facture annulée.")
        return redirect(
            _finance_url(
                school, "finance_invoice_detail", invoice_id=invoice.pk
            )
        )
    if invoice.balance <= 0:
        messages.info(request, "Cette facture est déjà entièrement payée.")
        return redirect(
            _finance_url(
                school, "finance_invoice_detail", invoice_id=invoice.pk
            )
        )
    form = PaymentForm(request.POST or None, invoice=invoice)
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        try:
            payment = record_payment(
                invoice,
                amount=cleaned["amount"],
                method=cleaned["method"],
                user=request.user,
                reference=cleaned.get("reference", ""),
                paid_at=cleaned.get("paid_at"),
                notes=cleaned.get("notes", ""),
            )
        except ValidationError as error:
            _add_validation_error(form, error)
        else:
            messages.success(
                request,
                f"Paiement de {payment.amount} FCFA enregistré. "
                f"Reçu {payment.receipt_number}.",
            )
            return redirect(
                _finance_url(
                    school, "finance_payment_receipt", payment_id=payment.pk
                )
            )
    open_session = CashSession.objects.filter(
        school=school, status=CashSessionStatus.OPEN
    ).first()
    return render(
        request,
        "finance/payment_form.html",
        {
            "school": school,
            "invoice": invoice,
            "form": form,
            "open_session": open_session,
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def payment_receipt(request, org_slug, school_code, payment_id):
    _ensure_finance_view(request)
    school = request.school
    payment = get_object_or_404(
        Payment.objects.filter(school=school).select_related(
            "invoice",
            "invoice__student",
            "invoice__academic_year",
            "invoice__enrollment__school_class",
            "cash_session",
            "received_by",
            "cancelled_by",
        ),
        pk=payment_id,
        school=school,
    )
    return render(
        request,
        "finance/receipt.html",
        {"school": school, "payment": payment, "invoice": payment.invoice},
    )


@login_required
@tenant_scoped_view
def payment_list(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    current = current_academic_year(school)
    form = PaymentFilterForm(
        request.GET or None,
        school=school,
        initial={"academic_year": current} if current else None,
    )
    payments = (
        Payment.objects.filter(school=school)
        .select_related(
            "invoice",
            "invoice__student",
            "invoice__academic_year",
            "invoice__enrollment__school_class",
            "cash_session",
            "received_by",
        )
    )
    year = None
    if form.is_valid():
        cleaned = form.cleaned_data
        year = cleaned.get("academic_year")
        if year is None and "academic_year" not in request.GET:
            year = current
        if year:
            payments = payments.filter(invoice__academic_year=year)
        if cleaned.get("method"):
            payments = payments.filter(method=cleaned["method"])
        if cleaned.get("q"):
            query = cleaned["q"]
            payments = payments.filter(
                Q(receipt_number__icontains=query)
                | Q(reference__icontains=query)
                | Q(invoice__number__icontains=query)
                | Q(invoice__student__matricule__icontains=query)
                | Q(invoice__student__first_name__icontains=query)
                | Q(invoice__student__last_name__icontains=query)
            )
        if not cleaned.get("include_cancelled"):
            payments = payments.filter(cancelled_at__isnull=True)
    else:
        year = current
        if year:
            payments = payments.filter(invoice__academic_year=year)
        payments = payments.filter(cancelled_at__isnull=True)

    payments = payments.order_by("-paid_at", "-created_at")
    totals = payments.filter(cancelled_at__isnull=True).aggregate(
        total=Sum("amount")
    )
    paginator = Paginator(payments, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "finance/payment_list.html",
        {
            "school": school,
            "form": form,
            "selected_year": year,
            "page_obj": page_obj,
            "payments": page_obj.object_list,
            "total_count": paginator.count,
            "total": totals["total"] or ZERO,
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def payment_cancel(request, org_slug, school_code, payment_id):
    _ensure_finance_management(request)
    school = request.school
    payment = get_object_or_404(
        Payment.objects.filter(school=school).select_related(
            "invoice__student"
        ),
        pk=payment_id,
        school=school,
    )
    if payment.is_cancelled:
        messages.info(request, "Ce paiement est déjà annulé.")
        return redirect(
            _finance_url(
                school,
                "finance_invoice_detail",
                invoice_id=payment.invoice_id,
            )
        )
    form = CancelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancel_payment(payment, request.user, form.cleaned_data["reason"])
        except ValidationError as error:
            _add_validation_error(form, error)
        else:
            messages.success(
                request, f"Paiement {payment.receipt_number} annulé."
            )
            return redirect(
                _finance_url(
                    school,
                    "finance_invoice_detail",
                    invoice_id=payment.invoice_id,
                )
            )
    context = _form_context(
        school,
        f"Annuler le reçu {payment.receipt_number}",
        f"{payment.invoice.student.full_name} — {payment.amount} FCFA. "
        "Le paiement reste visible dans l'historique avec son motif.",
        _finance_url(
            school,
            "finance_invoice_detail",
            invoice_id=payment.invoice_id,
        ),
    )
    context["form"] = form
    context["submit_label"] = "Confirmer l'annulation"
    return render(request, "generic_form.html", context)


# ---------------------------------------------------------------------------
# Impayés
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def overdue_list(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    current = current_academic_year(school)
    form = OverdueFilterForm(
        request.GET or None,
        school=school,
        initial={"academic_year": current} if current else None,
    )
    year = None
    school_class = None
    as_of = date.today()
    if form.is_valid():
        cleaned = form.cleaned_data
        year = cleaned.get("academic_year")
        if year is None and "academic_year" not in request.GET:
            year = current
        school_class = cleaned.get("school_class")
        as_of = cleaned.get("as_of") or date.today()
    else:
        year = current
    installments = list(
        overdue_installments(
            school,
            academic_year=year,
            school_class=school_class,
            as_of=as_of,
        )
    )
    for installment in installments:
        installment.days_late = max(
            (as_of - installment.due_date).days, 0
        )
    total = sum((item.balance for item in installments), ZERO)
    paginator = Paginator(installments, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "finance/overdue_list.html",
        {
            "school": school,
            "form": form,
            "selected_year": year,
            "selected_class": school_class,
            "as_of": as_of,
            "page_obj": page_obj,
            "installments": page_obj.object_list,
            "total_count": paginator.count,
            "total": total,
        },
    )


# ---------------------------------------------------------------------------
# Caisse
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def cash_home(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    years = AcademicYear.objects.filter(school=school).order_by("-start_date")
    year = _selected_year(request, years)
    sessions = CashSession.objects.filter(school=school).select_related(
        "site", "opened_by", "closed_by"
    )
    if year:
        sessions = sessions.filter(
            opened_at__date__range=(year.start_date, year.end_date)
        )
    sessions = sessions.order_by("-opened_at")
    open_session = CashSession.objects.filter(
        school=school, status=CashSessionStatus.OPEN
    ).select_related("site", "opened_by").first()
    open_summary = cash_session_summary(open_session) if open_session else None
    return render(
        request,
        "finance/cash_home.html",
        {
            "school": school,
            "years": years,
            "selected_year": year,
            "sessions": sessions[:30],
            "open_session": open_session,
            "open_summary": open_summary,
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def cash_open(request, org_slug, school_code):
    _ensure_finance_management(request)
    school = request.school
    if CashSession.objects.filter(
        school=school, status=CashSessionStatus.OPEN
    ).exists():
        messages.info(request, "Une caisse est déjà ouverte.")
        return redirect(_finance_url(school, "finance_cash_home"))
    form = CashSessionOpenForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        cleaned = form.cleaned_data
        try:
            session = open_cash_session(
                school,
                user=request.user,
                opening_float=cleaned["opening_float"],
                site=cleaned.get("site"),
                notes=cleaned.get("notes", ""),
            )
        except ValidationError as error:
            _add_validation_error(form, error)
        else:
            messages.success(request, "Caisse ouverte.")
            return redirect(
                _finance_url(
                    school, "finance_cash_detail", session_id=session.pk
                )
            )
    context = _form_context(
        school,
        "Ouvrir la caisse",
        "Le fonds de caisse correspond aux espèces déjà présentes avant "
        "les encaissements de la journée.",
        _finance_url(school, "finance_cash_home"),
    )
    context["form"] = form
    context["submit_label"] = "Ouvrir la caisse"
    return render(request, "generic_form.html", context)


@login_required
@tenant_scoped_view
def cash_detail(request, org_slug, school_code, session_id):
    _ensure_finance_view(request)
    school = request.school
    session = get_object_or_404(
        CashSession.objects.filter(school=school).select_related(
            "site", "opened_by", "closed_by"
        ),
        pk=session_id,
        school=school,
    )
    summary = cash_session_summary(session)
    return render(
        request,
        "finance/cash_detail.html",
        {
            "school": school,
            "session": session,
            "summary": summary,
            "payments": summary["payments"],
            "can_manage_finance": user_can_manage_finance(
                request.user, school
            ),
        },
    )


@login_required
@tenant_scoped_view
def cash_close(request, org_slug, school_code, session_id):
    _ensure_finance_management(request)
    school = request.school
    session = get_object_or_404(
        CashSession.objects.filter(school=school).select_related(
            "site", "opened_by"
        ),
        pk=session_id,
        school=school,
    )
    if session.status != CashSessionStatus.OPEN:
        messages.info(request, "Cette caisse est déjà clôturée.")
        return redirect(
            _finance_url(
                school, "finance_cash_detail", session_id=session.pk
            )
        )
    summary = cash_session_summary(session)
    form = CashSessionCloseForm(
        request.POST or None,
        initial={"counted_cash": summary["expected_cash"]},
    )
    if request.method == "POST" and form.is_valid():
        try:
            close_cash_session(
                session,
                request.user,
                form.cleaned_data["counted_cash"],
                form.cleaned_data.get("notes", ""),
            )
        except ValidationError as error:
            _add_validation_error(form, error)
        else:
            messages.success(request, "Caisse clôturée.")
            return redirect(
                _finance_url(
                    school, "finance_cash_detail", session_id=session.pk
                )
            )
    return render(
        request,
        "finance/cash_close.html",
        {
            "school": school,
            "session": session,
            "summary": summary,
            "form": form,
            "cancel_url": _finance_url(
                school, "finance_cash_detail", session_id=session.pk
            ),
        },
    )


# ---------------------------------------------------------------------------
# Export comptable
# ---------------------------------------------------------------------------


@login_required
@tenant_scoped_view
def finance_export(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    form = FinanceExportForm(request.GET or None, school=school)
    if form.is_valid():
        return redirect(
            _finance_url(school, "finance_export_download")
            + f"?academic_year={form.cleaned_data['academic_year'].pk}"
        )
    return render(
        request,
        "finance/export.html",
        {"school": school, "form": form},
    )


@login_required
@tenant_scoped_view
def finance_export_download(request, org_slug, school_code):
    _ensure_finance_view(request)
    school = request.school
    try:
        year = get_object_or_404(
            AcademicYear,
            pk=request.GET.get("academic_year"),
            school=school,
        )
    except (ValidationError, ValueError) as error:
        raise Http404("Année scolaire invalide.") from error
    workbook = build_finance_workbook(school, year)
    filename = (
        slugify(f"finances-{school.code}-{year.name}") or "finances"
    ) + ".xlsx"
    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response
