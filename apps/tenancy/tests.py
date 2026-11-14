from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Organization, School


class SchoolIdentityTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe A", slug="groupe-a")
        self.other_org = Organization.all_objects.create(name="Groupe B", slug="groupe-b")

    def test_same_name_schools_allowed_with_distinct_codes(self):
        first = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-1"
        )
        second = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-2"
        )

        self.assertEqual(
            School.all_objects.filter(
                organization=self.org, name="Lycée Excellence"
            ).count(),
            2,
        )
        self.assertIn("EXC-1", str(first))
        self.assertIn("EXC-2", str(second))

    def test_school_code_unique_per_organization(self):
        School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-1"
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            School.all_objects.create(
                organization=self.org, name="Autre nom", code="EXC-1"
            )

    def test_same_code_allowed_in_another_organization(self):
        School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-1"
        )
        School.all_objects.create(
            organization=self.other_org, name="Lycée Excellence", code="EXC-1"
        )

        self.assertEqual(School.all_objects.filter(code="EXC-1").count(), 2)

    def test_school_slug_is_generated(self):
        school = School.all_objects.create(
            organization=self.org, name="Lycée Excellence", code="EXC-3"
        )
        self.assertTrue(school.slug)
        self.assertIn("exc-3", school.slug)
