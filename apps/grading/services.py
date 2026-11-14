from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from apps.academics.models import Curriculum, CurriculumSubject, SchoolClass
from apps.students.models import Enrollment, EnrollmentStatus

from .models import (
    Assessment,
    BulletinSnapshot,
    Deliberation,
    Grade,
    GradeStatus,
)


TWENTY = Decimal("20")
TWO_PLACES = Decimal("0.01")


def _rounded(value):
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def build_bulletins(school_class, period, snapshot_version=None):
    """Calcule les bulletins d'une classe à partir des notes publiées."""
    if period.is_closed or snapshot_version is not None:
        return build_bulletins_from_snapshots(
            school_class, period, version=snapshot_version
        )
    enrollments = list(
        Enrollment.objects.filter(
            school_class=school_class, status=EnrollmentStatus.ACTIVE
        )
        .select_related("student")
        .order_by("student__last_name", "student__first_name", "student__matricule")
    )
    class_subjects = list(
        school_class.class_subjects.select_related("subject").order_by(
            "subject__name"
        )
    )

    assessments = list(
        Assessment.objects.filter(
            class_subject__school_class=school_class,
            period=period,
            is_published=True,
        ).select_related("class_subject", "class_subject__subject")
    )
    assessments_by_subject = defaultdict(list)
    for assessment in assessments:
        assessments_by_subject[assessment.class_subject_id].append(assessment)

    grades = Grade.objects.filter(
        assessment__in=assessments, enrollment__in=enrollments
    )
    grade_by_key = {
        (grade.assessment_id, grade.enrollment_id): grade for grade in grades
    }
    deliberation_by_enrollment = {
        item.enrollment_id: item
        for item in Deliberation.objects.filter(
            period=period, enrollment__in=enrollments
        )
    }

    coefficient_by_subject = {}
    curriculum = Curriculum.objects.filter(
        school=school_class.school,
        academic_year=school_class.academic_year,
        level=school_class.level,
        series=school_class.series,
        is_active=True,
    ).first()
    if curriculum:
        coefficient_by_subject = dict(
            CurriculumSubject.objects.filter(curriculum=curriculum).values_list(
                "subject_id", "coefficient"
            )
        )

    bulletins = []
    for enrollment in enrollments:
        rows = []
        weighted_total = Decimal("0")
        included_coefficients = Decimal("0")

        for class_subject in class_subjects:
            subject_assessments = assessments_by_subject[class_subject.pk]
            weighted_marks = Decimal("0")
            total_weight = Decimal("0")
            absences = 0
            excused = 0
            recorded = 0

            for assessment in subject_assessments:
                grade = grade_by_key.get((assessment.pk, enrollment.pk))
                if grade is None:
                    continue
                if grade.status == GradeStatus.ABSENT:
                    absences += 1
                elif grade.status == GradeStatus.EXCUSED:
                    excused += 1
                elif grade.status == GradeStatus.GRADED and grade.score is not None:
                    normalized = grade.score * TWENTY / assessment.max_score
                    weighted_marks += normalized * assessment.weight
                    total_weight += assessment.weight
                    recorded += 1

            average = (
                _rounded(weighted_marks / total_weight)
                if total_weight
                else None
            )
            coefficient = coefficient_by_subject.get(class_subject.subject_id)
            points = (
                _rounded(average * coefficient)
                if average is not None and coefficient is not None
                else None
            )
            rows.append(
                {
                    "class_subject": class_subject,
                    "subject": class_subject.subject,
                    "average": average,
                    "coefficient": coefficient,
                    "points": points,
                    "recorded_count": recorded,
                    "absence_count": absences,
                    "excused_count": excused,
                }
            )
            if average is not None and coefficient is not None:
                weighted_total += average * coefficient
                included_coefficients += coefficient

        general_average = (
            _rounded(weighted_total / included_coefficients)
            if included_coefficients
            else None
        )
        bulletins.append(
            {
                "enrollment": enrollment,
                "student": enrollment.student,
                "class_name": school_class.display_name,
                "period_name": period.name,
                "rows": rows,
                "general_average": general_average,
                "coefficient_total": included_coefficients,
                "subjects_count": len(class_subjects),
                "subjects_with_average": sum(
                    1 for row in rows if row["average"] is not None
                ),
                "subjects_counted": sum(
                    1
                    for row in rows
                    if row["average"] is not None and row["coefficient"] is not None
                ),
                "unconfigured_coefficient_count": sum(
                    1
                    for row in rows
                    if row["average"] is not None and row["coefficient"] is None
                ),
                "deliberation": deliberation_by_enrollment.get(enrollment.pk),
                "deliberation_label": (
                    deliberation_by_enrollment[enrollment.pk].get_outcome_display()
                    if enrollment.pk in deliberation_by_enrollment
                    else ""
                ),
                "deliberation_comment": (
                    deliberation_by_enrollment[enrollment.pk].comment
                    if enrollment.pk in deliberation_by_enrollment
                    else ""
                ),
                "rank": None,
            }
        )

    ranked = sorted(
        (item for item in bulletins if item["general_average"] is not None),
        key=lambda item: (-item["general_average"], item["student"].last_name,
                          item["student"].first_name),
    )
    previous_average = None
    current_rank = 0
    for position, item in enumerate(ranked, start=1):
        if item["general_average"] != previous_average:
            current_rank = position
            previous_average = item["general_average"]
        item["rank"] = current_rank

    return bulletins


