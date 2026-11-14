from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Level, SchoolClass, Series
from apps.students.models import Enrollment, Student

from .models import Membership, Organization, Role, School

User = get_user_model()


class SchoolAccessTests(TestCase):
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
            organization=self.other_org, name="École Étrangère", code="FOR-1"
        )

        self.org_user = User.objects.create_user(
            username="org-admin", password=None
        )
        Membership.all_objects.create(
            user=self.org_user,
            organization=self.org,
            role=Role.SCHOOL_ADMIN,
        )

        self.school_user = User.objects.create_user(
            username="secretaire", password=None
        )
        Membership.all_objects.create(
            user=self.school_user,
            organization=self.org,
            school=self.school,
            role=Role.SECRETARY,
        )

        self.foreign_user = User.objects.create_user(
            username="foreign-admin", password=None
        )
        Membership.all_objects.create(
            user=self.foreign_user,
            organization=self.other_org,
            role=Role.SCHOOL_ADMIN,
        )

        self.parent_user = User.objects.create_user(
            username="parent", password=None
        )
        Membership.all_objects.create(
            user=self.parent_user,
            organization=self.org,
            role=Role.PARENT,
        )

        self.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password=None
        )

        self.year = self._create_year(self.school, "2026-2027", is_current=True)
        self.level = Level.all_objects.create(
            school=self.school, code="11", name="11ème", order=2
        )
        self.series = Series.all_objects.create(
            level=self.level, code="LET", name="Lettres"
        )
        self.class_a = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
            capacity=10,
        )
        self.class_b = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="B",
            capacity=10,
        )

        self.other_year = self._create_year(
            self.same_name_school, "2026-2027", is_current=True
        )
        self.other_level = Level.all_objects.create(
            school=self.same_name_school, code="11", name="11ème", order=2
        )
        self.other_series = Series.all_objects.create(
            level=self.other_level, code="LET", name="Lettres"
        )
        self.other_class = SchoolClass.all_objects.create(
            school=self.same_name_school,
            academic_year=self.other_year,
            level=self.other_level,
            series=self.other_series,
            section="A",
        )

        self.student = Student.all_objects.create(
            school=self.school,
            matricule="M001",
            first_name="Awa",
            last_name="Traoré",
        )
        self.student_without_class = Student.all_objects.create(
            school=self.school,
            matricule="M002",
            first_name="Fatoumata",
            last_name="Keita",
        )
        self.other_student = Student.all_objects.create(
            school=self.same_name_school,
            matricule="M001",
            first_name="Ibrahim",
            last_name="Diarra",
        )
        Enrollment.all_objects.create(
            student=self.student,
            academic_year=self.year,
            school_class=self.class_a,
        )
        Enrollment.all_objects.create(
            student=self.other_student,
            academic_year=self.other_year,
            school_class=self.other_class,
        )

    def _create_year(self, school, name, is_current=False):
        return AcademicYear.all_objects.create(
            school=school,
            name=name,
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
            is_current=is_current,
        )

    def school_url(self, name, school, **kwargs):
        return reverse(
            f"school:{name}",
            kwargs={
                "org_slug": school.organization.slug,
                "school_code": school.code,
                **kwargs,
            },
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.school_url("dashboard", self.school))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("school:login"), response.url)

    def test_org_wide_member_can_access_both_same_name_schools(self):
        self.client.force_login(self.org_user)

        first = self.client.get(self.school_url("dashboard", self.school))
        second = self.client.get(
            self.school_url("dashboard", self.same_name_school)
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

    def test_school_member_cannot_access_sibling_school(self):
        self.client.force_login(self.school_user)

        allowed = self.client.get(self.school_url("dashboard", self.school))
        denied = self.client.get(
            self.school_url("dashboard", self.same_name_school)
        )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_other_organization_member_is_denied(self):
        self.client.force_login(self.foreign_user)

        response = self.client.get(self.school_url("dashboard", self.school))

        self.assertEqual(response.status_code, 403)

    def test_parent_role_is_denied_from_school_back_office(self):
        self.client.force_login(self.parent_user)

        response = self.client.get(self.school_url("dashboard", self.school))

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_any_school(self):
        self.client.force_login(self.superuser)

        response = self.client.get(
            self.school_url("dashboard", self.foreign_school)
        )

        self.assertEqual(response.status_code, 200)

    def test_home_lists_only_accessible_schools(self):
        self.client.force_login(self.org_user)

        response = self.client.get(reverse("school:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "EXC-1")
        self.assertContains(response, "EXC-2")
        self.assertNotContains(response, "FOR-1")
        self.assertNotContains(response, "École Étrangère")

    def test_home_redirects_single_school_user(self):
        self.client.force_login(self.school_user)

        response = self.client.get(reverse("school:home"))

        self.assertRedirects(
            response, self.school_url("dashboard", self.school)
        )

    def test_organization_home_lists_schools_of_the_organization(self):
        self.client.force_login(self.org_user)

        response = self.client.get(
            reverse(
                "school:organization_home",
                kwargs={"org_slug": self.org.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["schools"]), 2)

    def test_user_without_membership_gets_403(self):
        user = User.objects.create_user(username="sans-acces", password=None)
        self.client.force_login(user)

        response = self.client.get(reverse("school:home"))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "tenancy/no_access.html")

    def test_student_list_is_scoped_to_school(self):
        self.client.force_login(self.org_user)

        response = self.client.get(self.school_url("student_list", self.school))

        self.assertEqual(response.status_code, 200)
        student_ids = {student.id for student in response.context["students"]}
        self.assertIn(self.student.id, student_ids)
        self.assertIn(self.student_without_class.id, student_ids)
        self.assertNotIn(self.other_student.id, student_ids)
        self.assertContains(response, "Traoré")
        self.assertNotContains(response, "Diarra")

    def test_student_search_filters_within_school(self):
        self.client.force_login(self.org_user)

        response = self.client.get(
            self.school_url("student_list", self.school), {"q": "Keita"}
        )

        student_ids = {student.id for student in response.context["students"]}
        self.assertEqual(student_ids, {self.student_without_class.id})

    def test_student_detail_cannot_cross_school_boundary(self):
        self.client.force_login(self.org_user)

        response = self.client.get(
            self.school_url(
                "student_detail", self.school, student_id=self.other_student.id
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_student_detail_shows_guardians_and_enrollment(self):
        self.client.force_login(self.org_user)

        response = self.client.get(
            self.school_url(
                "student_detail", self.school, student_id=self.student.id
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awa Traoré")
        self.assertContains(response, "11ème A")

    def test_class_list_is_scoped_to_school_and_year(self):
        self.client.force_login(self.org_user)

        response = self.client.get(self.school_url("class_list", self.school))

        self.assertEqual(response.status_code, 200)
        classes = list(response.context["classes"])
        self.assertEqual(len(classes), 2)
        self.assertTrue(all(item.school_id == self.school.id for item in classes))
        self.assertEqual(
            {item.display_name for item in classes}, {"11ème A", "11ème B"}
        )

    def test_class_list_rejects_year_from_another_school(self):
        self.client.force_login(self.org_user)

        response = self.client.get(
            self.school_url("class_list", self.school),
            {"annee": str(self.other_year.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_year"], self.year)

    def test_dashboard_counts_are_scoped_to_school(self):
        self.client.force_login(self.org_user)

        response = self.client.get(self.school_url("dashboard", self.school))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["student_count"], 2)
        self.assertEqual(response.context["class_count"], 2)
        self.assertEqual(response.context["enrollment_count"], 1)
        self.assertEqual(response.context["capacity"], 20)
