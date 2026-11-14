from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    ClassSubject,
    Curriculum,
    CurriculumSubject,
    Level,
    SchoolClass,
    Series,
    Subject,
)
from apps.students.models import (
    Enrollment,
    Guardian,
    GuardianRelationship,
    Student,
    StudentGuardian,
)
from apps.tenancy.models import Membership, Organization, Role, School, Site

from apps.common.tenancy import tenant_scope


TENANT_MODELS = (
    Organization,
    School,
    Site,
    Membership,
    AcademicYear,
    Level,
    Series,
    Subject,
    Curriculum,
    CurriculumSubject,
    SchoolClass,
    ClassSubject,
    Student,
    Guardian,
    StudentGuardian,
    Enrollment,
)


class TenantManagerTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe A", slug="groupe-a")
        self.other_org = Organization.all_objects.create(
            name="Groupe B", slug="groupe-b"
        )
        self.school_a = self._make_school(self.org, "A-1")
        self.school_sibling = self._make_school(self.org, "A-2")
        self.school_other = self._make_school(self.other_org, "B-1")

        user = get_user_model().objects.create_user(username="staff")
        Membership.all_objects.create(
            user=user, organization=self.org, role=Role.ORG_ADMIN
        )
        Membership.all_objects.create(
            user=user,
            organization=self.org,
            school=self.school_a,
            role=Role.SECRETARY,
        )
        Membership.all_objects.create(
            user=user,
            organization=self.org,
            school=self.school_sibling,
            role=Role.SECRETARY,
        )
        Membership.all_objects.create(
            user=user, organization=self.other_org, role=Role.ORG_ADMIN
        )

    def _make_school(self, organization, code):
        school = School.all_objects.create(
            organization=organization, name="Lycée Démo", code=code
        )
        Site.all_objects.create(school=school, name="Principal", code="MAIN")
        year = AcademicYear.all_objects.create(
            school=school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
        )
        level = Level.all_objects.create(school=school, code="11", name="11ème")
        series = Series.all_objects.create(level=level, code="LET", name="Lettres")
        subject = Subject.all_objects.create(school=school, code="FR", name="Français")
        curriculum = Curriculum.all_objects.create(
            school=school,
            academic_year=year,
            level=level,
            series=series,
        )
        CurriculumSubject.all_objects.create(
            curriculum=curriculum, subject=subject, coefficient=Decimal("1")
        )
        school_class = SchoolClass.all_objects.create(
            school=school,
            academic_year=year,
            level=level,
            series=series,
            section="A",
        )
        ClassSubject.all_objects.create(school_class=school_class, subject=subject)
        student = Student.all_objects.create(
            school=school, first_name="Awa", last_name="Traoré"
        )
        guardian, _ = Guardian.all_objects.get_or_create(
            organization=organization,
            phone=f"+223 70 {organization.slug}",
            defaults={"first_name": "Mariam", "last_name": "Traoré"},
        )
        StudentGuardian.all_objects.create(
            student=student,
            guardian=guardian,
            relationship=GuardianRelationship.MOTHER,
        )
        Enrollment.all_objects.create(
            student=student, academic_year=year, school_class=school_class
        )
        return school

    def test_every_tenant_manager_returns_no_rows_without_scope(self):
        for model in TENANT_MODELS:
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.count(), 0)

    def test_organization_scope_filters_all_tenant_models(self):
        with tenant_scope(self.org.pk):
            self.assertEqual(Organization.objects.count(), 1)
            self.assertEqual(School.objects.count(), 2)
            self.assertEqual(Site.objects.count(), 2)
            self.assertEqual(Membership.objects.count(), 3)
            for model in (
                AcademicYear,
                Level,
                Series,
                Subject,
                Curriculum,
                CurriculumSubject,
                SchoolClass,
                ClassSubject,
                Student,
                StudentGuardian,
                Enrollment,
            ):
                with self.subTest(model=model.__name__):
                    self.assertEqual(model.objects.count(), 2)
            self.assertEqual(Guardian.objects.count(), 1)

    def test_school_scope_isolates_school_rows_and_keeps_org_membership(self):
        with tenant_scope(self.org.pk, self.school_a.pk):
            self.assertEqual(
                list(School.objects.values_list("pk", flat=True)),
                [self.school_a.pk],
            )
            self.assertEqual(Site.objects.count(), 1)
            self.assertEqual(Membership.objects.count(), 2)
            for model in (
                AcademicYear,
                Level,
                Series,
                Subject,
                Curriculum,
                CurriculumSubject,
                SchoolClass,
                ClassSubject,
                Student,
                StudentGuardian,
                Enrollment,
            ):
                with self.subTest(model=model.__name__):
                    self.assertEqual(model.objects.count(), 1)
            self.assertEqual(Guardian.objects.count(), 1)

    def test_create_requires_scope_and_rejects_cross_school_insert(self):
        with self.assertRaises(RuntimeError):
            Student.objects.create(
                school=self.school_a, first_name="No", last_name="Scope"
            )

        with tenant_scope(self.org.pk, self.school_a.pk):
            with self.assertRaises(RuntimeError):
                Student.objects.create(
                    school=self.school_other, first_name="Cross", last_name="Tenant"
                )
            self.assertEqual(Student.objects.count(), 1)

            student = Student.all_objects.get(school=self.school_a)
            with self.assertRaises(RuntimeError):
                Student.objects.filter(pk=student.pk).update(
                    school=self.school_other
                )
            student.refresh_from_db()
            self.assertEqual(student.school_id, self.school_a.pk)
