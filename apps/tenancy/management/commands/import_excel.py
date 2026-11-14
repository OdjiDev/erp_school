from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from apps.academics.models import AcademicYear
from apps.academics.utils import current_academic_year
from apps.common.excel import normalize_code
from apps.common.tenancy import tenant_scope
from apps.tenancy.import_service import run_import
from apps.tenancy.models import Organization, School


class Command(BaseCommand):
    help = (
        "Importe les matières, coefficients par série et élèves depuis un "
        "classeur Excel. L'import est transactionnel : tout ou rien."
    )

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Chemin du classeur .xlsx")
        parser.add_argument(
            "--organisation",
            required=True,
            help="Slug de l'organisation (client).",
        )
        parser.add_argument(
            "--ecole",
            required=True,
            help="Code de l'école, par exemple DEMO-A.",
        )
        parser.add_argument(
            "--annee",
            help="Année scolaire, par exemple 2026-2027. "
            "Par défaut : année courante ou la plus récente.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valide le fichier sans enregistrer de données.",
        )
        parser.add_argument(
            "--sans-creation-classes",
            action="store_false",
            dest="create_classes",
            default=True,
            help="Refuse les classes absentes au lieu de les créer.",
        )

    def handle(self, *args, **options):
        fichier = Path(options["fichier"])
        if not fichier.exists():
            raise CommandError(f"Fichier introuvable : {fichier}")

        organization = Organization.all_objects.filter(
            slug=options["organisation"]
        ).first()
        if organization is None:
            raise CommandError(
                f"Organisation introuvable : {options['organisation']}."
            )

        school = School.all_objects.filter(
            organization=organization,
            code=normalize_code(options["ecole"]),
        ).first()
        if school is None:
            raise CommandError(
                f"École introuvable : {options['ecole']} "
                f"pour l'organisation {organization.slug}."
            )

        try:
            workbook = load_workbook(
                fichier, data_only=True, read_only=True
            )
        except Exception as exc:
            raise CommandError(
                f"Impossible de lire le classeur Excel : {exc}"
            ) from exc

        with tenant_scope(organization.pk, school.pk):
            academic_year = self._resolve_academic_year(
                school, options["annee"]
            )
            report = run_import(
                workbook,
                organization,
                school,
                academic_year,
                dry_run=options["dry_run"],
                create_classes=options["create_classes"],
            )

        self._print_report(report, options["dry_run"])

        if report.has_errors:
            raise CommandError(
                f"Import annulé : {len(report.errors)} erreur(s). "
                "Aucune donnée n'a été enregistrée."
            )
        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    "Simulation réussie : aucune donnée enregistrée."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Import terminé."))

    def _resolve_academic_year(self, school, name):
        if name:
            academic_year = AcademicYear.objects.filter(
                school=school, name=name.strip()
            ).first()
            if academic_year is None:
                available = ", ".join(
                    AcademicYear.objects.filter(school=school)
                    .order_by("-start_date")
                    .values_list("name", flat=True)
                )
                raise CommandError(
                    f"Année introuvable : {name}. "
                    f"Années disponibles : {available or 'aucune'}."
                )
            return academic_year

        academic_year = current_academic_year(school)
        if academic_year is None:
            raise CommandError(
                "Aucune année scolaire n'existe pour cette école."
            )
        return academic_year

    def _print_report(self, report, dry_run):
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Mode simulation : les données ne seront pas enregistrées."
                )
            )
        if not report.has_errors:
            for label, count in sorted(report.created.items()):
                self.stdout.write(f"  Créés     : {count} — {label}")
            for label, count in sorted(report.updated.items()):
                self.stdout.write(f"  Mis à jour: {count} — {label}")
        else:
            self.stdout.write(
                "  Aucune donnée n'a été enregistrée (rollback)."
            )
        for message in report.warnings:
            self.stdout.write(
                self.style.WARNING(f"  Avertissement — {message}")
            )
        for message in report.errors:
            self.stdout.write(self.style.ERROR(f"  Erreur — {message}"))
