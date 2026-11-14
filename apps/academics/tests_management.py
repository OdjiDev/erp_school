from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from apps.students.models import Enrollment, Student
from apps.tenancy.models import Membership, Organization, Role, School

from .models import (
    AcademicYear,
    ClassSubject,
    Curriculum,
    CurriculumSubject,
    Level,
    SchoolClass,
    Series,
    Subject,
)

User = get_user_model()


class AcademicManagementTestBase(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe Académique")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Académique", code="ACA-1"
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
        self.subject_fr = Subject.all_objects.create(
            school=self.school, code="FR", name="Français"
        )
        self.subject_math = Subject.all_objects.create(
            school=self.school, code="MATH", name="Mathématiques"
        )

        self.admin = User.objects.create_user(
            username="direction-academique", password=None
        )
        Membership.all_objects.create(
            user=self.admin,
            organization=self.org,
            school=self.school,
            role=Role.SCHOOL_ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="enseignant-academique", password=None,
            first_name="Ibrahim", last_name="Konaté",
        )
        Membership.all_objects.create(
            user=self.teacher,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )
        self.teacher_2 = User.objects.create_user(
            username="enseignant-academique-2", password=None,
            first_name="Mariam", last_name="Cissé",
        )
        Membership.all_objects.create(
            user=self.teacher_2,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )

        self.client.force_login(self.admin)

    def url(self, name, **kwargs):
        return reverse(
            f"school:{name}",
            kwargs={
                "org_slug": self.school.organization.slug,
                "school_code": self.school.code,
                **kwargs,
            },
        )

    def curriculum_url(self):
        return (
            f"{self.url('curriculum_list')}"
            f"?annee={self.year.id}&niveau={self.level.id}"
            f"&serie={self.series.id}"
        )


class SubjectManagementTests(AcademicManagementTestBase):
    def test_create_subject_normalizes_code(self):
        response = self.client.post(
            self.url("subject_create"),
            {"code": "hg", "name": "Histoire-Géographie"},
        )

        self.assertRedirects(response, self.url("subject_list"))
        subject = Subject.all_objects.get(school=self.school, code="HG")
        self.assertEqual(subject.name, "Histoire-Géographie")

    def test_duplicate_subject_code_is_rejected(self):
        response = self.client.post(
            self.url("subject_create"),
            {"code": "fr", "name": "Français bis"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "existe déjà")
        self.assertEqual(
            Subject.all_objects.filter(school=self.school, code="FR").count(),
            1,
        )

    def test_teacher_cannot_manage_subjects(self):
        self.client.force_login(self.teacher)

        response = self.client.get(self.url("subject_create"))

        self.assertEqual(response.status_code, 403)


class CurriculumManagementTests(AcademicManagementTestBase):
    def test_create_curriculum_for_selection(self):
        response = self.client.post(
            self.curriculum_url(), {"action": "create"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Curriculum.all_objects.filter(
                school=self.school,
                academic_year=self.year,
                level=self.level,
                series=self.series,
            ).exists()
        )

    def test_add_coefficient_to_curriculum(self):
        curriculum = Curriculum.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
        )

        response = self.client.post(
            self.curriculum_url(),
            {
                "action": "add",
                "subject": self.subject_fr.id,
                "coefficient": "4.00",
                "weekly_hours": "3.0",
            },
        )

        self.assertEqual(response.status_code, 302)
        item = CurriculumSubject.all_objects.get(
            curriculum=curriculum, subject=self.subject_fr
        )
        self.assertEqual(item.coefficient, 4)
        self.assertEqual(item.weekly_hours, 3)

    def test_duplicate_coefficient_is_rejected(self):
        curriculum = Curriculum.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
        )
        CurriculumSubject.all_objects.create(
            curriculum=curriculum,
            subject=self.subject_fr,
            coefficient=4,
        )

        response = self.client.post(
            self.curriculum_url(),
            {
                "action": "add",
                "subject": self.subject_fr.id,
                "coefficient": "2.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CurriculumSubject.all_objects.filter(
                curriculum=curriculum, subject=self.subject_fr
            ).count(),
            1,
        )

    def test_edit_coefficient_cannot_change_subject(self):
        curriculum = Curriculum.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
        )
        item = CurriculumSubject.all_objects.create(
            curriculum=curriculum,
            subject=self.subject_fr,
            coefficient=4,
        )

        response = self.client.post(
            self.url(
                "curriculum_subject_edit", curriculum_subject_id=item.id
            ),
            {
                "subject": self.subject_math.id,
                "coefficient": "5.00",
                "weekly_hours": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.subject, self.subject_fr)
        self.assertEqual(item.coefficient, 5)


class ClassManagementTests(AcademicManagementTestBase):
    def test_create_class_copies_curriculum_subjects(self):
        curriculum = Curriculum.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
        )
        CurriculumSubject.all_objects.create(
            curriculum=curriculum, subject=self.subject_fr, coefficient=4
        )
        CurriculumSubject.all_objects.create(
            curriculum=curriculum, subject=self.subject_math, coefficient=5
        )

        response = self.client.post(
            self.url("class_create"),
            {
                "academic_year": self.year.id,
                "level": self.level.id,
                "series": self.series.id,
                "section": "b",
                "name": "",
                "site": "",
                "capacity": "100",
            },
        )

        school_class = SchoolClass.all_objects.get(
            school=self.school, section="B"
        )
        self.assertRedirects(
            response,
            self.url("class_detail", class_id=school_class.id),
        )
        self.assertEqual(
            ClassSubject.all_objects.filter(
                school_class=school_class
            ).count(),
            2,
        )

    def test_duplicate_class_is_rejected(self):
        SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
        )

        response = self.client.post(
            self.url("class_create"),
            {
                "academic_year": self.year.id,
                "level": self.level.id,
                "series": self.series.id,
                "section": "A",
                "name": "",
                "site": "",
                "capacity": "100",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            SchoolClass.all_objects.filter(
                school=self.school, section="A"
            ).count(),
            1,
        )

    def test_class_identity_is_locked_when_students_are_enrolled(self):
        school_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
        )
        student = Student.all_objects.create(
            school=self.school,
            matricule="M100",
            first_name="Awa",
            last_name="Traoré",
        )
        Enrollment.all_objects.create(
            school=self.school,
            student=student,
            academic_year=self.year,
            school_class=school_class,
        )

        response = self.client.get(
            self.url("class_edit", class_id=school_class.id)
        )

        form = response.context["form"]
        for field_name in ("academic_year", "level", "series", "section"):
            self.assertTrue(form.fields[field_name].disabled)

        self.client.post(
            self.url("class_edit", class_id=school_class.id),
            {
                "academic_year": self.year.id,
                "level": self.level.id,
                "series": self.series.id,
                "section": "Z",
                "name": "",
                "site": "",
                "capacity": "100",
            },
        )
        school_class.refresh_from_db()
        self.assertEqual(school_class.section, "A")

    def test_add_subject_assignment_with_teacher(self):
        school_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
        )

        response = self.client.post(
            self.url("class_assignments", class_id=school_class.id),
            {
                "action": "add",
                "subject": self.subject_fr.id,
                "teacher": self.teacher.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment = ClassSubject.all_objects.get(
            school_class=school_class, subject=self.subject_fr
        )
        self.assertEqual(assignment.teacher, self.teacher)

    def test_save_teacher_assignments(self):
        school_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
        )
        assignment = ClassSubject.all_objects.create(
            school_class=school_class,
            subject=self.subject_fr,
            teacher=self.teacher,
        )

        response = self.client.post(
            self.url("class_assignments", class_id=school_class.id),
            {
                "action": "save",
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": assignment.id,
                "form-0-teacher": self.teacher_2.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.teacher, self.teacher_2)

    def test_class_export_contains_students(self):
        school_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
        )
        student = Student.all_objects.create(
            school=self.school,
            matricule="M200",
            first_name="Awa",
            last_name="Traoré",
            gender="F",
        )
        Enrollment.all_objects.create(
            school=self.school,
            student=student,
            academic_year=self.year,
            school_class=school_class,
        )

        response = self.client.get(
            self.url("class_export", class_id=school_class.id)
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "spreadsheetml.sheet", response["Content-Type"]
        )
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook.active
        self.assertEqual(sheet["A1"].value, "Matricule")
        self.assertEqual(sheet["A2"].value, "M200")
        self.assertEqual(sheet["B2"].value, "Traoré")

    def test_teacher_cannot_create_class(self):
        self.client.force_login(self.teacher)

        response = self.client.get(self.url("class_create"))

        self.assertEqual(response.status_code, 403)

    def test_class_from_another_school_is_not_accessible(self):
        other_org = Organization.all_objects.create(name="Groupe Extérieur")
        other_school = School.all_objects.create(
            organization=other_org, name="Lycée Extérieur", code="EXT-1"
        )
        other_year = AcademicYear.all_objects.create(
            school=other_school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
        )
        other_level = Level.all_objects.create(
            school=other_school, code="11", name="11ème", order=2
        )
        other_series = Series.all_objects.create(
            level=other_level, code="LET", name="Lettres"
        )
        other_class = SchoolClass.all_objects.create(
            school=other_school,
            academic_year=other_year,
            level=other_level,
            series=other_series,
            section="A",
        )

        response = self.client.get(
            self.url("class_detail", class_id=other_class.id)
        )

        self.assertEqual(response.status_code, 404)
