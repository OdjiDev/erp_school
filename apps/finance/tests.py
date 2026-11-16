from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from apps.academics.models import AcademicYear, Level, SchoolClass, Series
from apps.common.tenancy import tenant_scope
from apps.students.models import Enrollment, EnrollmentStatus, Student
from apps.tenancy.models import Membership, Organization, Role, School

from .exports import build_finance_workbook
from .models import (
    CashSession,
    CashSessionStatus,
    Discount,
    DiscountKind,
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
from .services import (
    cancel_invoice,
    cancel_payment,
    cash_session_summary,
    close_cash_session,
    generate_invoice_for_enrollment,
    open_cash_session,
    overdue_installments,
    record_payment,
)

User = get_user_model()


class FinanceTestBase(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Organisation Finances")
        self.other_org = Organization.all_objects.create(name="Autre Organisation")
        self.data = self._create_school("FIN", self.org, "Lycée Finance")
        self.other_data = self._create_school(
            "OTH", self.other_org, "Lycée Autre"
        )
        self._add_finance(self.data, with_discount=True)
        self._add_finance(self.other_data, with_discount=False)

        self.school = self.data["school"]
        self.year = self.data["year"]
        self.level = self.data["level"]
        self.series = self.data["series"]
        self.school_class = self.data["school_class"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]

    def _create_school(self, code, organization, name):
        school = School.all_objects.create(
            organization=organization, name=name, code=code
        )
        year = AcademicYear.all_objects.create(
            school=school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
        )
        level = Level.all_objects.create(
            school=school, code="11", name="11ème", order=2
        )
        series = Series.all_objects.create(
            level=level, code="LET", name="Lettres"
        )
        school_class = SchoolClass.all_objects.create(
            school=school,
            academic_year=year,
            level=level,
            series=series,
            section="A",
            capacity=100,
        )
        student = Student.all_objects.create(
            school=school,
            matricule=f"{code}-001",
            first_name="Awa",
            last_name="Traoré",
        )
        enrollment = Enrollment.all_objects.create(
            school=school,
            student=student,
            academic_year=year,
            school_class=school_class,
            status=EnrollmentStatus.ACTIVE,
        )
        other_level = Level.all_objects.create(
            school=school, code="10", name="10ème", order=1
        )
        other_series = Series.all_objects.create(
            level=other_level, code="CG", name="Comptabilité et Gestion"
        )
        return {
            "school": school,
            "year": year,
            "level": level,
            "series": series,
            "school_class": school_class,
            "student": student,
            "enrollment": enrollment,
            "other_level": other_level,
            "other_series": other_series,
        }

    def _add_finance(self, data, with_discount):
        school = data["school"]
        year = data["year"]
        Fee.all_objects.create(
            school=school,
            academic_year=year,
            name="Frais d'inscription",
            amount=Decimal("25000.00"),
        )
        Fee.all_objects.create(
            school=school,
            academic_year=year,
            level=data["level"],
            name="Frais de scolarité",
            amount=Decimal("100000.00"),
        )
        Fee.all_objects.create(
            school=school,
            academic_year=year,
            level=data["other_level"],
            name="Frais de scolarité",
            amount=Decimal("999000.00"),
        )
        plan = PaymentPlan.all_objects.create(
            school=school,
            academic_year=year,
            name="Paiement en 3 tranches",
        )
        PaymentPlanLine.all_objects.create(
            plan=plan,
            sequence=1,
            label="1ère tranche",
            due_date=date(2026, 10, 15),
            percentage=Decimal("40.00"),
        )
        PaymentPlanLine.all_objects.create(
            plan=plan,
            sequence=2,
            label="2ème tranche",
            due_date=date(2027, 1, 15),
            percentage=Decimal("30.00"),
        )
        PaymentPlanLine.all_objects.create(
            plan=plan,
            sequence=3,
            label="3ème tranche",
            due_date=date(2027, 4, 15),
            percentage=Decimal("30.00"),
        )
        data["plan"] = plan
        if with_discount:
            discount = Discount.all_objects.create(
                school=school,
                academic_year=year,
                student=data["student"],
                label="Bourse d'excellence",
                kind=DiscountKind.PERCENTAGE,
                value=Decimal("10.00"),
            )
            data["discount"] = discount

    def generate_invoice(self, data=None):
        data = data or self.data
        return generate_invoice_for_enrollment(
            data["enrollment"], issue_date=data["year"].start_date
        )[0]

    def school_url(self, name, **kwargs):
        return reverse(
            f"school:{name}",
            kwargs={
                "org_slug": self.school.organization.slug,
                "school_code": self.school.code,
                **kwargs,
            },
        )


class InvoiceGenerationTests(FinanceTestBase):
    def test_invoice_applies_matching_fees_and_active_discount(self):
        invoice, created = generate_invoice_for_enrollment(
            self.enrollment, issue_date=self.year.start_date
        )

        self.assertTrue(created)
        self.assertEqual(invoice.number, "FAC-2026-00001")
        self.assertEqual(invoice.subtotal, Decimal("125000.00"))
        self.assertEqual(invoice.discount_total, Decimal("12500.00"))
        self.assertEqual(invoice.total, Decimal("112500.00"))
        self.assertEqual(invoice.paid_total, Decimal("0.00"))
        self.assertEqual(invoice.status, InvoiceStatus.ISSUED)
        self.assertEqual(
            InvoiceLine.all_objects.filter(invoice=invoice).count(), 2
        )
        self.assertEqual(
            InvoiceDiscount.all_objects.filter(invoice=invoice).count(), 1
        )
        self.assertEqual(
            sum(
                (
                    line.amount
                    for line in InvoiceInstallment.all_objects.filter(
                        invoice=invoice
                    )
                ),
                Decimal("0.00"),
            ),
            invoice.total,
        )
        self.assertFalse(
            InvoiceLine.all_objects.filter(
                invoice=invoice, description="Frais de scolarité"
            )
            .filter(amount=Decimal("999000.00"))
            .exists()
        )

    def test_invoice_generation_is_idempotent(self):
        first, created = generate_invoice_for_enrollment(self.enrollment)
        second, created_again = generate_invoice_for_enrollment(self.enrollment)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Invoice.all_objects.filter(
                school=self.school, academic_year=self.year
            ).count(),
            1,
        )

    def test_invoice_numbers_are_continuous_per_school_and_year(self):
        first = self.generate_invoice()
        second_student = Student.all_objects.create(
            school=self.school,
            matricule="FIN-002",
            first_name="Ibrahim",
            last_name="Diarra",
        )
        second_enrollment = Enrollment.all_objects.create(
            school=self.school,
            student=second_student,
            academic_year=self.year,
            school_class=self.school_class,
            status=EnrollmentStatus.ACTIVE,
        )
        second = generate_invoice_for_enrollment(second_enrollment)[0]

        self.assertEqual(first.number, "FAC-2026-00001")
        self.assertEqual(second.number, "FAC-2026-00002")

    def test_inactive_fee_is_ignored(self):
        Fee.all_objects.filter(name="Frais d'inscription").update(
            is_active=False
        )

        invoice = self.generate_invoice()

        self.assertEqual(invoice.subtotal, Decimal("100000.00"))
        self.assertEqual(
            InvoiceLine.all_objects.filter(invoice=invoice).count(), 1
        )

    def test_full_discount_marks_invoice_as_paid(self):
        Discount.all_objects.create(
            school=self.school,
            academic_year=self.year,
            student=self.student,
            label="Remise exceptionnelle",
            kind=DiscountKind.FIXED,
            value=Decimal("999999.00"),
        )

        invoice = self.generate_invoice()

        self.assertEqual(invoice.total, Decimal("0.00"))
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(
            InvoiceInstallment.all_objects.filter(invoice=invoice).count(), 0
        )

    def test_fee_from_another_level_is_not_applied(self):
        invoice = self.generate_invoice()

        self.assertEqual(invoice.subtotal, Decimal("125000.00"))
        self.assertNotEqual(invoice.subtotal, Decimal("1124000.00"))

    def test_tenant_scope_hides_invoices_outside_school(self):
        self.generate_invoice()
        other_invoice = self.generate_invoice(self.other_data)

        self.assertEqual(Invoice.objects.count(), 0)
        with tenant_scope(self.org.id, self.school.id):
            self.assertEqual(Invoice.objects.count(), 1)
            self.assertNotEqual(
                Invoice.objects.first().pk, other_invoice.pk
            )


class PaymentTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.invoice = self.generate_invoice()

    def test_partial_payment_creates_receipt_and_allocations(self):
        session = open_cash_session(
            self.school, opening_float=Decimal("10000.00")
        )

        payment = record_payment(
            self.invoice,
            amount=Decimal("50000.00"),
            method=PaymentMethod.CASH,
            reference="TM-001",
        )

        self.invoice.refresh_from_db()
        self.assertEqual(payment.receipt_number, "REC-2026-00001")
        self.assertEqual(payment.cash_session_id, session.pk)
        self.assertEqual(payment.amount, Decimal("50000.00"))
        self.assertEqual(self.invoice.paid_total, Decimal("50000.00"))
        self.assertEqual(self.invoice.balance, Decimal("62500.00"))
        self.assertEqual(self.invoice.status, InvoiceStatus.PARTIAL)
        first_installment = InvoiceInstallment.all_objects.get(
            invoice=self.invoice, sequence=1
        )
        second_installment = InvoiceInstallment.all_objects.get(
            invoice=self.invoice, sequence=2
        )
        self.assertEqual(
            first_installment.paid_amount, first_installment.amount
        )
        self.assertEqual(
            second_installment.paid_amount, Decimal("5000.00")
        )
        self.assertEqual(
            PaymentAllocation.all_objects.filter(payment=payment).count(), 2
        )

    def test_full_payment_marks_invoice_as_paid(self):
        open_cash_session(self.school)
        record_payment(
            self.invoice,
            amount=Decimal("50000.00"),
            method=PaymentMethod.CASH,
        )

        self.invoice.refresh_from_db()
        record_payment(
            self.invoice,
            amount=self.invoice.balance,
            method=PaymentMethod.CASH,
        )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_total, self.invoice.total)
        self.assertEqual(self.invoice.status, InvoiceStatus.PAID)
        self.assertTrue(
            all(
                installment.balance == 0
                for installment in InvoiceInstallment.all_objects.filter(
                    invoice=self.invoice
                )
            )
        )

    def test_payment_above_balance_is_rejected(self):
        open_cash_session(self.school)

        with self.assertRaises(ValidationError):
            record_payment(
                self.invoice,
                amount=Decimal("999999.00"),
                method=PaymentMethod.CASH,
            )

        self.assertEqual(
            Payment.all_objects.filter(invoice=self.invoice).count(), 0
        )

    def test_cash_payment_requires_open_cash_session(self):
        with self.assertRaises(ValidationError):
            record_payment(
                self.invoice,
                amount=Decimal("1000.00"),
                method=PaymentMethod.CASH,
            )

        self.assertEqual(
            Payment.all_objects.filter(invoice=self.invoice).count(), 0
        )

    def test_mobile_money_payment_does_not_require_cash_session(self):
        payment = record_payment(
            self.invoice,
            amount=Decimal("1000.00"),
            method=PaymentMethod.ORANGE_MONEY,
            reference="OM-123",
        )

        self.assertIsNone(payment.cash_session_id)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_total, Decimal("1000.00"))

    def test_cancelling_payment_restores_installments_and_balance(self):
        open_cash_session(self.school)
        payment = record_payment(
            self.invoice,
            amount=Decimal("50000.00"),
            method=PaymentMethod.CASH,
        )

        cancel_payment(payment, None, "Erreur de caisse")

        payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertTrue(payment.is_cancelled)
        self.assertEqual(self.invoice.paid_total, Decimal("0.00"))
        self.assertEqual(self.invoice.status, InvoiceStatus.ISSUED)
        self.assertEqual(
            sum(
                (
                    installment.paid_amount
                    for installment in InvoiceInstallment.all_objects.filter(
                        invoice=self.invoice
                    )
                ),
                Decimal("0.00"),
            ),
            Decimal("0.00"),
        )

    def test_payment_cannot_be_cancelled_after_cash_session_close(self):
        session = open_cash_session(self.school)
        payment = record_payment(
            self.invoice,
            amount=Decimal("50000.00"),
            method=PaymentMethod.CASH,
        )
        close_cash_session(
            session, None, counted_cash=session.opening_float + Decimal("50000.00")
        )

        with self.assertRaises(ValidationError):
            cancel_payment(payment, None, "Tentative tardive")

    def test_cash_session_summary_and_difference(self):
        session = open_cash_session(
            self.school, opening_float=Decimal("10000.00")
        )
        record_payment(
            self.invoice,
            amount=Decimal("50000.00"),
            method=PaymentMethod.CASH,
        )
        summary = cash_session_summary(session)
        self.assertEqual(summary["cash_total"], Decimal("50000.00"))
        self.assertEqual(summary["expected_cash"], Decimal("60000.00"))
        self.assertEqual(summary["count"], 1)

        closed = close_cash_session(session, None, counted_cash=Decimal("59000.00"))

        self.assertEqual(closed.status, CashSessionStatus.CLOSED)
        self.assertEqual(closed.expected_cash, Decimal("60000.00"))
        self.assertEqual(closed.counted_cash, Decimal("59000.00"))
        self.assertEqual(closed.difference, Decimal("-1000.00"))

    def test_only_one_cash_session_can_be_open(self):
        open_cash_session(self.school)
        with self.assertRaises(ValidationError):
            open_cash_session(self.school)

    def test_invoice_with_payment_cannot_be_cancelled(self):
        open_cash_session(self.school)
        record_payment(
            self.invoice,
            amount=Decimal("1000.00"),
            method=PaymentMethod.CASH,
        )

        with self.assertRaises(ValidationError):
            cancel_invoice(self.invoice, None, "Erreur de facturation")

    def test_cancelled_invoice_allows_new_invoice(self):
        cancel_invoice(self.invoice, None, "Facture erronée")
        second = self.generate_invoice()

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.CANCELLED)
        self.assertEqual(second.number, "FAC-2026-00002")
        self.assertNotEqual(second.pk, self.invoice.pk)

    def test_overdue_installments_are_reported(self):
        InvoiceInstallment.all_objects.filter(invoice=self.invoice).update(
            due_date=date(2020, 1, 1)
        )

        overdue = list(
            overdue_installments(self.school, academic_year=self.year)
        )

        self.assertEqual(len(overdue), 3)
        self.assertEqual(
            sum((item.balance for item in overdue), Decimal("0.00")),
            self.invoice.total,
        )

    def test_export_workbook_contains_accounting_sheets(self):
        open_cash_session(self.school)
        record_payment(
            self.invoice,
            amount=Decimal("50000.00"),
            method=PaymentMethod.CASH,
        )

        workbook = build_finance_workbook(self.school, self.year)

        self.assertEqual(
            workbook.sheetnames,
            ["Synthèse", "Factures", "Encaissements", "Impayes", "Caisse"],
        )
        self.assertEqual(workbook["Factures"]["A2"].value, self.invoice.number)
        self.assertEqual(
            workbook["Encaissements"]["A2"].value, "REC-2026-00001"
        )


class FinancePermissionTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = self._user("admin-fin", Role.SCHOOL_ADMIN)
        self.accountant = self._user("comptable", Role.ACCOUNTANT)
        self.secretary = self._user("secretaire-fin", Role.SECRETARY)
        self.auditor = self._user("auditeur", Role.AUDITOR)
        self.teacher = self._user("enseignant-fin", Role.TEACHER)

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password="test")
        Membership.all_objects.create(
            user=user,
            organization=self.org,
            school=self.school,
            role=role,
        )
        return user

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.school_url("finance_home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("school:login"), response.url)

    def test_accountant_can_manage_finance(self):
        self.client.force_login(self.accountant)

        home = self.client.get(self.school_url("finance_home"))
        fees = self.client.get(self.school_url("finance_fee_create"))

        self.assertEqual(home.status_code, 200)
        self.assertEqual(fees.status_code, 200)

    def test_secretary_can_view_and_collect_but_not_manage(self):
        invoice = self.generate_invoice()
        open_cash_session(self.school)
        self.client.force_login(self.secretary)

        detail = self.client.get(
            self.school_url(
                "finance_invoice_detail", invoice_id=invoice.pk
            )
        )
        payment = self.client.get(
            self.school_url(
                "finance_payment_create", invoice_id=invoice.pk
            )
        )
        fee_create = self.client.get(self.school_url("finance_fee_create"))
        cash_open = self.client.get(self.school_url("finance_cash_open"))

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(payment.status_code, 200)
        self.assertEqual(fee_create.status_code, 403)
        self.assertEqual(cash_open.status_code, 403)

    def test_auditor_can_consult_but_not_modify(self):
        self.client.force_login(self.auditor)

        home = self.client.get(self.school_url("finance_home"))
        invoices = self.client.get(self.school_url("finance_invoice_list"))
        fee_create = self.client.get(self.school_url("finance_fee_create"))

        self.assertEqual(home.status_code, 200)
        self.assertEqual(invoices.status_code, 200)
        self.assertEqual(fee_create.status_code, 403)

    def test_teacher_cannot_access_finance(self):
        self.client.force_login(self.teacher)
        response = self.client.get(self.school_url("finance_home"))
        self.assertEqual(response.status_code, 403)

    def test_cross_school_invoice_is_not_visible(self):
        other_invoice = self.generate_invoice(self.other_data)
        self.client.force_login(self.admin_user)

        response = self.client.get(
            self.school_url(
                "finance_invoice_detail", invoice_id=other_invoice.pk
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_invoice_page_renders_for_authorized_user(self):
        invoice = self.generate_invoice()
        self.client.force_login(self.admin_user)

        response = self.client.get(
            self.school_url(
                "finance_invoice_detail", invoice_id=invoice.pk
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, invoice.number)
        self.assertContains(response, "Traoré")
        self.assertContains(response, "112 500 FCFA")

    def test_receipt_page_renders_after_payment(self):
        invoice = self.generate_invoice()
        open_cash_session(self.school)
        payment = record_payment(
            invoice,
            amount=Decimal("1000.00"),
            method=PaymentMethod.CASH,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(
            self.school_url(
                "finance_payment_receipt", payment_id=payment.pk
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, payment.receipt_number)
        self.assertContains(response, "1 000 FCFA")


class FinanceViewFlowTests(FinanceTestBase):
    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_user(
            username="flow-admin", password="test"
        )
        Membership.all_objects.create(
            user=self.admin_user,
            organization=self.org,
            school=self.school,
            role=Role.SCHOOL_ADMIN,
        )
        self.client.force_login(self.admin_user)

    def test_invoice_generation_view_creates_invoice_for_class(self):
        response = self.client.post(
            self.school_url("finance_invoice_generate"),
            {
                "academic_year": self.year.pk,
                "school_class": self.school_class.pk,
                "student": "",
                "payment_plan": "",
                "issue_date": "2026-10-01",
                "notes": "Rentrée",
            },
        )

        self.assertEqual(response.status_code, 302)
        invoice = Invoice.all_objects.get(
            school=self.school, academic_year=self.year
        )
        self.assertEqual(invoice.subtotal, Decimal("125000.00"))
        self.assertEqual(
            response.url,
            self.school_url("finance_invoice_list")
            + f"?academic_year={self.year.pk}",
        )

    def test_payment_view_records_payment_and_redirects_to_receipt(self):
        invoice = self.generate_invoice()
        open_cash_session(self.school)

        response = self.client.post(
            self.school_url(
                "finance_payment_create", invoice_id=invoice.pk
            ),
            {
                "amount": "1000.00",
                "method": PaymentMethod.CASH,
                "reference": "Caisse 1",
                "paid_at": "2026-10-01",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        payment = Payment.all_objects.get(invoice=invoice)
        self.assertEqual(
            response.url,
            self.school_url(
                "finance_payment_receipt", payment_id=payment.pk
            ),
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_total, Decimal("1000.00"))

    def test_payment_view_rejects_amount_above_balance(self):
        invoice = self.generate_invoice()
        open_cash_session(self.school)

        response = self.client.post(
            self.school_url(
                "finance_payment_create", invoice_id=invoice.pk
            ),
            {
                "amount": "999999.00",
                "method": PaymentMethod.CASH,
                "reference": "",
                "paid_at": "2026-10-01",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dépasse le solde")
        self.assertFalse(
            Payment.all_objects.filter(invoice=invoice).exists()
        )

    def test_cash_open_and_close_views(self):
        open_response = self.client.post(
            self.school_url("finance_cash_open"),
            {
                "site": "",
                "opening_float": "10000.00",
                "notes": "Ouverture test",
            },
        )
        session = CashSession.all_objects.get(school=self.school)
        self.assertEqual(open_response.status_code, 302)
        self.assertEqual(session.status, CashSessionStatus.OPEN)

        close_response = self.client.post(
            self.school_url(
                "finance_cash_close", session_id=session.pk
            ),
            {"counted_cash": "10000.00", "notes": "Clôture test"},
        )
        session.refresh_from_db()
        self.assertEqual(close_response.status_code, 302)
        self.assertEqual(session.status, CashSessionStatus.CLOSED)
        self.assertEqual(session.difference, Decimal("0.00"))

    def test_cancel_invoice_view_requires_reason_and_cancels(self):
        invoice = self.generate_invoice()
        page = self.client.get(
            self.school_url(
                "finance_invoice_cancel", invoice_id=invoice.pk
            )
        )
        self.assertEqual(page.status_code, 200)

        response = self.client.post(
            self.school_url(
                "finance_invoice_cancel", invoice_id=invoice.pk
            ),
            {"reason": "Erreur de saisie sur la classe"},
        )

        invoice.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(invoice.status, InvoiceStatus.CANCELLED)
        self.assertEqual(invoice.cancellation_reason, "Erreur de saisie sur la classe")

    def test_overdue_page_lists_late_installments(self):
        invoice = self.generate_invoice()
        InvoiceInstallment.all_objects.filter(invoice=invoice).update(
            due_date=date(2020, 1, 1)
        )

        response = self.client.get(self.school_url("finance_overdue_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, invoice.number)
        self.assertContains(response, invoice.student.full_name)
        self.assertContains(response, "112 500 FCFA")

    def test_export_download_returns_excel_workbook(self):
        self.generate_invoice()
        response = self.client.get(
            self.school_url("finance_export_download"),
            {"academic_year": self.year.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        workbook = load_workbook(BytesIO(response.content))
        self.assertIn("Factures", workbook.sheetnames)
        self.assertIn("Synthèse", workbook.sheetnames)

    def test_export_download_with_invalid_year_returns_404(self):
        response = self.client.get(
            self.school_url("finance_export_download"),
            {"academic_year": "annee-invalide"},
        )

        self.assertEqual(response.status_code, 404)

    def test_payment_list_and_invoice_list_render(self):
        invoice = self.generate_invoice()
        open_cash_session(self.school)
        record_payment(
            invoice,
            amount=Decimal("1000.00"),
            method=PaymentMethod.CASH,
        )

        invoices = self.client.get(
            self.school_url("finance_invoice_list"),
            {"academic_year": self.year.pk},
        )
        payments = self.client.get(
            self.school_url("finance_payment_list"),
            {"academic_year": self.year.pk},
        )

        self.assertEqual(invoices.status_code, 200)
        self.assertEqual(payments.status_code, 200)
        self.assertContains(invoices, invoice.number)
        self.assertContains(payments, "REC-2026-00001")
