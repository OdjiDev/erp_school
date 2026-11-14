from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.common.excel import normalize_code
from apps.common.tenancy import tenant_scope
from apps.tenancy.excel import build_workbook
from apps.tenancy.models import Organization, School


class Command(BaseCommand):
    help = "Génère un modèle Excel pour l'import de la scolarité."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sortie",
            default="modele_import_scolaire.xlsx",
            help="Chemin du fichier à générer.",
        )
        parser.add_argument(
            "--organisation",
            help="Slug de l'organisation pour remplir les références.",
        )
        parser.add_argument(
            "--ecole",
            help="Code de l'école pour remplir les références.",
        )

    def handle(self, *args, **options):
        organization = None
        school = None

        if bool(options["organisation"]) != bool(options["ecole"]):
            raise CommandError(
                "Les options --organisation et --ecole vont ensemble."
            )

        if options["organisation"] and options["ecole"]:
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
                    f"École introuvable : {options['ecole']}."
                )

        if school is None:
            workbook = build_workbook(
                organization=organization, school=school
            )
        else:
            with tenant_scope(organization.pk, school.pk):
                workbook = build_workbook(
                    organization=organization, school=school
                )

        output = Path(options["sortie"])
        output.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(output)
        self.stdout.write(
            self.style.SUCCESS(f"Modèle Excel généré : {output.resolve()}")
        )
