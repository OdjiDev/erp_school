from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.students.models import Enrollment, EnrollmentStatus

from .models import (
    CashSession,
    CashSessionStatus,
    Discount,
    DocumentSequence,
    Fee,
    Invoice,
    InvoiceDiscount,
    InvoiceInstallment,
    InvoiceLine,
    InvoiceStatus,
    Payment,
    PaymentAllocation,
    PaymentMethod,
    PaymentPlan,
    PaymentPlanLine,
)

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def quantize(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def next_document_number(school, academic_year, document_type):
    """Numéro continu par école et année, sûr en concurrence."""
    prefix = {
        DocumentSequence.DOCUMENT_INVOICE: "FAC",
        DocumentSequence.DOCUMENT_RECEIPT: "REC",
    }[document_type]
    with transaction.atomic():
        sequence, _ = DocumentSequence.all_objects.select_for_update().get_or_create(
            school=school,
            academic_year=academic_year,
            document_type=document_type,
            defaults={"last_value": 0},
        )
        sequence.last_value += 1
        sequence.save(update_fields=["last_value", "updated_at"])
    year = academic_year.start_date.year
    return f"{prefix}-{year}-{sequence.last_value:05d}"


def resolve_payment_plan(school, academic_year, level, series):
    """Choisit l'échéancier le plus spécifique, sinon l'échéancier général."""
    plans = list(
        PaymentPlan.all_objects.filter(
            school=school, academic_year=academic_year, is_active=True
        )
        .filter(Q(level__isnull=True) | Q(level=level))
        .filter(Q(series__isnull=True) | Q(series=series))
        .prefetch_related("lines")
    )
    if not plans:
        return None

    def priority(plan):
        if plan.level_id and plan.series_id:
            return 0
        if plan.level_id:
            return 1
        if not plan.level_id and not plan.series_id:
            return 2
        return 3

    plans.sort(key=lambda plan: (priority(plan), plan.created_at))
    return plans[0]


def matching_fees(school, academic_year, school_class):
    return list(
        Fee.all_objects.filter(
            school=school, academic_year=academic_year, is_active=True
        )
        .filter(
            Q(level__isnull=True) | Q(level_id=school_class.level_id)
        )
        .filter(
            Q(series__isnull=True) | Q(series_id=school_class.series_id)
        )
        .order_by("name")
    )


def _create_installments(invoice, plan, total):
    if total <= 0:
        return
    lines = list(
        PaymentPlanLine.all_objects.filter(plan=plan).order_by(
            "sequence", "due_date"
        )
    )
    if not lines:
        raise ValidationError("L'échéancier ne contient aucune échéance.")
    percentage_total = sum((line.percentage for line in lines), ZERO)
    if percentage_total != Decimal("100.00"):
        raise ValidationError(
            "Le total des pourcentages de l'échéancier doit être égal à 100 %."
        )

    remaining = total
    for index, plan_line in enumerate(lines):
        if index == len(lines) - 1:
            amount = remaining
        else:
            amount = quantize(total * plan_line.percentage / Decimal("100"))
            amount = min(amount, remaining)
        if amount <= 0:
            continue
        installment = InvoiceInstallment(
            invoice=invoice,
            sequence=index + 1,
            label=plan_line.label,
            due_date=plan_line.due_date,
            amount=amount,
        )
        installment.full_clean()
        installment.save()
        remaining -= amount
    if remaining > 0:
        raise ValidationError(
            "L'échéancier ne couvre pas la totalité de la facture."
        )


def generate_invoice_for_enrollment(
    enrollment, user=None, payment_plan=None, issue_date=None, notes=""
):
    """Crée une facture complète pour une inscription, de façon idempotente."""
    if enrollment.status != EnrollmentStatus.ACTIVE:
        raise ValidationError(
            f"L'inscription de {enrollment.student.full_name} n'est pas active."
        )
    existing = (
        Invoice.all_objects.filter(
            school=enrollment.school,
            academic_year=enrollment.academic_year,
            student=enrollment.student,
        )
        .exclude(status=InvoiceStatus.CANCELLED)
        .first()
    )
    if existing is not None:
        return existing, False

    school_class = enrollment.school_class
    fees = matching_fees(
        enrollment.school, enrollment.academic_year, school_class
    )
    if not fees:
        raise ValidationError(
            f"Aucun frais actif ne correspond à la classe "
            f"{school_class.display_name}."
        )

    plan = payment_plan or resolve_payment_plan(
        enrollment.school,
        enrollment.academic_year,
        school_class.level,
        school_class.series,
    )
    if plan is None:
        raise ValidationError(
            "Aucun échéancier actif ne correspond à cette classe. "
            "Créez un échéancier avant de facturer."
        )
    if plan.school_id != enrollment.school_id:
        raise ValidationError("L'échéancier appartient à une autre école.")
    plan_lines = list(
        PaymentPlanLine.all_objects.filter(plan=plan).order_by(
            "sequence", "due_date"
        )
    )
    if not plan_lines:
        raise ValidationError("L'échéancier sélectionné ne contient aucune échéance.")

    issue_date = issue_date or date.today()
    due_date = max(line.due_date for line in plan_lines)
    if due_date < issue_date:
        due_date = issue_date

    with transaction.atomic():
        invoice = Invoice(
            school=enrollment.school,
            academic_year=enrollment.academic_year,
            student=enrollment.student,
            enrollment=enrollment,
            payment_plan=plan,
            number=next_document_number(
                enrollment.school,
                enrollment.academic_year,
                DocumentSequence.DOCUMENT_INVOICE,
            ),
            issue_date=issue_date,
            due_date=due_date,
            status=InvoiceStatus.ISSUED,
            created_by=user,
            notes=notes,
        )
        invoice.full_clean()
        invoice.save()

        subtotal = ZERO
        for fee in fees:
            line = InvoiceLine(
                invoice=invoice,
                fee=fee,
                description=fee.name,
                amount=fee.amount,
            )
            line.full_clean()
            line.save()
            subtotal += fee.amount

        remaining = subtotal
        discount_total = ZERO
        discounts = Discount.all_objects.filter(
            school=enrollment.school,
            academic_year=enrollment.academic_year,
            student=enrollment.student,
            is_active=True,
        ).order_by("label")
        for discount in discounts:
            amount = quantize(discount.compute_amount(subtotal))
            amount = min(amount, remaining)
            if amount <= 0:
                continue
            invoice_discount = InvoiceDiscount(
                invoice=invoice,
                discount=discount,
                label=discount.label,
                kind=discount.kind,
                value=discount.value,
                amount=amount,
            )
            invoice_discount.full_clean()
            invoice_discount.save()
            discount_total += amount
            remaining -= amount

        total = max(subtotal - discount_total, ZERO)
        _create_installments(invoice, plan, total)

        invoice.subtotal = subtotal
        invoice.discount_total = discount_total
        invoice.total = total
        invoice.status = InvoiceStatus.PAID if total == 0 else InvoiceStatus.ISSUED
        invoice.save(
            update_fields=[
                "subtotal",
                "discount_total",
                "total",
                "status",
                "updated_at",
            ]
        )
    return invoice, True


@transaction.atomic
def generate_invoices_for_class(
    school_class, user=None, payment_plan=None, issue_date=None
):
    """Facture toute une classe. Une erreur annule le lot complet."""
    enrollments = list(
        Enrollment.all_objects.filter(
            school=school_class.school,
            academic_year=school_class.academic_year,
            school_class=school_class,
            status=EnrollmentStatus.ACTIVE,
        )
        .select_related("student", "school_class", "academic_year", "school")
        .order_by("student__last_name", "student__first_name")
    )
    if not enrollments:
        raise ValidationError(
            "Cette classe ne contient aucun élève actif à facturer."
        )

    created = []
    skipped = []
    for enrollment in enrollments:
        invoice, was_created = generate_invoice_for_enrollment(
            enrollment,
            user=user,
            payment_plan=payment_plan,
            issue_date=issue_date,
        )
        if was_created:
            created.append(invoice)
        else:
            skipped.append(invoice)
    return created, skipped


def recalculate_invoice(invoice):
    """Recalcule les totaux et le statut depuis les lignes et paiements."""
    subtotal = sum(
        (
            line.amount
            for line in InvoiceLine.all_objects.filter(invoice=invoice)
        ),
        ZERO,
    )
    discount_total = sum(
        (
            discount.amount
            for discount in InvoiceDiscount.all_objects.filter(
                invoice=invoice
            )
        ),
        ZERO,
    )
    total = max(subtotal - discount_total, ZERO)
    paid_total = sum(
        (
            payment.amount
            for payment in Payment.all_objects.filter(
                invoice=invoice, cancelled_at__isnull=True
            )
        ),
        ZERO,
    )

    invoice.subtotal = subtotal
    invoice.discount_total = discount_total
    invoice.total = total
    invoice.paid_total = paid_total
    if invoice.status != InvoiceStatus.CANCELLED:
        if total == 0:
            invoice.status = InvoiceStatus.PAID
        elif paid_total <= 0:
            invoice.status = InvoiceStatus.ISSUED
        elif paid_total < total:
            invoice.status = InvoiceStatus.PARTIAL
        else:
            invoice.status = InvoiceStatus.PAID
    invoice.save(
        update_fields=[
            "subtotal",
            "discount_total",
            "total",
            "paid_total",
            "status",
            "updated_at",
        ]
    )
    return invoice


def _allocate_payment(payment):
    remaining = payment.amount
    installments = InvoiceInstallment.all_objects.select_for_update().filter(
        invoice=payment.invoice
    ).order_by("sequence", "due_date")
    for installment in installments:
        available = installment.amount - installment.paid_amount
        if available <= 0:
            continue
        allocated = min(available, remaining)
        PaymentAllocation.all_objects.create(
            payment=payment,
            installment=installment,
            amount=allocated,
        )
        installment.paid_amount += allocated
        installment.save(update_fields=["paid_amount", "updated_at"])
        remaining -= allocated
        if remaining <= 0:
            break
    if remaining > 0:
        raise ValidationError(
            "Le montant du paiement dépasse l'échéancier de la facture."
        )


def record_payment(
    invoice,
    amount,
    method,
    user=None,
    reference="",
    paid_at=None,
    notes="",
):
    """Encaisse un paiement, l'affecte aux échéances et met à jour la facture."""
    amount = quantize(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Le montant doit être positif."})

    with transaction.atomic():
        invoice = Invoice.all_objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ValidationError("Impossible d'encaisser une facture annulée.")
        if amount > invoice.balance:
            raise ValidationError(
                {
                    "amount": (
                        "Le montant dépasse le solde de la facture "
                        f"({invoice.balance} FCFA)."
                    )
                }
            )

        cash_session = None
        if method == PaymentMethod.CASH:
            cash_session = (
                CashSession.all_objects.select_for_update()
                .filter(
                    school=invoice.school,
                    status=CashSessionStatus.OPEN,
                )
                .first()
            )
            if cash_session is None:
                raise ValidationError(
                    "Aucune caisse n'est ouverte. Ouvrez la caisse avant "
                    "d'encaisser en espèces."
                )

        payment = Payment(
            school=invoice.school,
            invoice=invoice,
            receipt_number=next_document_number(
                invoice.school,
                invoice.academic_year,
                DocumentSequence.DOCUMENT_RECEIPT,
            ),
            amount=amount,
            method=method,
            reference=(reference or "").strip(),
            paid_at=paid_at or date.today(),
            received_by=user,
            cash_session=cash_session,
            notes=notes or "",
        )
        payment.full_clean()
        payment.save()

        _allocate_payment(payment)
        recalculate_invoice(invoice)
    return payment


def _recalculate_installments(invoice):
    for installment in InvoiceInstallment.all_objects.filter(invoice=invoice):
        paid = (
            PaymentAllocation.all_objects.filter(
                installment=installment,
                payment__cancelled_at__isnull=True,
            ).aggregate(total=Sum("amount"))["total"]
            or ZERO
        )
        installment.paid_amount = min(paid, installment.amount)
        installment.save(update_fields=["paid_amount", "updated_at"])


def cancel_payment(payment, user, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Le motif d'annulation est obligatoire.")
    with transaction.atomic():
        payment = Payment.all_objects.select_for_update().get(pk=payment.pk)
        if payment.is_cancelled:
            raise ValidationError("Ce paiement est déjà annulé.")
        if payment.cash_session_id:
            session = CashSession.all_objects.get(pk=payment.cash_session_id)
            if session.status == CashSessionStatus.CLOSED:
                raise ValidationError(
                    "La caisse de ce paiement est clôturée. "
                    "Le paiement ne peut plus être annulé."
                )
        payment.cancelled_at = timezone.now()
        payment.cancelled_by = user
        payment.cancellation_reason = reason
        payment.save(
            update_fields=[
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
                "updated_at",
            ]
        )
        PaymentAllocation.all_objects.filter(payment=payment).delete()
        invoice = payment.invoice
        _recalculate_installments(invoice)
        recalculate_invoice(invoice)
    return payment


def cancel_invoice(invoice, user, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Le motif d'annulation est obligatoire.")
    with transaction.atomic():
        invoice = Invoice.all_objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ValidationError("Cette facture est déjà annulée.")
        if Payment.all_objects.filter(
            invoice=invoice, cancelled_at__isnull=True
        ).exists():
            raise ValidationError(
                "Impossible d'annuler une facture qui comporte des paiements."
            )
        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.cancelled_by = user
        invoice.cancellation_reason = reason
        invoice.save(
            update_fields=[
                "status",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
                "updated_at",
            ]
        )
    return invoice


def overdue_installments(
    school, academic_year=None, school_class=None, as_of=None
):
    as_of = as_of or date.today()
    queryset = InvoiceInstallment.all_objects.filter(
        invoice__school=school,
        invoice__status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIAL],
        due_date__lt=as_of,
        amount__gt=F("paid_amount"),
    ).select_related(
        "invoice",
        "invoice__student",
        "invoice__enrollment__school_class",
    )
    if academic_year is not None:
        queryset = queryset.filter(invoice__academic_year=academic_year)
    if school_class is not None:
        queryset = queryset.filter(
            invoice__enrollment__school_class=school_class
        )
    return queryset.order_by("due_date", "invoice__student__last_name")


def open_cash_session(
    school, user=None, opening_float=ZERO, site=None, notes=""
):
    opening_float = quantize(opening_float)
    if opening_float < 0:
        raise ValidationError("Le fonds de caisse ne peut pas être négatif.")
    if site is not None and site.school_id != school.id:
        raise ValidationError("Le site appartient à une autre école.")
    with transaction.atomic():
        if CashSession.all_objects.select_for_update().filter(
            school=school, status=CashSessionStatus.OPEN
        ).exists():
            raise ValidationError("Une caisse est déjà ouverte pour cette école.")
        session = CashSession(
            school=school,
            site=site,
            opened_by=user,
            opening_float=opening_float,
            notes=notes or "",
        )
        session.full_clean()
        try:
            session.save()
        except IntegrityError as exc:
            raise ValidationError(
                "Une caisse est déjà ouverte pour cette école."
            ) from exc
    return session


def cash_session_summary(session):
    payments = Payment.all_objects.filter(
        cash_session=session,
        method=PaymentMethod.CASH,
        cancelled_at__isnull=True,
    )
    total = payments.aggregate(total=Sum("amount"))["total"] or ZERO
    return {
        "payments": payments.select_related(
            "invoice", "invoice__student"
        ).order_by("-paid_at", "-created_at"),
        "count": payments.count(),
        "cash_total": total,
        "expected_cash": session.opening_float + total,
    }


def close_cash_session(session, user, counted_cash, notes=""):
    counted_cash = quantize(counted_cash)
    if counted_cash < 0:
        raise ValidationError("Le montant compté ne peut pas être négatif.")
    with transaction.atomic():
        session = CashSession.all_objects.select_for_update().get(pk=session.pk)
        if session.status != CashSessionStatus.OPEN:
            raise ValidationError("Cette caisse est déjà clôturée.")
        summary = cash_session_summary(session)
        expected = summary["expected_cash"]
        session.expected_cash = expected
        session.counted_cash = counted_cash
        session.difference = counted_cash - expected
        session.status = CashSessionStatus.CLOSED
        session.closed_by = user
        session.closed_at = timezone.now()
        if notes:
            session.notes = (
                f"{session.notes}\n{notes}".strip()
                if session.notes
                else notes
            )
        session.save(
            update_fields=[
                "expected_cash",
                "counted_cash",
                "difference",
                "status",
                "closed_by",
                "closed_at",
                "notes",
                "updated_at",
            ]
        )
    return session
