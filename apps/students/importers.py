from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.academics.importers import resolve_level, resolve_series
from apps.academics.models import SchoolClass
from apps.common.excel import (
    iter_rows,
    normalize_code,
    normalize_key,
    parse_bool,
    parse_date,
    text,
)
from apps.common.importing import error_message

from .models import (
    Enrollment,
    EnrollmentStatus,
    Gender,
    Guardian,
    GuardianRelationship,
    Student,
    StudentGuardian,
    StudentStatus,
)

SHEET = "Eleves"
REQUIRED = ["Matricule", "Nom", "Prénoms"]
OPTIONAL = [
    "Sexe",
    "Date de naissance",
    "Lieu de naissance",
    "Téléphone",
    "Email",
    "Adresse",
    "Niveau",
    "Série",
    "Section",
    "Tuteur nom",
    "Tuteur prénoms",
    "Tuteur téléphone",
    "Lien",
    "Payeur",
    "Statut",
]

STATUS_ALIASES = {
    "actif": StudentStatus.ACTIVE,
    "active": StudentStatus.ACTIVE,
    "inactif": StudentStatus.INACTIVE,
    "diplome": StudentStatus.GRADUATED,
    "transfere": StudentStatus.TRANSFERRED,
    "archive": StudentStatus.ARCHIVED,
}


def normalize_phone(value):
    raw = text(value)
    digits = "".join(char for char in raw if char.isdigit())
    if not digits:
        return ""
    if raw.startswith("+"):
        return f"+{digits}"
    return digits


def parse_gender(value):
    key = normalize_key(value)
    if not key:
        return ""
    if key in {"m", "masculin", "h", "homme"}:
        return Gender.MALE
    if key in {"f", "feminin", "femme"}:
        return Gender.FEMALE
    raise ValueError(f"Sexe invalide : {value}. Utilisez M ou F.")


def parse_student_status(value):
    key = normalize_key(value)
    if not key:
        return None
    status = STATUS_ALIASES.get(key)
    if status is None:
        raise ValueError(
            f"Statut invalide : {value}. "
            "Utilisez Actif, Inactif, Diplômé, Transféré ou Archivé."
        )
    return status


def parse_relationship(value):
    key = normalize_key(value)
    if key in {"pere", "father"}:
        return GuardianRelationship.FATHER
    if key in {"mere", "mother"}:
        return GuardianRelationship.MOTHER
    if key in {"tuteur", "tutrice", "tutor"}:
        return GuardianRelationship.TUTOR
    return GuardianRelationship.OTHER


