from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.academics.models import AcademicYear, Level, SchoolClass, Series
from apps.common.tenancy import tenant_scope
from apps.tenancy.models import Organization, School

from .models import (
    Enrollment,
    EnrollmentStatus,
    Guardian,
    GuardianRelationship,
    Student,
    StudentGuardian,
)


class StudentIdentityTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe A")
        self.other_org = Organization.all_objects.create(name="Groupe B")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-1"
        )
        self.same_name_school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-2"
        )

    def test_matricule_is_generated_when_missing(self):
        first = Student.all_objects.create(
            school=self.school, first_name="Awa", last_name="Traoré"
        )
        second = Student.all_objects.create(
            school=self.school, first_name="Ibrahim", last_name="Traoré"
        )

        self.assertTrue(first.matricule.startswith("EXC-1-"))
        self.assertNotEqual(first.matricule, second.matricule)

    def test_matricule_is_unique_per_school(self):
        Student.all_objects.create(
            school=self.school,
            matricule="M001",
            first_name="Awa",
            last_name="Traoré",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Student.all_objects.create(
                school=self.school,
                matricule="M001",
                first_name="Autre",
                last_name="Élève",
            )

    def test_same_matricule_allowed_in_another_school(self):
        Student.all_objects.create(
            school=self.school,
            matricule="M001",
            first_name="Awa",
            last_name="Traoré",
        )
        Student.all_objects.create(
            school=self.same_name_school,
            matricule="M001",
            first_name="Ibrahim",
            last_name="Traoré",
        )

        self.assertEqual(Student.all_objects.filter(matricule="M001").count(), 2)

    def test_future_birth_date_is_rejected(self):
        student = Student(
            school=self.school,
            first_name="Futur",
            last_name="Élève",
            date_of_birth=date.today() + timedelta(days=1),
        )

        with self.assertRaises(ValidationError):
            student.full_clean()

    def test_full_name_and_display(self):
        student = Student.all_objects.create(
            school=self.school,
            matricule="M001",
            first_name="Awa",
            last_name="Traoré",
        )

        self.assertEqual(student.full_name, "Awa Traoré")
        self.assertIn("M001", str(student))


class GuardianTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe A")
        self.other_org = Organization.all_objects.create(name="Groupe B")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-1"
        )
        self.other_school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-2"
        )
        self.student = Student.all_objects.create(
            school=self.school,
            matricule="M001",
            first_name="Awa",
            last_name="Traoré",
        )
        self.guardian = Guardian.all_objects.create(
            organization=self.org,
            first_name="Moussa",
            last_name="Traoré",
            phone="+22370000000",
        )

    def test_guardian_can_have_children_in_two_schools_of_same_org(self):
        other_student = Student.all_objects.create(
            school=self.other_school,
            matricule="M001",
            first_name="Ibrahim",
            last_name="Traoré",
        )

        for student in (self.student, other_student):
            link = StudentGuardian(
                student=student,
                guardian=self.guardian,
                relationship=GuardianRelationship.FATHER,
                is_primary=True,
            )
            link.full_clean()
            link.save()

        with tenant_scope(self.org.pk):
            self.assertEqual(self.guardian.studentships.count(), 2)

    def test_guardian_from_another_organization_is_rejected(self):
        foreign_guardian = Guardian.all_objects.create(
            organization=self.other_org,
            first_name="Autre",
            last_name="Parent",
            phone="+22376000000",
        )
        link = StudentGuardian(
            student=self.student,
            guardian=foreign_guardian,
            relationship=GuardianRelationship.TUTOR,
        )

        with self.assertRaises(ValidationError):
            link.full_clean()

    def test_only_one_primary_guardian_per_student(self):
        second_guardian = Guardian.all_objects.create(
            organization=self.org,
            first_name="Aminata",
            last_name="Traoré",
            phone="+22376000000",
        )
        StudentGuardian.all_objects.create(
            student=self.student,
            guardian=self.guardian,
            relationship=GuardianRelationship.FATHER,
            is_primary=True,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentGuardian.all_objects.create(
                student=self.student,
                guardian=second_guardian,
                relationship=GuardianRelationship.MOTHER,
                is_primary=True,
            )

        StudentGuardian.all_objects.create(
            student=self.student,
            guardian=second_guardian,
            relationship=GuardianRelationship.MOTHER,
            is_primary=False,
        )
        with tenant_scope(self.org.pk, self.school.pk):
            self.assertEqual(self.student.guardianships.count(), 2)


class EnrollmentTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe A")
        self.other_org = Organization.all_objects.create(name="Groupe B")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-1"
        )
        self.same_name_school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-2"
        )
        self.foreign_school = School.all_objects.create(
            organization=self.other_org, name="Lycée B", code="EXC-1"
        )
        self.student = Student.all_objects.create(
            school=self.school,
            matricule="M001",
            first_name="Awa",
            last_name="Traoré",
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
        )
        self.parallel_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="B",
        )

        self.next_year = AcademicYear.all_objects.create(
            school=self.school,
            name="2027-2028",
            start_date=date(2027, 10, 1),
            end_date=date(2028, 6, 30),
        )
        self.next_year_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.next_year,
            level=self.level,
            series=self.series,
            section="A",
        )

        other_year = AcademicYear.all_objects.create(
            school=self.same_name_school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
        )
        other_level = Level.all_objects.create(
            school=self.same_name_school, code="11", name="11ème", order=2
        )
        other_series = Series.all_objects.create(
            level=other_level, code="LET", name="Lettres"
        )
        self.other_school_class = SchoolClass.all_objects.create(
            school=self.same_name_school,
            academic_year=other_year,
            level=other_level,
            series=other_series,
            section="A",
        )

    def make_enrollment(self, **kwargs):
        defaults = {
            "school": self.school,
            "student": self.student,
            "academic_year": self.year,
            "school_class": self.school_class,
        }
        defaults.update(kwargs)
        return Enrollment(**defaults)

    def test_school_is_derived_from_student(self):
        enrollment = Enrollment.all_objects.create(
            student=self.student,
            academic_year=self.year,
            school_class=self.school_class,
        )

        self.assertEqual(enrollment.school_id, self.school.id)

    def test_one_enrollment_per_student_and_year(self):
        Enrollment.all_objects.create(
            student=self.student,
            academic_year=self.year,
            school_class=self.school_class,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.all_objects.create(
                student=self.student,
                academic_year=self.year,
                school_class=self.parallel_class,
            )

    def test_enrollment_rejects_class_from_another_school(self):
        enrollment = self.make_enrollment(
            school_class=self.other_school_class
        )

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_enrollment_rejects_class_from_another_year(self):
        enrollment = self.make_enrollment(school_class=self.next_year_class)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_enrollment_rejects_student_from_another_school(self):
        foreign_student = Student.all_objects.create(
            school=self.foreign_school,
            first_name="Autre",
            last_name="Élève",
        )
        enrollment = self.make_enrollment(student=foreign_student)

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_active_enrollment_cannot_have_exit_date(self):
        enrollment = self.make_enrollment(exited_on=date(2027, 1, 15))

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_exit_date_cannot_precede_enrollment_date(self):
        enrollment = self.make_enrollment(
            status=EnrollmentStatus.WITHDRAWN,
            exited_on=date(2020, 1, 1),
        )

        with self.assertRaises(ValidationError):
            enrollment.full_clean()

    def test_enrolled_count_ignores_non_active_enrollments(self):
        self.parallel_class.capacity = 2
        self.parallel_class.save()

        for index in range(2):
            student = Student.all_objects.create(
                school=self.school,
                first_name=f"Élève{index}",
                last_name="Test",
            )
            Enrollment.all_objects.create(
                student=student,
                academic_year=self.year,
                school_class=self.parallel_class,
            )

        withdrawn = Student.all_objects.create(
            school=self.school, first_name="Parti", last_name="Test"
        )
        Enrollment.all_objects.create(
            student=withdrawn,
            academic_year=self.year,
            school_class=self.parallel_class,
            status=EnrollmentStatus.WITHDRAWN,
        )

        self.assertEqual(self.parallel_class.enrolled_count, 2)
        self.assertTrue(self.parallel_class.is_full)
