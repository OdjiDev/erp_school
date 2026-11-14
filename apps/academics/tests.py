from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.common.tenancy import tenant_scope
from apps.tenancy.models import Organization, School

from .models import (
    AcademicYear,
    Curriculum,
    CurriculumSubject,
    Level,
    SchoolClass,
    Series,
    Subject,
)


class AcademicStructureTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe A", slug="groupe-a")
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
        self.subject = Subject.all_objects.create(
            school=self.school, code="FR", name="Français"
        )

    def make_class(self, section="A", **kwargs):
        defaults = {
            "school": self.school,
            "academic_year": self.year,
            "level": self.level,
            "series": self.series,
            "section": section,
        }
        defaults.update(kwargs)
        return SchoolClass.all_objects.create(**defaults)

    def test_parallel_classes_are_allowed(self):
        first = self.make_class("A")
        second = self.make_class("B")

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(
            SchoolClass.all_objects.filter(
                school=self.school, level=self.level, series=self.series
            ).count(),
            2,
        )

    def test_class_is_unique_per_year_level_series_section(self):
        self.make_class("A")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_class("A")

    def test_same_class_name_allowed_in_another_school(self):
        other_year = AcademicYear.all_objects.create(
            school=self.other_school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
        )
        other_level = Level.all_objects.create(
            school=self.other_school, code="11", name="11ème", order=2
        )
        other_series = Series.all_objects.create(
            level=other_level, code="LET", name="Lettres"
        )

        self.make_class("A")
        self.make_class(
            "A",
            school=self.other_school,
            academic_year=other_year,
            level=other_level,
            series=other_series,
        )

        self.assertEqual(SchoolClass.all_objects.filter(section="A").count(), 2)

    def test_default_capacity_is_100(self):
        self.assertEqual(self.make_class().capacity, 100)

    def test_display_name_is_generated(self):
        self.assertEqual(self.make_class("A").display_name, "11ème A")

    def test_curriculum_and_coefficients(self):
        curriculum = Curriculum.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
        )
        CurriculumSubject.all_objects.create(
            curriculum=curriculum, subject=self.subject, coefficient=Decimal("4")
        )

        with tenant_scope(self.org.pk, self.school.pk):
            self.assertEqual(curriculum.curriculum_subjects.count(), 1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CurriculumSubject.all_objects.create(
                curriculum=curriculum,
                subject=self.subject,
                coefficient=Decimal("4"),
            )

    def test_coefficient_must_be_positive(self):
        curriculum = Curriculum.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
        )
        math = Subject.all_objects.create(school=self.school, code="MATH", name="Maths")

        with self.assertRaises(IntegrityError), transaction.atomic():
            CurriculumSubject.all_objects.create(
                curriculum=curriculum, subject=math, coefficient=Decimal("-1")
            )

    def test_series_must_belong_to_level(self):
        other_level = Level.all_objects.create(
            school=self.school, code="10", name="10ème", order=1
        )
        curriculum = Curriculum(
            school=self.school,
            academic_year=self.year,
            level=other_level,
            series=self.series,
        )

        with self.assertRaises(ValidationError):
            curriculum.full_clean()

    def test_school_class_rejects_series_from_another_level(self):
        other_level = Level.all_objects.create(
            school=self.school, code="10", name="10ème", order=1
        )
        school_class = SchoolClass(
            school=self.school,
            academic_year=self.year,
            level=other_level,
            series=self.series,
            section="A",
        )

        with self.assertRaises(ValidationError):
            school_class.full_clean()
