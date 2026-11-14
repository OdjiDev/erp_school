from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
from apps.common.tenancy import tenant_scope
from apps.students.models import Enrollment, Student
from apps.tenancy.models import Membership, Organization, Role, School

from .models import (
    Assessment,
    BulletinSnapshot,
    Deliberation,
    Grade,
    GradingPeriod,
    GradingPeriodAction,
    PeriodActionType,
)
from .services import build_bulletins


User = get_user_model()


class GradingPeriodLifecycleTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe Cycle")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Cycle", code="CYC-1"
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
        self.school_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="A",
        )
        self.admin = User.objects.create_user(username="direction-cycle")
        self.teacher = User.objects.create_user(username="enseignant-cycle")
        Membership.all_objects.create(
            user=self.admin,
            organization=self.org,
            school=self.school,
            role=Role.SCHOOL_ADMIN,
        )
        Membership.all_objects.create(
            user=self.teacher,
            organization=self.org,
            school=self.school,
            role=Role.TEACHER,
        )
        self.class_subject = ClassSubject.all_objects.create(
            school_class=self.school_class,
            subject=self.subject,
            teacher=self.teacher,
        )
        self.curriculum = Curriculum.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
        )
        CurriculumSubject.all_objects.create(
            curriculum=self.curriculum,
            subject=self.subject,
            coefficient=Decimal("4"),
        )
        self.period = GradingPeriod.all_objects.create(
            school=self.school,
            academic_year=self.year,
            code="T1",
            name="Trimestre 1",
            sequence=1,
        )
        self.students = [
            Student.all_objects.create(
                school=self.school,
                matricule="CYC-001",
                first_name="Awa",
                last_name="Traoré",
            ),
            Student.all_objects.create(
                school=self.school,
                matricule="CYC-002",
                first_name="Boubacar",
                last_name="Diarra",
            ),
        ]
        self.enrollments = [
            Enrollment.all_objects.create(
                student=student,
                academic_year=self.year,
                school_class=self.school_class,
            )
            for student in self.students
        ]
        self.close_url = self.url(
            "grading_period_close", period_id=self.period.pk
        )
        self.reopen_url = self.url(
            "grading_period_reopen", period_id=self.period.pk
        )
        self.client.force_login(self.admin)

    def url(self, name, **kwargs):
        return reverse(
            f"school:{name}",
            kwargs={
                "org_slug": self.org.slug,
                "school_code": self.school.code,
                **kwargs,
            },
        )

    def make_assessment(
        self,
        title="Composition",
        published=True,
        scores=(16, 12),
        class_subject=None,
    ):
        class_subject = class_subject or self.class_subject
        if class_subject.pk == self.class_subject.pk:
            enrollments = list(self.enrollments)
        else:
            enrollments = list(
                Enrollment.all_objects.filter(
                    school_class=class_subject.school_class, status="active"
                ).order_by("student__last_name", "student__first_name")
            )
        assessment = Assessment.all_objects.create(
            school=self.school,
            class_subject=class_subject,
            period=self.period,
            title=title,
            assessment_type="composition",
            held_on=date(2026, 11, 10),
            max_score=Decimal("20"),
            weight=Decimal("1"),
            created_by=self.admin,
        )
        for enrollment, score in zip(enrollments, scores):
            Grade.all_objects.create(
                school=self.school,
                assessment=assessment,
                enrollment=enrollment,
                score=Decimal(str(score)),
                status="graded",
            )
        if published:
            assessment.is_published = True
            assessment.published_at = timezone.now()
            assessment.published_by = self.admin
            assessment.save(
                update_fields=[
                    "is_published",
                    "published_at",
                    "published_by",
                    "updated_at",
                ]
            )
        return assessment

    def add_other_class_with_enrollment(self):
        other_class = SchoolClass.all_objects.create(
            school=self.school,
            academic_year=self.year,
            level=self.level,
            series=self.series,
            section="B",
        )
        other_subject = Subject.all_objects.create(
            school=self.school, code="HG", name="Histoire-Géographie"
        )
        other_class_subject = ClassSubject.all_objects.create(
            school_class=other_class,
            subject=other_subject,
            teacher=self.teacher,
        )
        student = Student.all_objects.create(
            school=self.school,
            matricule="CYC-003",
            first_name="Fatou",
            last_name="Keïta",
        )
        enrollment = Enrollment.all_objects.create(
            student=student,
            academic_year=self.year,
            school_class=other_class,
        )
        return other_class, other_class_subject, enrollment

    def set_grade(self, assessment, enrollment, score):
        grade = Grade.all_objects.get(
            assessment=assessment, enrollment=enrollment
        )
        grade.score = Decimal(str(score))
        grade.save()
        return grade

    def get_snapshot(self, enrollment, version):
        return BulletinSnapshot.all_objects.get(
            period=self.period, enrollment=enrollment, version=version
        )

    def test_close_refuses_a_period_without_published_assessment(self):
        response = self.client.post(self.close_url, follow=True)

        self.period.refresh_from_db()
        self.assertFalse(self.period.is_closed)
        self.assertContains(response, "Clôture refusée")
        self.assertContains(
            response, "publiez au moins une évaluation pour cette période"
        )
        self.assertFalse(
            BulletinSnapshot.all_objects.filter(period=self.period).exists()
        )
        self.assertFalse(
            GradingPeriodAction.all_objects.filter(period=self.period).exists()
        )

    def test_close_refuses_a_period_with_a_draft_assessment(self):
        self.make_assessment(title="Évaluation publiée")
        self.make_assessment(title="Brouillon", published=False, scores=())

        response = self.client.post(self.close_url, follow=True)

        self.period.refresh_from_db()
        self.assertFalse(self.period.is_closed)
        self.assertContains(response, "1 évaluation(s) ne sont pas publiées")
        self.assertFalse(
            BulletinSnapshot.all_objects.filter(period=self.period).exists()
        )

    def test_close_refuses_when_an_active_class_has_no_published_result(self):
        self.make_assessment()
        self.add_other_class_with_enrollment()

        response = self.client.post(self.close_url, follow=True)

        self.period.refresh_from_db()
        self.assertFalse(self.period.is_closed)
        self.assertContains(response, "1 classe(s) active(s)")
        self.assertFalse(
            BulletinSnapshot.all_objects.filter(period=self.period).exists()
        )

    def test_close_captures_bulletins_for_every_active_class(self):
        self.make_assessment()
        _, other_class_subject, other_enrollment = (
            self.add_other_class_with_enrollment()
        )
        self.make_assessment(
            title="Histoire",
            scores=(14,),
            class_subject=other_class_subject,
        )

        response = self.client.post(self.close_url, follow=True)

        self.assertContains(response, "3 bulletin(s) figé(s), version 1")
        self.assertEqual(
            BulletinSnapshot.all_objects.filter(period=self.period).count(), 3
        )
        self.assertTrue(
            BulletinSnapshot.all_objects.filter(
                period=self.period,
                enrollment=other_enrollment,
                version=1,
            ).exists()
        )

    def test_close_freezes_bulletins_and_records_the_action(self):
        self.make_assessment()
        Deliberation.all_objects.create(
            school=self.school,
            period=self.period,
            enrollment=self.enrollments[0],
            outcome="promoted",
            comment="Décision du conseil de classe.",
            decided_by=self.admin,
        )

        response = self.client.post(self.close_url, follow=True)

        self.period.refresh_from_db()
        self.assertTrue(self.period.is_closed)
        self.assertIsNotNone(self.period.closed_at)
        self.assertEqual(self.period.closed_by, self.admin)
        self.assertContains(response, "2 bulletin(s) figé(s), version 1")

        snapshots = BulletinSnapshot.all_objects.filter(period=self.period)
        self.assertEqual(snapshots.count(), 2)
        self.assertEqual({item.version for item in snapshots}, {1})

        awa_snapshot = self.get_snapshot(self.enrollments[0], 1)
        self.assertEqual(awa_snapshot.data["general_average"], "16.00")
        self.assertEqual(awa_snapshot.data["rank"], 1)
        self.assertEqual(awa_snapshot.data["deliberation_label"], "Admis / promu")

        action = GradingPeriodAction.all_objects.get(period=self.period)
        self.assertEqual(action.action, PeriodActionType.CLOSED)
        self.assertEqual(action.performed_by, self.admin)
        self.assertIn("2 bulletin(s) figé(s), version 1", action.reason)

    def test_closed_period_bulletins_are_immutable_even_if_notes_change(self):
        assessment = self.make_assessment()
        Deliberation.all_objects.create(
            school=self.school,
            period=self.period,
            enrollment=self.enrollments[0],
            outcome="promoted",
            decided_by=self.admin,
        )
        self.client.post(self.close_url)
        self.period.refresh_from_db()
        self.assertTrue(self.period.is_closed)

        self.set_grade(assessment, self.enrollments[0], 2)
        deliberation = Deliberation.all_objects.get(
            period=self.period, enrollment=self.enrollments[0]
        )
        deliberation.outcome = "retained"
        deliberation.save()

        with tenant_scope(self.org.pk, self.school.pk):
            bulletins = build_bulletins(self.school_class, self.period)

        awa = next(
            item
            for item in bulletins
            if item["enrollment"].pk == self.enrollments[0].pk
        )
        self.assertEqual(awa["general_average"], Decimal("16.00"))
        self.assertEqual(awa["rank"], 1)
        self.assertEqual(awa["deliberation_label"], "Admis / promu")

    def test_closing_an_already_closed_period_does_not_create_a_new_version(self):
        self.make_assessment()
        self.client.post(self.close_url)

        response = self.client.post(self.close_url, follow=True)

        self.assertContains(response, "déjà clôturée")
        self.assertEqual(
            BulletinSnapshot.all_objects.filter(period=self.period).count(), 2
        )
        self.assertEqual(
            GradingPeriodAction.all_objects.filter(
                period=self.period, action=PeriodActionType.CLOSED
            ).count(),
            1,
        )

    def test_reopen_requires_a_motivated_reason(self):
        self.make_assessment()
        self.client.post(self.close_url)

        response = self.client.post(self.reopen_url, {"reason": "court"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("reason", response.context["form"].errors)
        self.period.refresh_from_db()
        self.assertTrue(self.period.is_closed)
        self.assertFalse(
            GradingPeriodAction.all_objects.filter(
                period=self.period, action=PeriodActionType.REOPENED
            ).exists()
        )

    def test_reopen_clears_the_closure_and_records_the_reason(self):
        self.make_assessment()
        self.client.post(self.close_url)
        reason = "Erreur de saisie constatée après vérification des copies."

        response = self.client.post(
            self.reopen_url, {"reason": reason}, follow=True
        )

        self.period.refresh_from_db()
        self.assertFalse(self.period.is_closed)
        self.assertIsNone(self.period.closed_at)
        self.assertIsNone(self.period.closed_by)
        self.assertContains(response, "Période rouverte")
        action = GradingPeriodAction.all_objects.get(
            period=self.period, action=PeriodActionType.REOPENED
        )
        self.assertEqual(action.reason, reason)
        self.assertEqual(action.performed_by, self.admin)
        self.assertEqual(
            BulletinSnapshot.all_objects.filter(period=self.period).count(), 2
        )

    def test_reopening_an_open_period_is_a_noop(self):
        response = self.client.post(
            self.reopen_url,
            {"reason": "Réouverture demandée par la direction de l'école."},
            follow=True,
        )

        self.assertContains(response, "déjà ouverte")
        self.assertFalse(
            GradingPeriodAction.all_objects.filter(period=self.period).exists()
        )

    def test_second_closure_creates_a_new_snapshot_version(self):
        assessment = self.make_assessment()
        self.client.post(self.close_url)
        self.client.post(
            self.reopen_url,
            {"reason": "Correction demandée par le conseil de classe."},
        )
        self.set_grade(assessment, self.enrollments[0], 10)

        response = self.client.post(self.close_url, follow=True)

        self.assertContains(response, "2 bulletin(s) figé(s), version 2")
        first_version = self.get_snapshot(self.enrollments[0], 1)
        second_version = self.get_snapshot(self.enrollments[0], 2)
        self.assertEqual(first_version.data["general_average"], "16.00")
        self.assertEqual(first_version.data["rank"], 1)
        self.assertEqual(second_version.data["general_average"], "10.00")
        self.assertEqual(second_version.data["rank"], 2)
        self.assertEqual(
            BulletinSnapshot.all_objects.filter(period=self.period).count(), 4
        )
        self.assertEqual(
            GradingPeriodAction.all_objects.filter(
                period=self.period, action=PeriodActionType.CLOSED
            ).count(),
            2,
        )

        print_url = self.url(
            "report_card_print",
            enrollment_id=self.enrollments[0].pk,
            period_id=self.period.pk,
        )
        first_response = self.client.get(print_url, {"version": 1})
        second_response = self.client.get(print_url, {"version": 2})
        self.assertContains(first_response, "16,00")
        self.assertContains(first_response, "Version figée 1")
        self.assertContains(second_response, "10,00")
        self.assertContains(second_response, "Version figée 2")

    def test_closed_period_blocks_deliberation_and_grade_correction(self):
        assessment = self.make_assessment()
        self.client.post(self.close_url)

        deliberation_response = self.client.get(
            self.url(
                "deliberation_edit",
                enrollment_id=self.enrollments[0].pk,
                period_id=self.period.pk,
            )
        )
        correction_response = self.client.get(
            f"{self.url('gradebook', assessment_id=assessment.pk)}?corriger=1"
        )

        self.assertEqual(deliberation_response.status_code, 403)
        self.assertEqual(correction_response.status_code, 403)

    def test_period_snapshots_and_history_cannot_be_modified(self):
        self.make_assessment()
        self.client.post(self.close_url)
        snapshot = BulletinSnapshot.all_objects.filter(
            period=self.period
        ).first()
        action = GradingPeriodAction.all_objects.get(period=self.period)

        snapshot.data = {**snapshot.data, "general_average": "0.00"}
        with self.assertRaisesMessage(ValidationError, "immuable"):
            snapshot.save()
        with self.assertRaisesMessage(
            ValidationError, "ne peut pas être supprimé"
        ):
            snapshot.delete()

        action.reason = "Motif modifié après coup."
        with self.assertRaisesMessage(ValidationError, "immuable"):
            action.save()
        with self.assertRaisesMessage(
            ValidationError, "ne peut pas être supprimé"
        ):
            action.delete()

    def test_period_management_is_reserved_to_management_roles(self):
        self.client.force_login(self.teacher)

        close_response = self.client.post(self.close_url)
        reopen_response = self.client.get(self.reopen_url)

        self.assertEqual(close_response.status_code, 403)
        self.assertEqual(reopen_response.status_code, 403)
        self.period.refresh_from_db()
        self.assertFalse(self.period.is_closed)

    def test_a_period_from_another_school_cannot_be_closed(self):
        other_school = School.all_objects.create(
            organization=self.org, name="Collège Cycle", code="CYC-2"
        )
        other_year = AcademicYear.all_objects.create(
            school=other_school,
            name="2026-2027",
            start_date=date(2026, 10, 1),
            end_date=date(2027, 6, 30),
        )
        other_period = GradingPeriod.all_objects.create(
            school=other_school,
            academic_year=other_year,
            code="T1",
            name="Trimestre 1",
            sequence=1,
        )

        response = self.client.post(
            self.url("grading_period_close", period_id=other_period.pk)
        )

        self.assertEqual(response.status_code, 404)
        other_period.refresh_from_db()
        self.assertFalse(other_period.is_closed)
