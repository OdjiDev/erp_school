from datetime import date
from decimal import Decimal

from django.db.models import Prefetch
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from apps.tenancy.excel import add_headers

from .models import (
    CashSession,
    CashSessionStatus,
    Invoice,
    InvoiceInstallment,
    InvoiceStatus,
    Payment,
)
from .services import overdue_installments

ZERO = Decimal("0.00")
MONEY_FORMAT = '#,##0.00 "FCFA"'
DATE_FORMAT = "DD/MM/YYYY"


def _money(value):
    return Decimal(value or 0)


def _write_totals(sheet, row, label, values):
    cell = sheet.cell(row=row, column=1, value=label)
    cell.font = Font(bold=True)
    for column, value in values.items():
        amount_cell = sheet.cell(row=row, column=column, value=value)
        amount_cell.font = Font(bold=True)
        amount_cell.number_format = MONEY_FORMAT


def build_finance_workbook(school, academic_year):
    """Classeur comptable complet pour une école et une année scolaire."""
    invoices = list(
        Invoice.all_objects.filter(school=school, academic_year=academic_year)
        .select_related(
            "student", "enrollment__school_class", "enrollment__school_class__level"
        )
        .prefetch_related(
            Prefetch(
                "installments",
                queryset=InvoiceInstallment.all_objects.all(),
            )
        )
        .order_by("number")
    )
    payments = list(
        Payment.all_objects.filter(
            school=school, invoice__academic_year=academic_year
        )
        .select_related("invoice__student", "cash_session")
        .order_by("paid_at", "receipt_number")
    )
    overdue = list(
        overdue_installments(school, academic_year=academic_year)
    )
    sessions = list(
        CashSession.all_objects.filter(
            school=school,
            opened_at__date__range=(
                academic_year.start_date,
                academic_year.end_date,
            ),
        ).order_by("opened_at")
    )

    active_invoices = [
        invoice for invoice in invoices if invoice.status != InvoiceStatus.CANCELLED
    ]
    active_payments = [
        payment for payment in payments if not payment.is_cancelled
    ]
    billed = sum((_money(invoice.total) for invoice in active_invoices), ZERO)
    discounted = sum(
        (_money(invoice.discount_total) for invoice in active_invoices), ZERO
    )
    collected = sum((_money(payment.amount) for payment in active_payments), ZERO)
    outstanding = sum(
        (_money(invoice.balance) for invoice in active_invoices), ZERO
    )
    overdue_total = sum(
        (_money(installment.balance) for installment in overdue), ZERO
    )

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Synthèse"
    summary.sheet_view.showGridLines = False
    summary.column_dimensions["A"].width = 42
    summary.column_dimensions["B"].width = 26
    summary["A1"] = f"Export comptable — {school.name}"
    summary["A1"].font = Font(bold=True, size=14, color="0B2E24")
    summary["A2"] = (
        f"École {school.code} · Année {academic_year.name} · "
        f"Édité le {date.today():%d/%m/%Y}"
    )
    summary["A2"].font = Font(color="52606D")
    summary_rows = [
        ("Factures émises (hors annulées)", len(active_invoices)),
        ("Total facturé", billed),
        ("Total des remises", discounted),
        ("Total encaissé (hors annulations)", collected),
        ("Solde restant à recouvrer", outstanding),
        ("Impayés échus à ce jour", overdue_total),
        ("Nombre d'encaissements", len(active_payments)),
        ("Sessions de caisse", len(sessions)),
    ]
    for index, (label, value) in enumerate(summary_rows, start=4):
        summary.cell(row=index, column=1, value=label)
        cell = summary.cell(row=index, column=2, value=value)
        if isinstance(value, Decimal):
            cell.number_format = MONEY_FORMAT
        cell.alignment = Alignment(horizontal="right")

    factures = workbook.create_sheet("Factures")
    add_headers(
        factures,
        [
            "Numéro",
            "Date",
            "Élève",
            "Matricule",
            "Classe",
            "Statut",
            "Sous-total",
            "Remises",
            "Net à payer",
            "Encaissé",
            "Solde",
            "Échéance",
        ],
        [18, 12, 28, 16, 22, 20, 16, 16, 16, 16, 16, 12],
    )
    for invoice in invoices:
        student = invoice.student
        school_class = (
            invoice.enrollment.school_class
            if invoice.enrollment_id
            else None
        )
        factures.append(
            [
                invoice.number,
                invoice.issue_date,
                f"{student.last_name} {student.first_name}",
                student.matricule,
                school_class.display_name if school_class else "",
                invoice.get_status_display(),
                _money(invoice.subtotal),
                _money(invoice.discount_total),
                _money(invoice.total),
                _money(invoice.paid_total),
                _money(invoice.balance),
                invoice.due_date,
            ]
        )
        for column in range(7, 12):
            factures.cell(row=factures.max_row, column=column).number_format = (
                MONEY_FORMAT
            )
        for column in (2, 12):
            factures.cell(row=factures.max_row, column=column).number_format = (
                DATE_FORMAT
            )
    _write_totals(
        factures,
        factures.max_row + 2,
        "Totaux (toutes factures)",
        {
            7: sum((_money(i.subtotal) for i in invoices), ZERO),
            8: sum((_money(i.discount_total) for i in invoices), ZERO),
            9: sum((_money(i.total) for i in invoices), ZERO),
            10: sum((_money(i.paid_total) for i in invoices), ZERO),
            11: sum((_money(i.balance) for i in invoices), ZERO),
        },
    )

    encaissements = workbook.create_sheet("Encaissements")
    add_headers(
        encaissements,
        [
            "Reçu",
            "Date",
            "Élève",
            "Facture",
            "Montant",
            "Mode",
            "Référence",
            "Caisse",
            "Annulé",
            "Motif d'annulation",
        ],
        [18, 12, 28, 18, 16, 20, 24, 22, 10, 36],
    )
    for payment in payments:
        encaissements.append(
            [
                payment.receipt_number,
                payment.paid_at,
                (
                    f"{payment.invoice.student.last_name} "
                    f"{payment.invoice.student.first_name}"
                ),
                payment.invoice.number,
                _money(payment.amount),
                payment.get_method_display(),
                payment.reference,
                str(payment.cash_session) if payment.cash_session_id else "",
                "Oui" if payment.is_cancelled else "Non",
                payment.cancellation_reason,
            ]
        )
        encaissements.cell(
            row=encaissements.max_row, column=5
        ).number_format = MONEY_FORMAT
        encaissements.cell(
            row=encaissements.max_row, column=2
        ).number_format = DATE_FORMAT
    _write_totals(
        encaissements,
        encaissements.max_row + 2,
        "Total encaissé (hors annulations)",
        {5: collected},
    )

    impayes = workbook.create_sheet("Impayes")
    add_headers(
        impayes,
        [
            "Facture",
            "Élève",
            "Matricule",
            "Classe",
            "Échéance",
            "Libellé",
            "Montant dû",
            "Déjà payé",
            "Solde",
            "Jours de retard",
        ],
        [18, 28, 16, 22, 12, 24, 16, 16, 16, 14],
    )
    today = date.today()
    for installment in overdue:
        invoice = installment.invoice
        school_class = (
            invoice.enrollment.school_class if invoice.enrollment_id else None
        )
        impayes.append(
            [
                invoice.number,
                f"{invoice.student.last_name} {invoice.student.first_name}",
                invoice.student.matricule,
                school_class.display_name if school_class else "",
                installment.due_date,
                installment.label,
                _money(installment.amount),
                _money(installment.paid_amount),
                _money(installment.balance),
                max((today - installment.due_date).days, 0),
            ]
        )
        for column in (7, 8, 9):
            impayes.cell(
                row=impayes.max_row, column=column
            ).number_format = MONEY_FORMAT
        impayes.cell(
            row=impayes.max_row, column=5
        ).number_format = DATE_FORMAT
    _write_totals(
        impayes,
        impayes.max_row + 2,
        "Total des impayés échus",
        {9: overdue_total},
    )

    caisse = workbook.create_sheet("Caisse")
    add_headers(
        caisse,
        [
            "Ouverte le",
            "Par",
            "Site",
            "Fonds initial",
            "Espèces encaissées",
            "Attendu",
            "Compté",
            "Écart",
            "Statut",
            "Clôturée le",
        ],
        [20, 24, 24, 16, 18, 16, 16, 16, 14, 20],
    )
    for session in sessions:
        cash_payments = [
            payment
            for payment in active_payments
            if payment.cash_session_id == session.pk
        ]
        cash_total = sum(
            (_money(payment.amount) for payment in cash_payments), ZERO
        )
        expected = _money(session.expected_cash)
        if session.status == CashSessionStatus.OPEN:
            expected = _money(session.opening_float) + cash_total
        caisse.append(
            [
                session.opened_at.strftime("%d/%m/%Y %H:%M"),
                session.opened_by.get_username() if session.opened_by else "",
                session.site.name if session.site_id else "Caisse principale",
                _money(session.opening_float),
                cash_total,
                expected,
                _money(session.counted_cash) if session.counted_cash is not None else None,
                _money(session.difference) if session.difference is not None else None,
                session.get_status_display(),
                (
                    session.closed_at.strftime("%d/%m/%Y %H:%M")
                    if session.closed_at
                    else ""
                ),
            ]
        )
        for column in (4, 5, 6, 7, 8):
            caisse.cell(row=caisse.max_row, column=column).number_format = (
                MONEY_FORMAT
            )

    for sheet in (factures, encaissements, impayes, caisse):
        sheet.freeze_panes = "A2"
        for column in range(1, sheet.max_column + 1):
            sheet.cell(row=1, column=column).alignment = Alignment(
                horizontal="center", vertical="center"
            )
        sheet.column_dimensions[get_column_letter(1)].width = max(
            sheet.column_dimensions[get_column_letter(1)].width or 12, 16
        )

    return workbook
