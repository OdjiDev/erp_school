from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academics.models import (
    AcademicYear,
    Level,
    SchoolClass,
    Series,
    Subject,
)
from apps.finance.models import (
    CashSession,
    CashSessionStatus,
    Discount,
    DiscountKind,
    Fee,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PaymentPlan,
    PaymentPlanLine,
)
from apps.finance.services import (
    generate_invoice_for_enrollment,
    open_cash_session,
    record_payment,
)
from apps.students.models import (
    Enrollment,
    EnrollmentStatus,
    Guardian,
    GuardianRelationship,
    Student,
    StudentGuardian,
)
from apps.tenancy.models import Organization, School, Site

LEVELS = [
    ("10", "10ème", 1),
    ("11", "11ème", 2),
    ("TLE", "Terminale", 3),
]

SERIES = {
    "10": [("CG", "Comptabilité et Gestion")],
    "11": [
        ("LET", "Lettres"),
        ("SCI", "Sciences"),
        ("SECO", "Sciences Économiques"),
    ],
    "TLE": [
        ("TSE", "Sciences Exactes"),
        ("TSEXP", "Sciences Expérimentales"),
        ("TSECO", "Sciences Économiques"),
        ("TSS", "Sciences Sociales"),
        ("TLL", "Langues et Littérature"),
        ("TAL", "Arts et Lettres"),
    ],
}

SUBJECTS = [
    ("FR", "Français"),
    ("MATH", "Mathématiques"),
    ("ANG", "Anglais"),
    ("HG", "Histoire-Géographie"),
    ("SVT", "Sciences de la Vie et de la Terre"),
    ("PC", "Physique-Chimie"),
    ("ECO", "Économie"),
]

STUDENTS = [
    ("Awa", "Traoré", "F"),
    ("Ibrahim", "Diarra", "M"),
    ("Fatoumata", "Keita", "F"),
    ("Moussa", "Coulibaly", "M"),
    ("Aminata", "Diallo", "F"),
    ("Oumar", "Sidibé", "M"),
    ("Mariam", "Touré", "F"),
    ("Seydou", "Konaté", "M"),
]

FEE_AMOUNTS = {
    "10": Decimal("150000.00"),
    "11": Decimal("180000.00"),
    "TLE": Decimal("220000.00"),
}


def _seed_finance(school, year):
    """Frais, échéancier, remise, factures, caisse et paiements de démonstration."""
    for level_code, level_name, order in LEVELS:
        level = Level.all_objects.get(school=school, code=level_code)
        Fee.all_objects.get_or_create(
            school=school,
            academic_year=year,
            level=level,
            series=None,
            name="Frais de scolarité",
            defaults={
                "amount": FEE_AMOUNTS[level_code],
                "description": f"Frais annuels de {level_name}.",
                "is_active": True,
            },
        )
    Fee.all_objects.get_or_create(
        school=school,
        academic_year=year,
        level=None,
        series=None,
        name="Frais d'inscription",
        defaults={
            "amount": Decimal("25000.00"),
            "description": "Frais administratifs d'inscription annuelle.",
            "is_active": True,
        },
    )

    plan, _ = PaymentPlan.all_objects.get_or_create(
        school=school,
        academic_year=year,
        level=None,
        series=None,
        name="Paiement en 3 tranches",
        defaults={"is_active": True},
    )
    start_year = year.start_date.year
    installments = [
        (1, "1ère tranche", date(start_year, 10, 15), Decimal("40.00")),
        (2, "2ème tranche", date(start_year + 1, 1, 15), Decimal("30.00")),
        (3, "3ème tranche", date(start_year + 1, 4, 15), Decimal("30.00")),
    ]
    for sequence, label, due_date, percentage in installments:
        PaymentPlanLine.all_objects.get_or_create(
            plan=plan,
            sequence=sequence,
            defaults={
                "label": label,
                "due_date": due_date,
                "percentage": percentage,
            },
        )

    first_student = (
        Student.all_objects.filter(school=school).order_by("matricule").first()
    )
    if first_student is not None:
        Discount.all_objects.get_or_create(
            school=school,
            academic_year=year,
            student=first_student,
            label="Bourse d'excellence",
            defaults={
                "kind": DiscountKind.PERCENTAGE,
                "value": Decimal("25.00"),
                "reason": "Major de promotion — démonstration.",
                "is_active": True,
            },
        )

    enrollments = (
        Enrollment.all_objects.filter(
            school=school,
            academic_year=year,
            status=EnrollmentStatus.ACTIVE,
        )
        .select_related(
            "student", "school_class__level", "school_class__series"
        )
        .order_by("student__last_name", "student__first_name")
    )
    for enrollment in enrollments:
        generate_invoice_for_enrollment(
            enrollment, issue_date=year.start_date
        )

    if not CashSession.all_objects.filter(
        school=school, status=CashSessionStatus.OPEN
    ).exists():
        open_cash_session(
            school,
            opening_float=Decimal("50000.00"),
            notes="Caisse de démonstration.",
        )

    invoices = (
        Invoice.all_objects.filter(school=school, academic_year=year)
        .exclude(status=InvoiceStatus.CANCELLED)
        .order_by("number")[:3]
    )
    for invoice in invoices:
        if invoice.total <= 0:
            continue
        if Payment.all_objects.filter(
            invoice=invoice, cancelled_at__isnull=True
        ).exists():
            continue
        amount = (invoice.total * Decimal("0.50")).quantize(Decimal("0.01"))
        if amount <= 0:
            continue
        record_payment(
            invoice,
            amount=amount,
            method=PaymentMethod.CASH,
            reference="Démonstration",
            paid_at=year.start_date,
            notes="Encaissement partiel de démonstration.",
        )


