from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
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
    Deliberation,
    GradingPeriod,
    Grade,
    GradeRevision,
)
from .services import build_bulletins


User = get_user_model()


class GradingWorkflowTests(TestCase):
    def setUp(self):
        self.org = Organization.all_objects.create(name="Groupe Résultats")
        self.school = School.all_objects.create(
            organization=self.org, name="Lycée Résultats", code="RES-1"
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
        self.admin = User.objects.create_user(username="direction-resultats")
        self.teacher = User.objects.create_user(username="enseignant-resultats")
        self.other_teacher = User.objects.create_user(
            username="enseignant-non-affecte"
        )
        for user, role in (
            (self.admin, Role.SCHOOL_ADMIN),
            (self.teacher, Role.TEACHER),
            (self.other_teacher, Role.TEACHER),
        ):
            Membership.all_objects.create(
                user=user,
                organization=self.org,
                school=self.school,
                role=role,
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
                matricule="RES-001",
                first_name="Awa",
                last_name="Traoré",
            ),
            Student.all_objects.create(
                school=self.school,
                matricule="RES-002",
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

    def make_assessment(self, title, max_score, weight):
        return Assessment.all_objects.create(
            school=self.school,
            class_subject=self.class_subject,
            period=self.period,
            title=title,
            assessment_type="quiz",
            held_on=date(2026, 11, 10),
            max_score=Decimal(max_score),
            weight=Decimal(weight),
            created_by=self.admin,
        )

    def test_published_notes_generate_weighted_bulletins_with_coefficients(self):
        first = self.make_assessment("Interrogation 1", "20", "2")
        second = self.make_assessment("Devoir 1", "10", "1")
        for assessment, scores in ((first, (16, 12)), (second, (8, 9))):
            for enrollment, score in zip(self.enrollments, scores):
                Grade.all_objects.create(
                    school=self.school,
                    assessment=assessment,
                    enrollment=enrollment,
                    score=Decimal(score),
                    status="graded",
                )
            assessment.is_published = True
            assessment.published_at = timezone.now()
            assessment.published_by = self.admin
            assessment.save()

        with tenant_scope(self.org.pk, self.school.pk):
            bulletins = build_bulletins(self.school_class, self.period)

        by_matricule = {
            bulletin["student"].matricule: bulletin for bulletin in bulletins
        }
        awa = by_matricule["RES-001"]
        boubacar = by_matricule["RES-002"]
        self.assertEqual(awa["general_average"], Decimal("16.00"))
        self.assertEqual(awa["rows"][0]["coefficient"], Decimal("4.00"))
        self.assertEqual(awa["rank"], 1)
        self.assertEqual(boubacar["general_average"], Decimal("14.00"))
        self.assertEqual(boubacar["rank"], 2)

    def test_gradebook_publishes_only_after_every_student_has_a_result(self):
        assessment = self.make_assessment("Composition", "20", "1")
        ordered_enrollments = sorted(
            self.enrollments,
            key=lambda item: (item.student.last_name, item.student.first_name),
        )
        url = self.url("gradebook", assessment_id=assessment.pk)
        post_data = {
            "notes-TOTAL_FORMS": "2",
            "notes-INITIAL_FORMS": "2",
            "notes-MIN_NUM_FORMS": "0",
            "notes-MAX_NUM_FORMS": "2000",
            "notes-0-enrollment_id": str(ordered_enrollments[0].pk),
            "notes-0-status": "graded",
            "notes-0-score": "15",
            "notes-0-comment": "",
            "notes-1-enrollment_id": str(ordered_enrollments[1].pk),
            "notes-1-status": "",
            "notes-1-score": "",
            "notes-1-comment": "",
            "action": "publish",
        }

        response = self.client.post(url, post_data, follow=True)

        assessment.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(assessment.is_published)
        self.assertContains(response, "Publication impossible")

    def test_teacher_cannot_enter_an_unassigned_class_subject(self):
        assessment = self.make_assessment("Interrogation", "20", "1")
        self.client.force_login(self.other_teacher)

        response = self.client.get(self.url("gradebook", assessment_id=assessment.pk))

        self.assertEqual(response.status_code, 403)

    def test_report_card_page_links_to_coefficient_configuration(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            self.url("report_card_list"),
            {"periode": self.period.pk, "classe": self.school_class.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configurer les coefficients")

    def test_deliberation_is_recorded_and_shown_on_report_card(self):
        url = self.url(
            "deliberation_edit",
            enrollment_id=self.enrollments[0].pk,
            period_id=self.period.pk,
        )

        response = self.client.post(
            url,
            {
                "outcome": "promoted",
                "comment": "Décision validée par le conseil de classe.",
            },
        )

        self.assertEqual(response.status_code, 302)
        deliberation = Deliberation.all_objects.get(
            period=self.period, enrollment=self.enrollments[0]
        )
        self.assertEqual(deliberation.decided_by, self.admin)
        bulletin_response = self.client.get(
            self.url("report_card_list"),
            {"periode": self.period.pk, "classe": self.school_class.pk},
        )
        self.assertContains(bulletin_response, "Admis / promu")

    def test_teacher_cannot_record_deliberation(self):
        self.client.force_login(self.teacher)

        response = self.client.get(
            self.url(
                "deliberation_edit",
                enrollment_id=self.enrollments[0].pk,
                period_id=self.period.pk,
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_published_grade_correction_requires_reason_and_keeps_history(self):
        assessment = self.make_assessment("Composition", "20", "1")
        ordered_enrollments = sorted(
            self.enrollments,
            key=lambda item: (item.student.last_name, item.student.first_name),
        )
        original_scores = {self.enrollments[0].pk: 16, self.enrollments[1].pk: 12}
        for enrollment in ordered_enrollments:
            Grade.all_objects.create(
                school=self.school,
                assessment=assessment,
                enrollment=enrollment,
                score=Decimal(original_scores[enrollment.pk]),
                status="graded",
            )
        assessment.is_published = True
        assessment.published_at = timezone.now()
        assessment.published_by = self.admin
        assessment.save()

        post_data = {
            "notes-TOTAL_FORMS": "2",
            "notes-INITIAL_FORMS": "2",
            "notes-MIN_NUM_FORMS": "0",
            "notes-MAX_NUM_FORMS": "2000",
            "reason": "Erreur de transcription corrigée après vérification.",
            "action": "correct",
        }
        for index, enrollment in enumerate(ordered_enrollments):
            post_data.update(
                {
                    f"notes-{index}-enrollment_id": str(enrollment.pk),
                    f"notes-{index}-status": "graded",
                    f"notes-{index}-score": (
                        "17" if enrollment.pk == self.enrollments[0].pk else "12"
                    ),
                    f"notes-{index}-comment": "",
                }
            )
        url = f"{self.url('gradebook', assessment_id=assessment.pk)}?corriger=1"

        missing_reason = post_data.copy()
        missing_reason.pop("reason")
        invalid_response = self.client.post(url, missing_reason)
        self.assertEqual(invalid_response.status_code, 200)
        self.assertEqual(
            Grade.all_objects.get(
                assessment=assessment, enrollment=self.enrollments[0]
            ).score,
            Decimal("16"),
        )
        self.assertFalse(GradeRevision.all_objects.filter(grade__assessment=assessment).exists())

        response = self.client.post(url, post_data, follow=True)

        self.assertEqual(response.status_code, 200)
        corrected_grade = Grade.all_objects.get(
            assessment=assessment, enrollment=self.enrollments[0]
        )
        self.assertEqual(corrected_grade.score, Decimal("17"))
        revision = GradeRevision.all_objects.get(grade=corrected_grade)
        self.assertEqual(revision.previous_score, Decimal("16"))
        self.assertEqual(revision.new_score, Decimal("17"))
        self.assertEqual(revision.changed_by, self.admin)
        self.assertEqual(
            revision.reason, "Erreur de transcription corrigée après vérification."
        )
        self.assertContains(response, "Erreur de transcription corrigée")

    def test_teacher_cannot_correct_a_published_grade(self):
        assessment = self.make_assessment("Composition", "20", "1")
        assessment.is_published = True
        assessment.save()
        self.client.force_login(self.teacher)

        response = self.client.get(
            f"{self.url('gradebook', assessment_id=assessment.pk)}?corriger=1"
        )

        self.assertEqual(response.status_code, 403)
