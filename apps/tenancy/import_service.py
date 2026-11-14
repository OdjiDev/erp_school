from django.db import transaction

from apps.academics.importers import import_coefficients, import_subjects
from apps.common.excel import SheetFormatError, normalize_key
from apps.common.importing import ImportReport
from apps.common.tenancy import tenant_scope
from apps.students.importers import import_students


class ImportRollback(Exception):
    """Sort du bloc transactionnel pour annuler ou simuler l'import."""


def find_sheet(workbook, name):
    target = normalize_key(name)
    for sheet_name in workbook.sheetnames:
        if normalize_key(sheet_name) == target:
            return workbook[sheet_name]
    return None


def run_import(
    workbook,
    organization,
    school,
    academic_year,
    dry_run=False,
    create_classes=True,
):
    """Importe matières, coefficients et élèves dans le périmètre de l'école.

    L'import est transactionnel : si une seule ligne échoue, aucune donnée
    n'est enregistrée. En mode simulation, tout est annulé à la fin.
    """
    report = ImportReport()
    found_sheet = False

    with tenant_scope(organization.pk, school.pk):
        try:
            with transaction.atomic():
                subjects_sheet = find_sheet(workbook, "Matieres")
                if subjects_sheet is None:
                    report.add_warning(
                        "Matieres", 0, "Feuille absente : matières ignorées."
                    )
                else:
                    found_sheet = True
                    try:
                        import_subjects(subjects_sheet, school, report)
                    except SheetFormatError as exc:
                        report.add_error("Matieres", 0, str(exc))

                coefficients_sheet = find_sheet(workbook, "Coefficients")
                if coefficients_sheet is None:
                    report.add_warning(
                        "Coefficients",
                        0,
                        "Feuille absente : coefficients ignorés.",
                    )
                else:
                    found_sheet = True
                    try:
                        import_coefficients(
                            coefficients_sheet,
                            school,
                            academic_year,
                            report,
                        )
                    except SheetFormatError as exc:
                        report.add_error("Coefficients", 0, str(exc))

                students_sheet = find_sheet(workbook, "Eleves")
                if students_sheet is None:
                    report.add_warning(
                        "Eleves", 0, "Feuille absente : élèves ignorés."
                    )
                else:
                    found_sheet = True
                    try:
                        import_students(
                            students_sheet,
                            school,
                            academic_year,
                            report,
                            create_classes=create_classes,
                        )
                    except SheetFormatError as exc:
                        report.add_error("Eleves", 0, str(exc))

                if not found_sheet:
                    report.add_error(
                        "Classeur",
                        0,
                        "Aucune feuille Matieres, Coefficients ou Eleves "
                        "n'a été trouvée.",
                    )

                if report.has_errors or dry_run:
                    raise ImportRollback()
        except ImportRollback:
            pass

    return report