class Command(BaseCommand):
    help = "Crée un jeu de données de démonstration (deux écoles homonymes)."
    @transaction.atomic
    def handle(self, *args, **options):
        organization, _ = Organization.all_objects.get_or_create(
            slug="demo",
            defaults={"name": "Groupe Scolaire Démo"},
        )

        schools = []
        school_years = {}
        for code, name in [
            ("DEMO-A", "Lycée Démo"),
            ("DEMO-B", "Lycée Démo"),
        ]:
            school, _ = School.all_objects.get_or_create(
                organization=organization,
                code=code,
                defaults={"name": name},
            )
            Site.all_objects.get_or_create(
                school=school,
                code="PRINCIPAL",
                defaults={"name": "Campus principal", "is_primary": True},
            )
            year, _ = AcademicYear.all_objects.get_or_create(
                school=school,
                name="2026-2027",
                defaults={
                    "start_date": date(2026, 10, 1),
                    "end_date": date(2027, 6, 30),
                    "is_current": True,
                },
            )
            school_years[school] = year

            school_classes = []
            for level_code, level_name, order in LEVELS:
                level, _ = Level.all_objects.get_or_create(
                    school=school,
                    code=level_code,
                    defaults={"name": level_name, "order": order},
                )
                for series_code, series_name in SERIES[level_code]:
                    series, _ = Series.all_objects.get_or_create(
                        level=level,
                        code=series_code,
                        defaults={"name": series_name},
                    )
                    sections = ["A", "B"] if (
                        level_code == "11" and series_code == "LET"
                    ) else ["A"]
                    for section in sections:
                        school_class, _ = SchoolClass.all_objects.get_or_create(
                            school=school,
                            academic_year=year,
                            level=level,
                            series=series,
                            section=section,
                            defaults={"capacity": 100},
                        )
                        school_classes.append(school_class)

            for subject_code, subject_name in SUBJECTS:
                Subject.all_objects.get_or_create(
                    school=school,
                    code=subject_code,
                    defaults={"name": subject_name},
                )

            for index, (first_name, last_name, gender) in enumerate(
                STUDENTS, start=1
            ):
                student, _ = Student.all_objects.get_or_create(
                    school=school,
                    matricule=f"{school.code}-{index:03d}",
                    defaults={
                        "first_name": first_name,
                        "last_name": last_name,
                        "gender": gender,
                        "date_of_birth": date(2008, 1, 1),
                    },
                )

                Enrollment.all_objects.get_or_create(
                    student=student,
                    academic_year=year,
                    defaults={
                        "school_class": school_classes[
                            (index - 1) % len(school_classes)
                        ],
                        "status": EnrollmentStatus.ACTIVE,
                    },
                )

                relationship = (
                    GuardianRelationship.MOTHER
                    if index % 2 == 0
                    else GuardianRelationship.FATHER
                )
                guardian, _ = Guardian.all_objects.get_or_create(
                    organization=organization,
                    phone=f"+223 70 00 {index:02d} {school.code[-1]}",
                    defaults={
                        "first_name": "Mariam"
                        if relationship == GuardianRelationship.MOTHER
                        else "Moussa",
                        "last_name": last_name,
                    },
                )
                StudentGuardian.all_objects.get_or_create(
                    student=student,
                    guardian=guardian,
                    defaults={
                        "relationship": relationship,
                        "is_primary": True,
                        "is_financial_responsible": True,
                    },
                )

            _seed_finance(school, year)
            schools.append(school)

        self.stdout.write(self.style.SUCCESS("Jeu de démonstration prêt."))
        self.stdout.write(
            f"Organisation : {organization.name} (slug : {organization.slug})"
        )
        for school in schools:
            year = school_years[school]
            self.stdout.write(
                f"- {school.name} [{school.code}] : "
                f"{Student.all_objects.filter(school=school).count()} élèves, "
                f"{SchoolClass.all_objects.filter(school=school, academic_year=year).count()} classes, "
                f"{Invoice.all_objects.filter(school=school, academic_year=year).count()} factures, "
                f"{Payment.all_objects.filter(school=school).count()} encaissements"
            )
        self.stdout.write(
            "Créez un compte d'accès : python manage.py createsuperuser"
        )
