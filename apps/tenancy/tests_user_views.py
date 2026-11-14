from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.academics.models import (
    AcademicYear,
    ClassSubject,
    Level,
    SchoolClass,
    Series,
    Subject,
)
from apps.tenancy.models import Membership, Organization, Role, School

User = get_user_model()

PASSWORD = "V7!plateforme2026"


class UserManagementTestBase(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe Utilisateurs")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Utilisateurs", code="USR-1"
        )
        self.other_school = School.all_objects.create(
            organization=self.org, name="Lycée Utilisateurs", code="USR-2"
        )
        self.other_org = Organization.all_objects.create(name="Groupe Externe")
        self.foreign_school = School.all_objects.create(
            organization=self.other_org, name="Lycée Externe", code="EXT-9"
        )

        self.org_admin = User.objects.create_user(
            username="admin-client", password=None,
            first_name="Awa", last_name="Traoré",
        )
        Membership.all_objects.create(
            user=self.org_admin,
            organization=self.org,
            role=Role.ORG_ADMIN,
        )
        self.school_admin = User.objects.create_user(
            username="direction-ecole", password=None,
            first_name="Moussa", last_name="Diarra",
        )
        self.school_admin_membership = Membership.all_objects.create(
            user=self.school_admin,
            organization=self.org,
            school=self.school,
            role=Role.SCHOOL_ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="enseignant-utilisateurs", password=None,
            first_name="Ibrahim", last_name="Konaté",
        )
        Membership.all_objects.create(
            user=self.teacher,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )
        self.secretary = User.objects.create_user(
            username="secretaire-ecole", password=None,
            first_name="Fatoumata", last_name="Sissoko",
        )
        self.secretary_membership = Membership.all_objects.create(
            user=self.secretary,
            organization=self.org,
            school=self.school,
            role=Role.SECRETARY,
        )
        self.other_school_user = User.objects.create_user(
            username="secretaire-autre-ecole", password=None,
        )
        self.other_school_membership = Membership.all_objects.create(
            user=self.other_school_user,
            organization=self.org,
            school=self.other_school,
            role=Role.SECRETARY,
        )
        self.foreign_user = User.objects.create_user(
            username="utilisateur-externe", password=None,
        )
        Membership.all_objects.create(
            user=self.foreign_user,
            organization=self.other_org,
            school=self.foreign_school,
            role=Role.SCHOOL_ADMIN,
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

        self.client.force_login(self.school_admin)

    def url(self, name, **kwargs):
        return reverse(
            f"school:{name}",
            kwargs={
                "org_slug": self.school.organization.slug,
                "school_code": self.school.code,
                **kwargs,
            },
        )

    def user_payload(self, **overrides):
        payload = {
            "username": "nouveau.compte",
            "first_name": "Nouveau",
            "last_name": "Compte",
            "email": "",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "role": Role.SECRETARY,
            "scope": "school",
        }
        payload.update(overrides)
        return payload


class UserListAndCreateTests(UserManagementTestBase):
    def test_school_admin_sees_own_school_and_org_roles_only(self):
        response = self.client.get(self.url("user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.school_admin.get_username())
        self.assertContains(response, self.org_admin.get_username())
        self.assertNotContains(response, self.other_school_user.get_username())
        self.assertNotContains(response, self.foreign_user.get_username())

    def test_school_admin_cannot_create_org_admin(self):
        response = self.client.post(
            self.url("user_create"),
            self.user_payload(
                username="escalade",
                role=Role.ORG_ADMIN,
                scope="organization",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("role", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="escalade").exists())

    def test_school_admin_creates_school_user(self):
        response = self.client.post(
            self.url("user_create"), self.user_payload()
        )

        user = User.objects.get(username="nouveau.compte")
        self.assertRedirects(
            response, self.url("user_edit", user_id=user.id)
        )
        membership = Membership.all_objects.get(user=user)
        self.assertEqual(membership.role, Role.SECRETARY)
        self.assertEqual(membership.school, self.school)
        self.assertTrue(user.check_password(PASSWORD))

    def test_org_admin_creates_org_wide_user(self):
        self.client.force_login(self.org_admin)

        response = self.client.post(
            self.url("user_create"),
            self.user_payload(
                username="admin.organisation",
                role=Role.ORG_ADMIN,
                scope="organization",
            ),
        )

        user = User.objects.get(username="admin.organisation")
        self.assertEqual(response.status_code, 302)
        membership = Membership.all_objects.get(user=user)
        self.assertEqual(membership.role, Role.ORG_ADMIN)
        self.assertIsNone(membership.school)

    def test_teacher_cannot_list_users(self):
        self.client.force_login(self.teacher)

        response = self.client.get(self.url("user_list"))

        self.assertEqual(response.status_code, 403)


class UserScopeTests(UserManagementTestBase):
    def test_school_admin_cannot_open_org_wide_only_user(self):
        response = self.client.get(
            self.url("user_edit", user_id=self.org_admin.id)
        )

        self.assertEqual(response.status_code, 404)

    def test_school_admin_cannot_reset_org_admin_password(self):
        response = self.client.get(
            self.url(
                "user_password_reset", user_id=self.org_admin.id
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_school_admin_can_edit_school_user(self):
        response = self.client.get(
            self.url("user_edit", user_id=self.secretary.id)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.secretary.get_username())

    def test_school_admin_cannot_edit_foreign_user(self):
        response = self.client.get(
            self.url("user_edit", user_id=self.foreign_user.id)
        )

        self.assertEqual(response.status_code, 404)

    def test_school_admin_cannot_edit_org_wide_membership(self):
        membership = Membership.all_objects.get(
            user=self.org_admin, role=Role.ORG_ADMIN
        )

        response = self.client.get(
            self.url("membership_edit", membership_id=membership.id)
        )

        self.assertEqual(response.status_code, 404)

    def test_org_admin_cannot_edit_role_from_another_school(self):
        self.client.force_login(self.org_admin)

        response = self.client.get(
            self.url(
                "membership_edit",
                membership_id=self.other_school_membership.id,
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_org_admin_cannot_toggle_role_from_another_school(self):
        self.client.force_login(self.org_admin)

        response = self.client.post(
            self.url(
                "membership_toggle",
                membership_id=self.other_school_membership.id,
            )
        )

        self.assertEqual(response.status_code, 404)
        self.other_school_membership.refresh_from_db()
        self.assertTrue(self.other_school_membership.is_active)

    def test_school_admin_cannot_assign_org_admin_membership(self):
        response = self.client.post(
            self.url(
                "membership_create", user_id=self.secretary.id
            ),
            {
                "role": Role.ORG_ADMIN,
                "school": self.school.id,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("role", response.context["form"].errors)
        self.assertFalse(
            Membership.all_objects.filter(
                user=self.secretary, role=Role.ORG_ADMIN
            ).exists()
        )

    def test_school_admin_membership_scope_is_forced_to_school(self):
        response = self.client.post(
            self.url(
                "membership_create", user_id=self.secretary.id
            ),
            {
                "role": Role.ACCOUNTANT,
                "school": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        membership = Membership.all_objects.get(
            user=self.secretary, role=Role.ACCOUNTANT
        )
        self.assertEqual(membership.school, self.school)

    def test_org_admin_can_assign_org_wide_role(self):
        self.client.force_login(self.org_admin)

        response = self.client.post(
            self.url(
                "membership_create", user_id=self.secretary.id
            ),
            {
                "role": Role.ORG_ADMIN,
                "school": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        membership = Membership.all_objects.get(
            user=self.secretary,
            role=Role.ORG_ADMIN,
            school__isnull=True,
        )
        self.assertEqual(membership.organization, self.org)

    def test_membership_form_rejects_another_school(self):
        self.client.force_login(self.org_admin)

        response = self.client.post(
            self.url(
                "membership_create", user_id=self.secretary.id
            ),
            {
                "role": Role.ACCOUNTANT,
                "school": self.other_school.id,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("school", response.context["form"].errors)
        self.assertFalse(
            Membership.all_objects.filter(
                user=self.secretary,
                role=Role.ACCOUNTANT,
                school=self.other_school,
            ).exists()
        )


class UserSelfProtectionTests(UserManagementTestBase):
    def test_admin_cannot_remove_own_user_management_access(self):
        response = self.client.post(
            self.url(
                "membership_edit",
                membership_id=self.school_admin_membership.id,
            ),
            {
                "role": Role.TEACHER,
                "school": self.school.id,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "retirer votre propre accès"
        )
        self.school_admin_membership.refresh_from_db()
        self.assertEqual(
            self.school_admin_membership.role, Role.SCHOOL_ADMIN
        )

    def test_admin_cannot_deactivate_own_account_from_edit_form(self):
        response = self.client.post(
            self.url("user_edit", user_id=self.school_admin.id),
            {
                "first_name": "Moussa",
                "last_name": "Diarra",
                "email": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.school_admin.refresh_from_db()
        self.assertTrue(self.school_admin.is_active)

    def test_admin_cannot_toggle_own_role(self):
        response = self.client.post(
            self.url(
                "membership_toggle",
                membership_id=self.school_admin_membership.id,
            )
        )

        self.assertEqual(response.status_code, 302)
        self.school_admin_membership.refresh_from_db()
        self.assertTrue(self.school_admin_membership.is_active)

    def test_admin_can_deactivate_another_school_user(self):
        response = self.client.post(
            self.url(
                "membership_toggle",
                membership_id=self.secretary_membership.id,
            )
        )

        self.assertEqual(response.status_code, 302)
        self.secretary_membership.refresh_from_db()
        self.assertFalse(self.secretary_membership.is_active)

    def test_password_reset_updates_target_password(self):
        response = self.client.post(
            self.url(
                "user_password_reset", user_id=self.secretary.id
            ),
            {
                "new_password1": PASSWORD,
                "new_password2": PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.secretary.refresh_from_db()
        self.assertTrue(self.secretary.check_password(PASSWORD))


class TeacherListTests(UserManagementTestBase):
    def test_teacher_list_counts_assignments(self):
        subject = Subject.all_objects.create(
            school=self.school, code="FR", name="Français"
        )
        ClassSubject.all_objects.create(
            school_class=self.school_class,
            subject=subject,
            teacher=self.teacher,
        )

        response = self.client.get(self.url("teacher_list"))

        self.assertEqual(response.status_code, 200)
        teachers = list(response.context["teachers"])
        self.assertEqual(len(teachers), 1)
        self.assertEqual(teachers[0], self.teacher)
        self.assertEqual(teachers[0].assignment_count, 1)
        self.assertContains(response, "Ibrahim Konaté")

    def test_teacher_cannot_open_teacher_list(self):
        self.client.force_login(self.teacher)

        response = self.client.get(self.url("teacher_list"))

        self.assertEqual(response.status_code, 403)
