from django.core.management import call_command
from django.test import TestCase

from apps.academics.models import SchoolClass
from apps.students.models import Enrollment, Student
from apps.tenancy.models import Organization, School


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)

        organization = Organization.all_objects.get(slug="demo")
        schools = School.all_objects.filter(organization=organization)
        self.assertEqual(schools.count(), 2)
        self.assertEqual(
            set(schools.values_list("code", flat=True)),
            {"DEMO-A", "DEMO-B"},
        )
        self.assertEqual(
            Student.all_objects.filter(school__organization=organization).count(),
            16,
        )
        self.assertEqual(
            SchoolClass.all_objects.filter(
                school__organization=organization
            ).count(),
            22,
        )
        self.assertEqual(
            Enrollment.all_objects.filter(
                school__organization=organization
            ).count(),
            16,
        )
