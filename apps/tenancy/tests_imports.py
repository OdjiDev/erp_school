import shutil
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from openpyxl import Workbook, load_workbook

from apps.academics.models import (
    AcademicYear,
    Curriculum,
    CurriculumSubject,
    Level,
    SchoolClass,
    Series,
    Subject,
)
from apps.common.tenancy import tenant_scope
from apps.students.models import (
    Enrollment,
    Guardian,
    Student,
    StudentGuardian,
)
from apps.tenancy.models import Organization, School


class ExcelImportTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

        self.org = Organization.all_objects.create(
            name="Groupe Import", slug="groupe-import"
        )
        self.enterContext(tenant_scope(self.org.pk))
        self.school = School.objects.create(
            organization=self.org, name="Lycée Import", code="IMP-1"
        )
        self.enterContext(tenant_scope(self.org.pk, self.school.pk))
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
        )
        self.level = Level.objects.create(
            school=self.school, code="11", name="11ème", order=2
        )
        self.series_let = Series.objects.create(
            level=self.level, code="LET", name="Lettres"
        )
        self.series_sci = Series.objects.create(
            level=self.level, code="SCI", name="Sciences"
        )

    def _save_workbook(
        self,
        name="import.xlsx",
        subject_rows=None,
        coefficient_rows=None,
        student_rows=None,
        subject_headers=("Code", "Nom"),
    ):
        workbook = Workbook()
        subjects = workbook.active
        subjects.title = "Matieres"
        subjects.append(list(subject_headers))
        for row in subject_rows or []:
            subjects.append(row)

        coefficients = workbook.create_sheet("Coefficients")
        coefficients.append(
            ["Niveau", "Série", "Matière", "Coefficient", "Heures"]
        )
        for row in coefficient_rows or []:
            coefficients.append(row)

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
        for row in student_rows or []:
            students.append(row)

        path = Path(self.temp_dir) / name
        workbook.save(path)
        return path

    def _run_import(self, path, **kwargs):
        call_command(
            "import_excel",
            str(path),
            organisation=self.org.slug,
            ecole=self.school.code,
            annee=self.year.name,
            **kwargs,
        )

    def _base_workbook(self, **overrides):
        values = {
            "subject_rows": [
                ["FR", "Français"],
                ["MATH", "Mathématiques"],
                ["ANG", "Anglais"],
            ],
            "coefficient_rows": [
                ["11", "LET", "FR", 4, 5],
                ["11", "LET", "MATH", 2, 3],
                ["11", "SCI", "FR", "4,5", None],
            ],
            "student_rows": [
                [
                    "M001",
                    "Traoré",
                    "Awa",
                    "F",
                    date(2009, 3, 12),
                    "Bamako",
                    "70000001",
                    "awa@example.com",
                    "Badalabougou",
                    "11",
                    "LET",
                    "A",
                    "Traoré",
                    "Moussa",
                    "76000001",
                    "Père",
                    "Oui",
                    "Actif",
                ],
                [
                    "M002",
                    "Diarra",
                    "Ibrahim",
                    "M",
                    "20/05/2008",
                    "Ségou",
                    "70000002",
                    "",
                    "",
                    "11",
                    "LET",
                    "A",
                    "Diarra",
                    "Aminata",
                    "76000002",
                    "Mère",
                    "",
                    "",
                ],
            ],
        }
        values.update(overrides)
        return self._save_workbook(**values)

    def test_import_subjects_coefficients_and_students(self):
        path = self._base_workbook()
        self._run_import(path)

        self.assertEqual(
            set(Subject.objects.filter(school=self.school).values_list(
                "code", flat=True
            )),
            {"FR", "MATH", "ANG"},
        )

        curriculum = Curriculum.objects.get(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series_let,
        )
        coefficients = {
            item.subject.code: item
            for item in curriculum.curriculum_subjects.select_related("subject")
        }
        self.assertEqual(coefficients["FR"].coefficient, Decimal("4"))
        self.assertEqual(coefficients["FR"].weekly_hours, Decimal("5"))
        self.assertEqual(coefficients["MATH"].coefficient, Decimal("2"))
        self.assertEqual(len(coefficients), 2)

        student = Student.objects.get(school=self.school, matricule="M001")
        self.assertEqual(student.first_name, "Awa")
        self.assertEqual(student.gender, "F")
        self.assertEqual(student.date_of_birth, date(2009, 3, 12))

        school_class = SchoolClass.objects.get(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series_let,
            section="A",
        )
        self.assertEqual(school_class.display_name, "11ème A")
        enrollment = Enrollment.objects.get(
            student=student, academic_year=self.year
        )
        self.assertEqual(enrollment.school_class, school_class)
        self.assertEqual(enrollment.status, "active")

        guardian = Guardian.objects.get(
            organization=self.org, phone="76000001"
        )
        self.assertEqual(guardian.last_name, "Traoré")
        link = StudentGuardian.objects.get(student=student, guardian=guardian)
        self.assertEqual(link.relationship, "father")
        self.assertTrue(link.is_primary)
        self.assertTrue(link.is_financial_responsible)

        second_student = Student.objects.get(
            school=self.school, matricule="M002"
        )
        second_link = StudentGuardian.objects.get(student=second_student)
        self.assertEqual(second_link.relationship, "mother")
        self.assertTrue(second_link.is_primary)
        self.assertFalse(second_link.is_financial_responsible)

    def test_reimport_updates_without_duplicates(self):
        self._run_import(self._base_workbook())

        updated_path = self._base_workbook(
            coefficient_rows=[
                ["11", "LET", "FR", 5, 5],
                ["11", "LET", "MATH", 2, 3],
                ["11", "SCI", "FR", "4,5", None],
            ],
            student_rows=[
                [
                    "M001",
                    "Traoré",
                    "Awa",
                    "F",
                    date(2009, 3, 12),
                    "Bamako",
                    "70000009",
                    "awa@example.com",
                    "Badalabougou",
                    "11",
                    "LET",
                    "A",
                    "Traoré",
                    "Moussa",
                    "76000001",
                    "Père",
                    "Oui",
                    "Actif",
                ]
            ],
        )
        self._run_import(updated_path)

        self.assertEqual(Subject.objects.filter(school=self.school).count(), 3)
        self.assertEqual(Student.objects.filter(school=self.school).count(), 2)
        self.assertEqual(
            Enrollment.objects.filter(school=self.school).count(), 2
        )
        self.assertEqual(
            Guardian.objects.filter(organization=self.org).count(), 2
        )
        self.assertEqual(
            StudentGuardian.objects.filter(student__school=self.school).count(),
            2,
        )
        self.assertEqual(
            SchoolClass.objects.filter(school=self.school).count(), 1
        )

        coefficient = CurriculumSubject.objects.get(
            curriculum__school=self.school,
            curriculum__academic_year=self.year,
            curriculum__series=self.series_let,
            subject__code="FR",
        )
        self.assertEqual(coefficient.coefficient, Decimal("5"))

        student = Student.objects.get(school=self.school, matricule="M001")
        self.assertEqual(student.phone, "70000009")

    def test_dry_run_rolls_back(self):
        path = self._save_workbook(
            name="dry-run.xlsx",
            subject_rows=[["HIST", "Histoire"]],
        )
        output = StringIO()

        self._run_import(path, dry_run=True, stdout=output)

        self.assertFalse(
            Subject.objects.filter(school=self.school, code="HIST").exists()
        )
        self.assertIn("Simulation", output.getvalue())

    def test_error_rolls_back_everything(self):
        path = self._save_workbook(
            name="erreur.xlsx",
            subject_rows=[["GEO", "Géographie"]],
            coefficient_rows=[
                ["11", "LET", "MATIERE_INCONNUE", 2, 1],
            ],
        )
        output = StringIO()

        with self.assertRaises(CommandError) as context:
            self._run_import(path, stdout=output)

        self.assertIn("Import annulé", str(context.exception))
        self.assertFalse(
            Subject.objects.filter(school=self.school, code="GEO").exists()
        )
        self.assertIn("MATIERE_INCONNUE", output.getvalue())

    def test_missing_required_header_is_reported(self):
        path = self._save_workbook(
            name="entete.xlsx",
            subject_rows=[["FR", "Français"]],
            subject_headers=("Code",),
        )

        with self.assertRaises(CommandError):
            self._run_import(path)

        self.assertFalse(
            Subject.objects.filter(school=self.school, code="FR").exists()
        )

    def test_excel_template_contains_sheets_and_references(self):
        path = Path(self.temp_dir) / "modele.xlsx"

        call_command(
            "excel_template",
            sortie=str(path),
            organisation=self.org.slug,
            ecole=self.school.code,
        )

        workbook = load_workbook(path, read_only=True)
        self.assertEqual(
            workbook.sheetnames,
            ["Mode d'emploi", "Matieres", "Coefficients", "Eleves", "References"],
        )
        students = workbook["Eleves"]
        self.assertEqual(students["A1"].value, "Matricule")
        self.assertEqual(students["R1"].value, "Statut")

        references = workbook["References"]
        values = [
            str(value)
            for row in references.iter_rows(values_only=True)
            for value in row
            if value is not None
        ]
        self.assertIn("11", values)
        self.assertIn("LET", values)
