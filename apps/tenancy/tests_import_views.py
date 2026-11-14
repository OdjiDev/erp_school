from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from apps.academics.models import (
    AcademicYear,
    CurriculumSubject,
    Level,
    Series,
    Subject,
)
from apps.students.models import Enrollment, Student

from .models import Membership, Organization, Role, School

User = get_user_model()

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


class ExcelImportViewTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe Web")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Web", code="WEB-1"
        )
        self.year = AcademicYear.all_objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
        )
        self.level = Level.all_objects.create(
            school=self.school, code="11", name="11ème", order=2
        )
        self.series = Series.all_objects.create(
            level=self.level, code="LET", name="Lettres"
        )

        self.user = User.objects.create_user(
            username="directeur-web", password=None
        )
        Membership.all_objects.create(
            user=self.user,
            organization=self.org,
            school=self.school,
            role=Role.SCHOOL_ADMIN,
        )
        self.client.force_login(self.user)

    def school_url(self, name="excel_import"):
        return reverse(
            f"school:{name}",
            kwargs={
                "org_slug": self.school.organization.slug,
                "school_code": self.school.code,
            },
        )

    def build_workbook(
        self,
        coefficient_subject="FR",
        student_matricule="WEB-001",
    ):
        workbook = Workbook()
        subjects = workbook.active
        subjects.title = "Matieres"
        subjects.append(["Code", "Nom"])
        subjects.append(["FR", "Français"])
        subjects.append(["MATH", "Mathématiques"])

        coefficients = workbook.create_sheet("Coefficients")
        coefficients.append(
            ["Niveau", "Série", "Matière", "Coefficient", "Heures"]
        )
        coefficients.append(["11", "LET", coefficient_subject, 4, 5])
        coefficients.append(["11", "LET", "MATH", 2, 3])

        students = workbook.create_sheet("Eleves")
        students.append(
            [
                "Matricule",
                "Nom",
                "Prénoms",
                "Sexe",
                "Date de naissance",
                "Lieu de naissance",
                "Téléphone",
                "Email",
                "Adresse",
                "Niveau",
                "Série",
                "Section",
                "Tuteur nom",
                "Tuteur prénoms",
                "Tuteur téléphone",
                "Lien",
                "Payeur",
                "Statut",
            ]
        )
        students.append(
            [
                student_matricule,
                "Traoré",
                "Awa",
                "F",
                "12/03/2009",
                "Bamako",
                "70000011",
                "",
                "",
                "11",
                "LET",
                "A",
                "Traoré",
                "Moussa",
                "76000011",
                "Père",
                "Oui",
                "Actif",
            ]
        )

        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def upload(self, content, name="import.xlsx"):
        return SimpleUploadedFile(
            name, content, content_type=XLSX_CONTENT_TYPE
        )

    def post_import(self, content=None, **extra):
        data = {
            "fichier": self.upload(content or self.build_workbook()),
            "annee": self.year.pk,
            "creer_classes": "on",
        }
        data.update(extra)
        return self.client.post(self.school_url(), data, follow=True)

    def test_get_import_page(self):
        response = self.client.get(self.school_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import Excel")
        self.assertContains(response, "Télécharger le modèle")

    def test_import_persists_subjects_coefficients_and_students(self):
        response = self.post_import()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import terminé")

        subjects = set(
            Subject.all_objects.filter(school=self.school).values_list(
                "code", flat=True
            )
        )
        self.assertEqual(subjects, {"FR", "MATH"})

        coefficient = CurriculumSubject.all_objects.get(
            curriculum__school=self.school,
            curriculum__academic_year=self.year,
            curriculum__level=self.level,
            curriculum__series=self.series,
            subject__code="FR",
        )
        self.assertEqual(coefficient.coefficient, Decimal("4"))
        self.assertEqual(coefficient.weekly_hours, Decimal("5"))

        student = Student.all_objects.get(
            school=self.school, matricule="WEB-001"
        )
        self.assertEqual(student.first_name, "Awa")
        enrollment = Enrollment.all_objects.get(
            student=student, academic_year=self.year
        )
        self.assertEqual(enrollment.school_class.section, "A")
        self.assertEqual(enrollment.status, "active")

    def test_dry_run_does_not_persist(self):
        response = self.post_import(dry_run="on")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Simulation réussie")
        self.assertFalse(
            Subject.all_objects.filter(school=self.school).exists()
        )
        self.assertFalse(
            Student.all_objects.filter(
                school=self.school, matricule="WEB-001"
            ).exists()
        )

    def test_import_error_rolls_back_everything(self):
        content = self.build_workbook(coefficient_subject="INCONNUE")
        response = self.post_import(content=content)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Aucune donnée n'a été enregistrée"
        )
        self.assertFalse(
            Subject.all_objects.filter(school=self.school).exists()
        )
        self.assertFalse(
            Student.all_objects.filter(
                school=self.school, matricule="WEB-001"
            ).exists()
        )

    def test_non_xlsx_upload_is_rejected(self):
        data = {
            "fichier": self.upload(b"pas un classeur", name="import.csv"),
            "annee": self.year.pk,
            "creer_classes": "on",
        }

        response = self.client.post(self.school_url(), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "format .xlsx")
        self.assertFalse(
            Subject.all_objects.filter(school=self.school).exists()
        )

    def test_template_download_contains_school_references(self):
        response = self.client.get(self.school_url("excel_template"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn("WEB-1", response["Content-Disposition"])

        workbook = load_workbook(
            BytesIO(response.content), read_only=True
        )
        self.assertEqual(
            workbook.sheetnames,
            [
                "Mode d'emploi",
                "Matieres",
                "Coefficients",
                "Eleves",
                "References",
            ],
        )
        values = [
            str(value)
            for row in workbook["References"].iter_rows(values_only=True)
            for value in row
            if value is not None
        ]
        self.assertIn("11", values)
        self.assertIn("LET", values)

    def test_teacher_cannot_import(self):
        teacher = User.objects.create_user(
            username="enseignant-web", password=None
        )
        Membership.all_objects.create(
            user=teacher,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )
        self.client.force_login(teacher)

        page = self.client.get(self.school_url())
        download = self.client.get(self.school_url("excel_template"))

        self.assertEqual(page.status_code, 403)
        self.assertEqual(download.status_code, 403)

    def test_secretary_can_access_import_page(self):
        secretary = User.objects.create_user(
            username="secretaire-web", password=None
        )
        Membership.all_objects.create(
            user=secretary,
            organization=self.org,
            school=self.school,
            role=Role.SECRETARY,
        )
        self.client.force_login(secretary)

        response = self.client.get(self.school_url())

        self.assertEqual(response.status_code, 200)

    def test_user_from_another_school_is_denied(self):
        other_org = Organization.all_objects.create(name="Groupe Autre")
        other_school = School.all_objects.create(
            organization=other_org, name="Autre école", code="AUT-1"
        )
        other_user = User.objects.create_user(
            username="autre-directeur", password=None
        )
        Membership.all_objects.create(
            user=other_user,
            organization=other_org,
            school=other_school,
            role=Role.SCHOOL_ADMIN,
        )
        self.client.force_login(other_user)

        response = self.client.get(self.school_url())

        self.assertEqual(response.status_code, 403)
