from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.common.excel import (
    SheetFormatError,
    iter_rows,
    normalize_code,
    normalize_key,
    parse_decimal,
    text,
)
from apps.common.importing import error_message

from .models import (
    Curriculum,
    CurriculumSubject,
    Level,
    Series,
    Subject,
)

SUBJECTS_SHEET = "Matieres"
COEFFICIENTS_SHEET = "Coefficients"
SUBJECT_REQUIRED = ["Code", "Nom"]
COEFFICIENT_REQUIRED = [
    "Niveau",
    "Série",
    "Matière",
    "Coefficient",
]
COEFFICIENT_OPTIONAL = ["Heures"]


def resolve_level(school, value):
    if not value:
        return None
    code = normalize_code(value)
    level = Level.objects.filter(school=school, code=code).first()
    if level:
        return level
    target = normalize_key(value)
    for candidate in Level.objects.filter(school=school):
        if normalize_key(candidate.name) == target:
            return candidate
    return None


def resolve_series(level, value):
    if not value:
        return None
    code = normalize_code(value)
    series = Series.objects.filter(level=level, code=code).first()
    if series:
        return series
    target = normalize_key(value)
    for candidate in Series.objects.filter(level=level):
        if normalize_key(candidate.name) == target:
            return candidate
    return None


def resolve_subject(school, value):
    if not value:
        return None
    code = normalize_code(value)
    subject = Subject.objects.filter(school=school, code=code).first()
    if subject:
        return subject
    target = normalize_key(value)
    for candidate in Subject.objects.filter(school=school):
        if normalize_key(candidate.name) == target:
            return candidate
    return None


def import_subjects(worksheet, school, report):
    seen_codes = set()
    for row_number, row in iter_rows(worksheet, SUBJECT_REQUIRED):
        events = []
        try:
            with transaction.atomic():
                code = normalize_code(row["code"])
                name = text(row["nom"])
                if not code:
                    raise ValueError("Le code de la matière est obligatoire.")
                if not name:
                    raise ValueError("Le nom de la matière est obligatoire.")
                if code in seen_codes:
                    raise ValueError(f"Matière en double dans le fichier : {code}.")
                seen_codes.add(code)

                subject = Subject.objects.filter(
                    school=school, code=code
                ).first()
                created = subject is None
                if subject is None:
                    subject = Subject(school=school, code=code, name=name)
                else:
                    subject.name = name
                subject.full_clean()
                subject.save()
                events.append((created, "Matières"))
        except (ValueError, ValidationError, IntegrityError) as exc:
            report.add_error(
                SUBJECTS_SHEET, row_number, error_message(exc)
            )
        else:
            for created, label in events:
                if created:
                    report.add_created(label)
                else:
                    report.add_updated(label)


def import_coefficients(worksheet, school, academic_year, report):
    seen = set()
    for row_number, row in iter_rows(
        worksheet, COEFFICIENT_REQUIRED, COEFFICIENT_OPTIONAL
    ):
        events = []
        try:
            with transaction.atomic():
                level_label = text(row["niveau"])
                series_label = text(row["serie"])
                subject_label = text(row["matiere"])
                if not level_label or not series_label or not subject_label:
                    raise ValueError(
                        "Niveau, série et matière sont obligatoires."
                    )

                level = resolve_level(school, level_label)
                if level is None:
                    raise ValueError(f"Niveau introuvable : {level_label}.")
                series = resolve_series(level, series_label)
                if series is None:
                    raise ValueError(
                        f"Série introuvable pour {level.name} : {series_label}."
                    )
                subject = resolve_subject(school, subject_label)
                if subject is None:
                    raise ValueError(
                        f"Matière introuvable : {subject_label}."
                    )

                coefficient = parse_decimal(row["coefficient"])
                if coefficient is None or coefficient <= 0:
                    raise ValueError(
                        "Le coefficient doit être un nombre strictement positif."
                    )
                hours = parse_decimal(row["heures"])
                if hours is not None and hours < 0:
                    raise ValueError("Le volume horaire ne peut pas être négatif.")

                key = (level.id, series.id, subject.id)
                if key in seen:
                    raise ValueError(
                        "Coefficient en double pour "
                        f"{level.name} / {series.name} / {subject.name}."
                    )

                curriculum = Curriculum.objects.filter(
                    school=school,
                    academic_year=academic_year,
                    level=level,
                    series=series,
                ).first()
                if curriculum is None:
                    curriculum = Curriculum(
                        school=school,
                        academic_year=academic_year,
                        level=level,
                        series=series,
                    )
                    curriculum.full_clean()
                    curriculum.save()
                    events.append((True, "Curricula"))

                subject_coefficient = CurriculumSubject.objects.filter(
                    curriculum=curriculum, subject=subject
                ).first()
                created = subject_coefficient is None
                if subject_coefficient is None:
                    subject_coefficient = CurriculumSubject(
                        curriculum=curriculum, subject=subject
                    )
                subject_coefficient.coefficient = coefficient
                subject_coefficient.weekly_hours = hours
                subject_coefficient.full_clean()
                subject_coefficient.save()
                events.append((created, "Coefficients"))
                seen.add(key)
        except (ValueError, ValidationError, IntegrityError) as exc:
            report.add_error(
                COEFFICIENTS_SHEET, row_number, error_message(exc)
            )
        else:
            for created, label in events:
                if created:
                    report.add_created(label)
                else:
                    report.add_updated(label)
