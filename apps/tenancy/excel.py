from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from apps.academics.models import AcademicYear, SchoolClass, Subject
from apps.academics.utils import current_academic_year

HEADER_FILL = PatternFill("solid", fgColor="0F5132")
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center")
TITLE_FONT = Font(bold=True, size=14, color="0B2E24")


def add_headers(worksheet, headers, widths, comments=None):
    for column, header in enumerate(headers, start=1):
        cell = worksheet.cell(row=1, column=column, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGNMENT
        if comments and header in comments:
            cell.comment = Comment(comments[header], "Gestion scolaire")
    for index, width in enumerate(widths, start=1):
        worksheet.column_dimensions[
            worksheet.cell(row=1, column=index).column_letter
        ].width = width
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = (
        f"A1:{worksheet.cell(row=1, column=len(headers)).column_letter}1"
    )


def build_workbook(organization=None, school=None):
    workbook = Workbook()
    guide = workbook.active
    guide.title = "Mode d'emploi"
    guide.column_dimensions["A"].width = 115
    guide["A1"] = "Modèle d'import de la scolarité"
    guide["A1"].font = TITLE_FONT
    lines = [
        "",
        "1. Renseigner les feuilles Matieres, Coefficients et Eleves.",
        "2. Les codes sont normalisés en majuscules.",
        "3. L'import est transactionnel : en cas d'erreur, rien n'est enregistré.",
        "4. Les dates acceptent JJ/MM/AAAA ou AAAA-MM-JJ.",
        "5. Le matricule est obligatoire pour identifier un élève de façon stable.",
        "6. Sexe : M ou F. Payeur : Oui ou Non.",
        "7. Niveau, Série et Section doivent être renseignés ensemble "
        "pour inscrire l'élève dans une classe.",
        "8. Une année scolaire et les niveaux/séries doivent exister avant l'import.",
        "9. Les matières et coefficients sont rattachés à l'année choisie.",
        "10. Contrôle recommandé : lancez d'abord une simulation "
        "depuis l'écran Import Excel.",
        "11. Ligne de commande équivalente :",
        "    python manage.py import_excel fichier.xlsx "
        "--organisation demo --ecole DEMO-A --dry-run",
        "12. Pour appliquer : retirer --dry-run.",
        "",
        "Feuilles :",
        "- Matieres : Code, Nom.",
        "- Coefficients : Niveau, Série, Matière, Coefficient, Heures.",
        "- Eleves : identité, classe et tuteur.",
        "",
        "Les colonnes Niveau et Série acceptent le code ou le nom existant.",
        "Les colonnes Matière et Section acceptent le code ou le nom.",
    ]
    for index, line in enumerate(lines, start=2):
        cell = guide.cell(row=index, column=1, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    guide["A3"].font = Font(bold=True, color="0B2E24")

    subjects = workbook.create_sheet("Matieres")
    add_headers(
        subjects,
        ["Code", "Nom"],
        [18, 42],
        {
            "Code": "Code court et stable, par exemple FR, MATH, SVT.",
            "Nom": "Libellé affiché de la matière.",
        },
    )

    coefficients = workbook.create_sheet("Coefficients")
    add_headers(
        coefficients,
        ["Niveau", "Série", "Matière", "Coefficient", "Heures"],
        [14, 16, 24, 14, 12],
        {
            "Niveau": "Code ou nom du niveau existant, par exemple 11 ou 11ème.",
            "Série": "Code ou nom de la série existante, par exemple LET.",
            "Matière": "Code ou nom de la matière existante.",
            "Coefficient": "Nombre strictement positif.",
            "Heures": "Volume horaire hebdomadaire, facultatif.",
        },
    )

    students = workbook.create_sheet("Eleves")
    student_headers = [
        "Matricule",
        "Nom",
        "Prénoms",
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
    add_headers(
        students,
        student_headers,
        [16, 20, 24, 9, 16, 22, 18, 28, 30, 12, 14, 10, 20, 22, 20, 14, 10, 14],
        {
            "Matricule": "Obligatoire. Identifiant stable de l'élève dans l'école.",
            "Sexe": "M ou F.",
            "Niveau": "Code ou nom du niveau. Avec Série et Section, crée "
            "la classe si elle n'existe pas.",
            "Section": "A, B, C…",
            "Tuteur téléphone": "Obligatoire dès qu'un tuteur est renseigné.",
            "Lien": "Père, Mère, Tuteur ou Autre.",
            "Payeur": "Oui ou Non.",
            "Statut": "Actif, Inactif, Diplômé, Transféré ou Archivé.",
        },
    )

    sex_validation = DataValidation(
        type="list", formula1='"M,F"', allow_blank=True
    )
    sex_validation.error = "Utilisez M ou F."
    sex_validation.errorTitle = "Sexe invalide"
    students.add_data_validation(sex_validation)
    sex_validation.add("D2:D2000")

    payer_validation = DataValidation(
        type="list", formula1='"Oui,Non"', allow_blank=True
    )
    payer_validation.error = "Utilisez Oui ou Non."
    payer_validation.errorTitle = "Valeur invalide"
    students.add_data_validation(payer_validation)
    payer_validation.add("Q2:Q2000")

    status_validation = DataValidation(
        type="list",
        formula1='"Actif,Inactif,Diplômé,Transféré,Archivé"',
        allow_blank=True,
    )
    status_validation.error = "Choisissez un statut dans la liste."
    status_validation.errorTitle = "Statut invalide"
    students.add_data_validation(status_validation)
    status_validation.add("R2:R2000")

    coefficient_validation = DataValidation(
        type="decimal",
        operator="greaterThan",
        formula1="0",
        allow_blank=False,
    )
    coefficient_validation.error = "Le coefficient doit être supérieur à 0."
    coefficient_validation.errorTitle = "Coefficient invalide"
    coefficients.add_data_validation(coefficient_validation)
    coefficient_validation.add("D2:D2000")

    hours_validation = DataValidation(
        type="decimal",
        operator="greaterThanOrEqual",
        formula1="0",
        allow_blank=True,
    )
    hours_validation.error = "Le volume horaire doit être positif ou nul."
    hours_validation.errorTitle = "Heures invalides"
    coefficients.add_data_validation(hours_validation)
    hours_validation.add("E2:E2000")

    references = workbook.create_sheet("References")
    add_headers(references, ["Type", "Code", "Nom", "Précision"], [14, 18, 34, 38])
    if school is not None:
        years = AcademicYear.objects.filter(school=school).order_by(
            "-start_date"
        )
        current_year = current_academic_year(school)
        row = 2
        for year in years:
            references.cell(row=row, column=1, value="Année")
            references.cell(row=row, column=2, value=year.name)
            references.cell(
                row=row,
                column=4,
                value="Courante" if year == current_year else "",
            )
            row += 1
        for level in school.levels.order_by("order", "code"):
            references.cell(row=row, column=1, value="Niveau")
            references.cell(row=row, column=2, value=level.code)
            references.cell(row=row, column=3, value=level.name)
            row += 1
            for series in level.series.order_by("code"):
                references.cell(row=row, column=1, value="Série")
                references.cell(row=row, column=2, value=series.code)
                references.cell(row=row, column=3, value=series.name)
                references.cell(
                    row=row,
                    column=4,
                    value=f"Niveau {level.code} — {level.name}",
                )
                row += 1
        for subject in Subject.objects.filter(school=school).order_by("name"):
            references.cell(row=row, column=1, value="Matière")
            references.cell(row=row, column=2, value=subject.code)
            references.cell(row=row, column=3, value=subject.name)
            row += 1
        classes = (
            SchoolClass.objects.filter(school=school)
            .select_related("academic_year", "level", "series")
            .order_by("-academic_year__start_date", "level__order", "section")
        )
        for school_class in classes:
            references.cell(row=row, column=1, value="Classe")
            references.cell(row=row, column=2, value=school_class.section)
            references.cell(row=row, column=3, value=school_class.display_name)
            references.cell(
                row=row,
                column=4,
                value=(
                    f"{school_class.academic_year.name} · "
                    f"{school_class.level.code} / "
                    f"{school_class.series.code}"
                ),
            )
            row += 1
    else:
        references["A2"] = (
            "Générez le modèle avec --organisation et --ecole pour obtenir "
            "les niveaux, séries, matières et classes existants."
        )

    return workbook