def _decimal_text(value):
    return str(value) if value is not None else None


def serialize_bulletin(period, bulletin):
    """Convertit le bulletin calculé en données indépendantes et immuables."""
    student = bulletin["student"]
    return {
        "student": {
            "first_name": student.first_name,
            "last_name": student.last_name,
            "full_name": student.full_name,
            "matricule": student.matricule,
        },
        "class_name": bulletin["class_name"],
        "academic_year": period.academic_year.name,
        "period_name": period.name,
        "rows": [
            {
                "subject_name": row["subject"].name,
                "average": _decimal_text(row["average"]),
                "coefficient": _decimal_text(row["coefficient"]),
                "points": _decimal_text(row["points"]),
                "recorded_count": row["recorded_count"],
                "absence_count": row["absence_count"],
                "excused_count": row["excused_count"],
            }
            for row in bulletin["rows"]
        ],
        "general_average": _decimal_text(bulletin["general_average"]),
        "coefficient_total": _decimal_text(bulletin["coefficient_total"]),
        "subjects_count": bulletin["subjects_count"],
        "subjects_with_average": bulletin["subjects_with_average"],
        "subjects_counted": bulletin["subjects_counted"],
        "unconfigured_coefficient_count": bulletin[
            "unconfigured_coefficient_count"
        ],
        "rank": bulletin["rank"],
        "deliberation_label": bulletin["deliberation_label"],
        "deliberation_comment": bulletin["deliberation_comment"],
    }


def capture_period_snapshots(period, user, version):
    """Fige tous les bulletins actifs de l'année au numéro de clôture donné."""
    classes = SchoolClass.objects.filter(
        school=period.school, academic_year=period.academic_year
    ).order_by("level__order", "series__code", "section")
    created_count = 0
    for school_class in classes:
        for bulletin in build_bulletins(school_class, period):
            snapshot = BulletinSnapshot(
                school=period.school,
                period=period,
                enrollment=bulletin["enrollment"],
                version=version,
                data=serialize_bulletin(period, bulletin),
                generated_by=user,
                generated_by_label=str(user),
            )
            snapshot.full_clean()
            snapshot.save()
            created_count += 1
    return created_count


def build_bulletins_from_snapshots(school_class, period, version=None):
    """Reconstitue des bulletins sans relire les notes ou coefficients courants."""
    snapshots = BulletinSnapshot.objects.filter(
        period=period, enrollment__school_class=school_class
    ).select_related("enrollment", "enrollment__student", "enrollment__school_class")
    if version is not None:
        snapshots = snapshots.filter(version=version)
    else:
        snapshots = snapshots.order_by("enrollment_id", "-version")

    latest_by_enrollment = {}
    for snapshot in snapshots:
        latest_by_enrollment.setdefault(snapshot.enrollment_id, snapshot)

    bulletins = []
    for snapshot in latest_by_enrollment.values():
        data = snapshot.data
        student = data["student"]
        rows = [
            {
                "subject": {"name": row["subject_name"]},
                "average": Decimal(row["average"])
                if row["average"] is not None
                else None,
                "coefficient": Decimal(row["coefficient"])
                if row["coefficient"] is not None
                else None,
                "points": Decimal(row["points"])
                if row["points"] is not None
                else None,
                "recorded_count": row["recorded_count"],
                "absence_count": row["absence_count"],
                "excused_count": row["excused_count"],
            }
            for row in data["rows"]
        ]
        bulletins.append(
            {
                "enrollment": snapshot.enrollment,
                "student": student,
                "class_name": data["class_name"],
                "period_name": data["period_name"],
                "rows": rows,
                "general_average": Decimal(data["general_average"])
                if data["general_average"] is not None
                else None,
                "coefficient_total": Decimal(data["coefficient_total"]),
                "subjects_count": data["subjects_count"],
                "subjects_with_average": data["subjects_with_average"],
                "subjects_counted": data["subjects_counted"],
                "unconfigured_coefficient_count": data[
                    "unconfigured_coefficient_count"
                ],
                "deliberation": None,
                "deliberation_label": data["deliberation_label"],
                "deliberation_comment": data["deliberation_comment"],
                "rank": data["rank"],
                "snapshot_version": snapshot.version,
            }
        )
    bulletins.sort(
        key=lambda item: (
            item["rank"] if item["rank"] is not None else 10**9,
            item["student"]["last_name"],
            item["student"]["first_name"],
        )
    )
    return bulletins