def import_students(
    worksheet,
    school,
    academic_year,
    report,
    create_classes=True,
):
    seen_matricules = set()
    warned_full_classes = set()

    for row_number, row in iter_rows(worksheet, REQUIRED, OPTIONAL):
        events = []
        warnings = []
        try:
            with transaction.atomic():
                matricule = normalize_code(row["matricule"])
                last_name = text(row["nom"])
                first_name = text(row["prenoms"])
                if not matricule:
                    raise ValueError(
                        "Le matricule est obligatoire pour garantir "
                        "l'idempotence de l'import."
                    )
                if not last_name or not first_name:
                    raise ValueError("Le nom et les prénoms sont obligatoires.")
                if matricule in seen_matricules:
                    raise ValueError(
                        f"Élève en double dans le fichier : {matricule}."
                    )
                seen_matricules.add(matricule)

                gender = parse_gender(row["sexe"])
                birth_date = parse_date(row["date de naissance"])
                if birth_date and birth_date > date.today():
                    raise ValueError(
                        "La date de naissance ne peut pas être dans le futur."
                    )
                status = parse_student_status(row["statut"])

                student = Student.objects.filter(
                    school=school, matricule=matricule
                ).first()
                created = student is None
                if student is None:
                    student = Student(school=school, matricule=matricule)

                student.last_name = last_name
                student.first_name = first_name
                if gender or created:
                    student.gender = gender
                if birth_date or created:
                    student.date_of_birth = birth_date
                for field, key in [
                    ("place_of_birth", "lieu de naissance"),
                    ("phone", "telephone"),
                    ("email", "email"),
                    ("address", "adresse"),
                ]:
                    value = text(row[key])
                    if value or created:
                        setattr(student, field, value)
                if status or created:
                    student.status = status or StudentStatus.ACTIVE

                student.full_clean()
                student.save()
                events.append((created, "Élèves"))

                level_label = text(row["niveau"])
                series_label = text(row["serie"])
                section = normalize_code(row["section"])
                school_class = None

                if level_label or series_label or section:
                    if not (level_label and series_label and section):
                        raise ValueError(
                            "Niveau, série et section doivent être "
                            "renseignés ensemble."
                        )
                    level = resolve_level(school, level_label)
                    if level is None:
                        raise ValueError(f"Niveau introuvable : {level_label}.")
                    series = resolve_series(level, series_label)
                    if series is None:
                        raise ValueError(
                            f"Série introuvable pour {level.name} : "
                            f"{series_label}."
                        )

                    school_class = SchoolClass.objects.filter(
                        school=school,
                        academic_year=academic_year,
                        level=level,
                        series=series,
                        section=section,
                    ).first()
                    if school_class is None:
                        if not create_classes:
                            raise ValueError(
                                "Classe introuvable : "
                                f"{level.name} {series.name} {section}."
                            )
                        school_class = SchoolClass(
                            school=school,
                            academic_year=academic_year,
                            level=level,
                            series=series,
                            section=section,
                            capacity=100,
                        )
                        school_class.full_clean()
                        school_class.save()
                        events.append((True, "Classes"))

                if school_class:
                    if student.status != StudentStatus.ACTIVE:
                        warnings.append(
                            "Élève non actif : aucune inscription créée."
                        )
                    else:
                        enrollment = Enrollment.objects.filter(
                            student=student, academic_year=academic_year
                        ).first()
                        enrollment_created = enrollment is None
                        if enrollment is None:
                            enrollment = Enrollment(
                                school=school,
                                student=student,
                                academic_year=academic_year,
                                school_class=school_class,
                            )
                        elif enrollment.school_class_id != school_class.id:
                            enrollment.school_class = school_class
                        enrollment.full_clean()
                        enrollment.save()
                        events.append(
                            (enrollment_created, "Inscriptions")
                        )
                        if (
                            school_class.id not in warned_full_classes
                            and school_class.is_full
                        ):
                            warnings.append(
                                f"Classe {school_class.display_name} pleine "
                                f"({school_class.enrolled_count}/"
                                f"{school_class.capacity})."
                            )
                            warned_full_classes.add(school_class.id)

                guardian_last = text(row["tuteur nom"])
                guardian_first = text(row["tuteur prenoms"])
                guardian_phone = normalize_phone(row["tuteur telephone"])
                relationship_label = text(row["lien"])
                payer_raw = row["payeur"]
                payer_provided = bool(text(payer_raw))

                if any(
                    [
                        guardian_last,
                        guardian_first,
                        guardian_phone,
                        relationship_label,
                        payer_provided,
                    ]
                ):
                    if not guardian_phone:
                        raise ValueError(
                            "Le téléphone du tuteur est obligatoire."
                        )
                    if not guardian_last:
                        raise ValueError("Le nom du tuteur est obligatoire.")

                    guardian = (
                        Guardian.objects.filter(
                            organization=school.organization,
                            phone=guardian_phone,
                        )
                        .order_by("created_at")
                        .first()
                    )
                    guardian_created = guardian is None
                    if guardian is None:
                        guardian = Guardian(
                            organization=school.organization,
                            phone=guardian_phone,
                            last_name=guardian_last,
                            first_name=guardian_first,
                        )
                    else:
                        if guardian_last:
                            guardian.last_name = guardian_last
                        if guardian_first:
                            guardian.first_name = guardian_first
                    guardian.full_clean()
                    guardian.save()
                    if guardian_created:
                        events.append((True, "Tuteurs"))

                    link = StudentGuardian.objects.filter(
                        student=student, guardian=guardian
                    ).first()
                    link_created = link is None
                    if link is None:
                        link = StudentGuardian(
                            student=student,
                            guardian=guardian,
                            relationship=parse_relationship(
                                relationship_label
                            ),
                            is_financial_responsible=(
                                parse_bool(payer_raw, default=False)
                                if payer_provided
                                else False
                            ),
                        )
                    else:
                        if relationship_label:
                            link.relationship = parse_relationship(
                                relationship_label
                            )
                        if payer_provided:
                            link.is_financial_responsible = parse_bool(
                                payer_raw, default=False
                            )

                    has_other_primary = (
                        StudentGuardian.objects.filter(
                            student=student, is_primary=True
                        )
                        .exclude(pk=link.pk)
                        .exists()
                    )
                    if not has_other_primary:
                        link.is_primary = True

                    link.full_clean()
                    link.save()
                    events.append((link_created, "Liens tuteurs"))
        except (ValueError, ValidationError, IntegrityError) as exc:
            report.add_error(SHEET, row_number, error_message(exc))
        else:
            for created, label in events:
                if created:
                    report.add_created(label)
                else:
                    report.add_updated(label)
            for warning in warnings:
                report.add_warning(SHEET, row_number, warning)
