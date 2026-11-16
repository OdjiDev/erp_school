from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Level, Series
from apps.tenancy.models import Membership, Organization, Role, School

User = get_user_model()


class StructureManagementTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe Structure")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Structure", code="STR-1"
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
            username="direction-structure", password=None
        )
        Membership.all_objects.create(
            user=self.user,
            organization=self.org,
            school=self.school,
            role=Role.SCHOOL_ADMIN,
        )
        self.client.force_login(self.user)

    def school_url(self, name="structure", **kwargs):
        return reverse(
            f"school:{name}",
            kwargs={
                "org_slug": self.school.organization.slug,
                "school_code": self.school.code,
                **kwargs,
            },
        )

    def test_structure_page_lists_years_levels_and_series(self):
        response = self.client.get(self.school_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026-2027")
        self.assertContains(response, "Courante")
        self.assertContains(response, "11ème")
        self.assertContains(response, "Lettres")

    def test_create_academic_year_and_set_current(self):
        response = self.client.post(
            self.school_url("structure_year_create"),
            {
                "name": "2027-2028",
                "start_date": "2027-10-01",
                "end_date": "2028-06-30",
                "is_current": "on",
            },
        )

        self.assertRedirects(response, self.school_url())
        new_year = AcademicYear.all_objects.get(
            school=self.school, name="2027-2028"
        )
        self.assertTrue(new_year.is_current)
        self.year.refresh_from_db()
        self.assertFalse(self.year.is_current)

    def test_duplicate_academic_year_is_rejected(self):
        response = self.client.post(
            self.school_url("structure_year_create"),
            {
                "name": "2026-2027",
                "start_date": "2026-10-01",
                "end_date": "2027-06-30",
                "is_current": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "existe déjà")
        self.assertEqual(
            AcademicYear.all_objects.filter(school=self.school).count(), 1
        )

    def test_academic_year_name_format_is_rejected(self):
        response = self.client.post(
            self.school_url("structure_year_create"),
            {
                "name": "2027/2028",
                "start_date": "2027-10-01",
                "end_date": "2028-06-30",
                "is_current": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "format AAAA-AAAA")
        self.assertEqual(
            AcademicYear.all_objects.filter(school=self.school).count(), 1
        )

    def test_academic_year_name_must_be_consecutive(self):
        response = self.client.post(
            self.school_url("structure_year_create"),
            {
                "name": "2027-2029",
                "start_date": "2027-10-01",
                "end_date": "2029-06-30",
                "is_current": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "consécutives")
        self.assertEqual(
            AcademicYear.all_objects.filter(school=self.school).count(), 1
        )

    def test_academic_year_name_is_normalized(self):
        response = self.client.post(
            self.school_url("structure_year_create"),
            {
                "name": " 2027 - 2028 ",
                "start_date": "2027-10-01",
                "end_date": "2028-06-30",
                "is_current": "on",
            },
        )

        self.assertRedirects(response, self.school_url())
        new_year = AcademicYear.all_objects.get(
            school=self.school, name="2027-2028"
        )
        self.assertTrue(new_year.is_current)

    def test_edit_rejects_invalid_academic_year_name(self):
        response = self.client.post(
            self.school_url(
                "structure_year_edit", year_id=self.year.id
            ),
            {
                "name": "2026/2027",
                "start_date": "2026-10-01",
                "end_date": "2027-06-30",
                "is_current": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "format AAAA-AAAA")
        self.year.refresh_from_db()
        self.assertEqual(self.year.name, "2026-2027")

    def test_edit_academic_year(self):
        response = self.client.post(
            self.school_url(
                "structure_year_edit", year_id=self.year.id
            ),
            {
                "name": "2026-2027",
                "start_date": "2026-10-05",
                "end_date": "2027-07-05",
                "is_current": "on",
            },
        )

        self.assertRedirects(response, self.school_url())
        self.year.refresh_from_db()
        self.assertEqual(self.year.start_date, date(2026, 10, 5))
        self.assertEqual(self.year.end_date, date(2027, 7, 5))

    def test_year_end_date_must_be_after_start_date(self):
        response = self.client.post(
            self.school_url("structure_year_create"),
            {
                "name": "2027-2028",
                "start_date": "2027-10-01",
                "end_date": "2027-09-30",
                "is_current": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "postérieure")
        self.assertEqual(
            AcademicYear.all_objects.filter(school=self.school).count(), 1
        )

    def test_structure_page_flags_missing_current_year(self):
        AcademicYear.all_objects.filter(pk=self.year.pk).update(
            is_current=False
        )

        response = self.client.get(self.school_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, ">Courante<")
        self.assertContains(
            response, "Aucune année n'est marquée comme courante"
        )

    def test_create_level_normalizes_code(self):
        response = self.client.post(
            self.school_url("structure_level_create"),
            {"code": "tle", "name": "Terminale", "order": 3},
        )

        self.assertRedirects(response, self.school_url())
        level = Level.all_objects.get(school=self.school, code="TLE")
        self.assertEqual(level.name, "Terminale")
        self.assertEqual(level.order, 3)

    def test_duplicate_level_code_is_rejected(self):
        response = self.client.post(
            self.school_url("structure_level_create"),
            {"code": "11", "name": "Double niveau", "order": 3},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "existe déjà")
        self.assertEqual(
            Level.all_objects.filter(school=self.school).count(), 1
        )

    def test_create_series_for_level(self):
        response = self.client.post(
            self.school_url(
                "structure_series_create", level_id=self.level.id
            ),
            {"level": self.level.id, "code": "sci", "name": "Sciences"},
        )

        self.assertRedirects(response, self.school_url())
        series = Series.all_objects.get(level=self.level, code="SCI")
        self.assertEqual(series.name, "Sciences")

    def test_duplicate_series_code_is_rejected(self):
        response = self.client.post(
            self.school_url(
                "structure_series_create", level_id=self.level.id
            ),
            {"level": self.level.id, "code": "LET", "name": "Doublon"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "existe déjà")
        self.assertEqual(
            Series.all_objects.filter(level=self.level).count(), 1
        )

    def test_edit_series(self):
        response = self.client.post(
            self.school_url(
                "structure_series_edit", series_id=self.series.id
            ),
            {
                "level": self.level.id,
                "code": "LET",
                "name": "Lettres et langues",
            },
        )

        self.assertRedirects(response, self.school_url())
        self.series.refresh_from_db()
        self.assertEqual(self.series.name, "Lettres et langues")

    def test_series_cannot_be_created_for_another_school(self):
        other_org = Organization.all_objects.create(name="Groupe Étranger")
        other_school = School.all_objects.create(
            organization=other_org, name="Lycée Étranger", code="ETR-1"
        )
        other_level = Level.all_objects.create(
            school=other_school, code="11", name="11ème", order=1
        )

        response = self.client.get(
            self.school_url(
                "structure_series_create", level_id=other_level.id
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_teacher_cannot_manage_structure(self):
        teacher = User.objects.create_user(
            username="enseignant-structure", password=None
        )
        Membership.all_objects.create(
            user=teacher,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )
        self.client.force_login(teacher)

        response = self.client.get(self.school_url())

        self.assertEqual(response.status_code, 403)

    def test_teacher_dashboard_hides_structure_link(self):
        teacher = User.objects.create_user(
            username="enseignant-menu", password=None
        )
        Membership.all_objects.create(
            user=teacher,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )
        self.client.force_login(teacher)

        response = self.client.get(
            reverse(
                "school:dashboard",
                kwargs={
                    "org_slug": self.school.organization.slug,
                    "school_code": self.school.code,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.school_url())
        self.assertNotContains(
            response, "Gérer la structure académique"
        )

    def test_manager_dashboard_links_to_structure(self):
        response = self.client.get(
            reverse(
                "school:dashboard",
                kwargs={
                    "org_slug": self.school.organization.slug,
                    "school_code": self.school.code,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.school_url())

    def test_user_from_another_school_is_denied(self):
        other_org = Organization.all_objects.create(name="Groupe Autre")
        other_school = School.all_objects.create(
            organization=other_org, name="Autre école", code="AUT-9"
        )
        other_user = User.objects.create_user(
            username="autre-direction", password=None
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
