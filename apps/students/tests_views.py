from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Level, SchoolClass, Series
from apps.tenancy.models import Membership, Organization, Role, School

from .models import (
    Enrollment,
    EnrollmentStatus,
    Guardian,
    GuardianRelationship,
    Student,
    StudentGuardian,
)

User = get_user_model()


class StudentViewTestBase(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe Scolaire")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-1"
        )
        self.other_school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-2"
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
        self.school_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
            capacity=100,
        )

        self.admin = User.objects.create_user(
            username="direction-eleves", password=None
        )
        Membership.all_objects.create(
            user=self.admin,
            organization=self.org,
            school=self.school,
            role=Role.SCHOOL_ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="enseignant-eleves", password=None
        )
        Membership.all_objects.create(
            user=self.teacher,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )

        self.student = Student.all_objects.create(
            school=self.school,
            matricule="M001",
            first_name="Awa",
            last_name="Traoré",
            gender="F",
        )
        self.other_student = Student.all_objects.create(
            school=self.school,
            matricule="M002",
            first_name="Moussa",
            last_name="Diarra",
            gender="M",
        )
        self.guardian = Guardian.all_objects.create(
            organization=self.org,
            first_name="Fatoumata",
            last_name="Traoré",
            phone="+223 70 00 00 01",
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


class StudentCreateEditTests(StudentViewTestBase):
    def test_create_student_normalizes_matricule(self):
        response = self.client.post(
            self.url("student_create"),
            {
                "matricule": "m010",
                "first_name": "Aminata",
                "last_name": "Keita",
                "gender": "F",
                "date_of_birth": "2010-03-12",
                "place_of_birth": "Bamako",
                "address": "",
                "phone": "",
                "email": "",
                "status": "active",
                "notes": "",
            },
        )

        student = Student.all_objects.get(
            school=self.school, matricule="M010"
        )
        self.assertRedirects(
            response,
            self.url("student_detail", student_id=student.id),
        )
        self.assertEqual(student.first_name, "Aminata")

    def test_create_student_without_matricule_generates_one(self):
        response = self.client.post(
            self.url("student_create"),
            {
                "matricule": "",
                "first_name": "Seydou",
                "last_name": "Coulibaly",
                "gender": "M",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 302)
        student = Student.all_objects.get(
            school=self.school, first_name="Seydou"
        )
        self.assertTrue(student.matricule)
        self.assertTrue(student.matricule.startswith("EXC-1-"))

    def test_duplicate_matricule_is_rejected(self):
        response = self.client.post(
            self.url("student_create"),
            {
                "matricule": "M001",
                "first_name": "Doublon",
                "last_name": "Test",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "porte déjà ce matricule")
        self.assertFalse(
            Student.all_objects.filter(
                school=self.school, first_name="Doublon"
            ).exists()
        )

    def test_edit_student_requires_matricule(self):
        response = self.client.post(
            self.url("student_edit", student_id=self.student.id),
            {
                "matricule": "",
                "first_name": "Awa",
                "last_name": "Traoré",
                "gender": "F",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "matricule")
        self.student.refresh_from_db()
        self.assertEqual(self.student.matricule, "M001")

    def test_edit_student_updates_identity(self):
        response = self.client.post(
            self.url("student_edit", student_id=self.student.id),
            {
                "matricule": "M001",
                "first_name": "Awa",
                "last_name": "Traoré Diarra",
                "gender": "F",
                "status": "active",
            },
        )

        self.assertRedirects(
            response,
            self.url("student_detail", student_id=self.student.id),
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.last_name, "Traoré Diarra")

    def test_teacher_cannot_create_student(self):
        self.client.force_login(self.teacher)

        response = self.client.get(self.url("student_create"))

        self.assertEqual(response.status_code, 403)


class GuardianManagementTests(StudentViewTestBase):
    def test_create_guardian(self):
        response = self.client.post(
            self.url("guardian_create"),
            {
                "first_name": "Bakary",
                "last_name": "Sissoko",
                "phone": "+223 76 00 00 02",
                "secondary_phone": "",
                "email": "",
                "address": "",
                "occupation": "Commerçant",
                "notes": "",
            },
        )

        guardian = Guardian.all_objects.get(
            organization=self.org, last_name="Sissoko"
        )
        self.assertRedirects(
            response,
            self.url("guardian_detail", guardian_id=guardian.id),
        )

    def test_link_existing_guardian_as_primary(self):
        response = self.client.post(
            self.url(
                "student_guardian_create", student_id=self.student.id
            ),
            {
                "action": "existing",
                "guardian": self.guardian.id,
                "relationship": GuardianRelationship.MOTHER,
                "is_primary": "on",
                "is_financial_responsible": "on",
            },
        )

        self.assertRedirects(
            response,
            self.url("student_detail", student_id=self.student.id),
        )
        link = StudentGuardian.all_objects.get(
            student=self.student, guardian=self.guardian
        )
        self.assertTrue(link.is_primary)
        self.assertTrue(link.is_financial_responsible)

    def test_new_primary_guardian_replaces_previous_primary(self):
        first = StudentGuardian.all_objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship=GuardianRelationship.MOTHER,
            is_primary=True,
        )
        second_guardian = Guardian.all_objects.create(
            organization=self.org,
            first_name="Bakary",
            last_name="Sissoko",
            phone="+223 76 00 00 02",
        )

        self.client.post(
            self.url(
                "student_guardian_create", student_id=self.student.id
            ),
            {
                "action": "existing",
                "guardian": second_guardian.id,
                "relationship": GuardianRelationship.FATHER,
                "is_primary": "on",
            },
        )

        first.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(
            StudentGuardian.all_objects.get(
                student=self.student, guardian=second_guardian
            ).is_primary
        )

    def test_duplicate_guardian_link_is_rejected(self):
        StudentGuardian.all_objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship=GuardianRelationship.MOTHER,
        )

        response = self.client.post(
            self.url(
                "student_guardian_create", student_id=self.student.id
            ),
            {
                "action": "existing",
                "guardian": self.guardian.id,
                "relationship": GuardianRelationship.TUTOR,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "déjà lié")
        self.assertEqual(
            StudentGuardian.all_objects.filter(student=self.student).count(),
            1,
        )

    def test_remove_link_keeps_guardian(self):
        link = StudentGuardian.all_objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship=GuardianRelationship.MOTHER,
        )

        response = self.client.post(
            self.url(
                "student_guardian_delete",
                student_id=self.student.id,
                link_id=link.id,
            )
        )

        self.assertRedirects(
            response,
            self.url("student_detail", student_id=self.student.id),
        )
        self.assertFalse(
            StudentGuardian.all_objects.filter(pk=link.pk).exists()
        )
        self.assertTrue(
            Guardian.all_objects.filter(pk=self.guardian.pk).exists()
        )


class EnrollmentManagementTests(StudentViewTestBase):
    def enrollment_payload(self, **overrides):
        payload = {
            "student": self.student.id,
            "academic_year": self.year.id,
            "school_class": self.school_class.id,
            "status": EnrollmentStatus.ACTIVE,
            "enrolled_on": "2026-10-05",
            "exited_on": "",
            "notes": "",
        }
        payload.update(overrides)
        return payload

    def test_create_enrollment(self):
        response = self.client.post(
            self.url("enrollment_create"), self.enrollment_payload()
        )

        enrollment = Enrollment.all_objects.get(
            student=self.student, academic_year=self.year
        )
        self.assertRedirects(
            response,
            self.url("student_detail", student_id=self.student.id),
        )
        self.assertEqual(enrollment.school_class, self.school_class)

    def test_duplicate_enrollment_is_rejected(self):
        Enrollment.all_objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.year,
            school_class=self.school_class,
        )

        response = self.client.post(
            self.url("enrollment_create"), self.enrollment_payload()
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "déjà inscrit")
        self.assertEqual(
            Enrollment.all_objects.filter(student=self.student).count(), 1
        )

    def test_enrollment_edit_locks_student_and_year(self):
        enrollment = Enrollment.all_objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.year,
            school_class=self.school_class,
        )
        second_year = AcademicYear.all_objects.create(
            school=self.school,
            name="2027-2028",
            start_date=date(2027, 10, 1),
            end_date=date(2028, 6, 30),
        )

        response = self.client.post(
            self.url("enrollment_edit", enrollment_id=enrollment.id),
            self.enrollment_payload(
                student=self.other_student.id,
                academic_year=second_year.id,
            ),
        )

        self.assertRedirects(
            response,
            self.url("student_detail", student_id=self.student.id),
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.student, self.student)
        self.assertEqual(enrollment.academic_year, self.year)

    def test_enrollment_edit_form_disables_identity_fields(self):
        enrollment = Enrollment.all_objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.year,
            school_class=self.school_class,
        )

        response = self.client.get(
            self.url("enrollment_edit", enrollment_id=enrollment.id)
        )

        form = response.context["form"]
        self.assertTrue(form.fields["student"].disabled)
        self.assertTrue(form.fields["academic_year"].disabled)

    def test_enrollment_list_without_year_does_not_crash(self):
        AcademicYear.all_objects.filter(school=self.school).delete()

        response = self.client.get(self.url("enrollment_list"), {"q": "zzz"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune inscription")
