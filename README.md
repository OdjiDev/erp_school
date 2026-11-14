# Plateforme SaaS de gestion scolaire — Mali

Socle Django multi-tenant pour établissements privés maliens. Le projet vise
50 clients, 50 à 100 écoles, des classes parallèles de 100 élèves et un
fonctionnement hors ligne sur chaque site.

## État actuel

- Tranches 0/1 en cours ; un premier incrément de la tranche 2 (notes et bulletins imprimables) est intégré.
- Apps disponibles : `tenancy`, `academics`, `students`, `grading`.
- Interface web : connexion, sélection d'école, tableau de bord, structure
  académique (années, niveaux, séries), matières et coefficients, élèves,
  tuteurs, inscriptions, classes, utilisateurs/rôles, enseignants et import
  Excel, évaluations, saisie des notes et bulletins.
- Listes de classe imprimables et export Excel des effectifs.
- Contrôle d'accès par organisation et par école.
- Import Excel des matières, coefficients par série et élèves, avec modèle
  téléchargeable, simulation et transaction tout-ou-rien.
- Managers ORM multi-tenant fermés sans contexte, avec accès système explicite
  via `all_objects`.
- Pas encore de synchronisation locale/cloud, de finances ni de portail parent.
- La clôture des périodes et les versions figées des bulletins sont intégrées ;
  les PDF serveur et la recette avec les écoles pilotes restent à compléter.

## Stack

- Python 3.14, Django 6.1
- PostgreSQL 16+ en production, SQLite en développement
- Templates Django + CSS, HTMX prévu pour les écrans interactifs
- Django Ninja pour l'API de synchronisation (à venir)
- Impression des bulletins via le navigateur (PDF serveur à venir)
- openpyxl pour les imports Excel (Tranche 1)

## Démarrage

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

- Application : `http://127.0.0.1:8000/`
- Connexion : `http://127.0.0.1:8000/connexion/`
- Admin : `http://127.0.0.1:8000/admin/`
- Contrôle de santé : `http://127.0.0.1:8000/health/`

`seed_demo` crée une organisation de démonstration avec **deux écoles
homonymes** (`DEMO-A`, `DEMO-B`), des classes parallèles, des élèves, des
tuteurs et des inscriptions. La commande est idempotente.

Pour utiliser PostgreSQL, renseigner `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_HOST` et `POSTGRES_PORT` dans `.env`.
Sans `POSTGRES_DB`, le projet utilise `db.sqlite3`.

## Accès et isolation

Les URLs utilisent le slug de l'organisation et le code de l'école, jamais
le nom :

```text
/o/<organization_slug>/s/<school_code>/
```

Exemple : `/o/demo/s/DEMO-A/`.

- Un superutilisateur accède à toutes les écoles.
- Un membre d'organisation accède à toutes les écoles de son organisation.
- Un membre rattaché à une école n'accède qu'à cette école.
- Les rôles parent et élève ne sont pas admis dans le back-office scolaire.
- L'import Excel est réservé aux administrateurs (plateforme, client, école)
  et au secrétariat ; les enseignants, comptables et auditeurs y sont refusés.
- La structure académique (années, niveaux, séries) est réservée aux mêmes
  rôles de gestion.
- La gestion des utilisateurs est réservée aux administrateurs plateforme,
  client et école. Un directeur d'école ne voit et ne modifie que les comptes
  rattachés à son école ; il ne peut pas attribuer `org_admin` ni une portée
  organisation.
- Un utilisateur ne peut ni désactiver son propre compte, ni retirer son
  propre rôle de gestion des utilisateurs.
- Une école inexistante renvoie 404 ; une école non autorisée renvoie 403.
- Les listes d'élèves, de classes et les tableaux de bord sont filtrés par
  école et par année scolaire.
- Les vues d'école établissent un `tenant_scope` avant leurs requêtes ORM.
- `objects` ne retourne rien sans scope et refuse les créations hors scope ;
  `all_objects` est réservé au routage, à l'admin plateforme, aux tâches système
  et aux lectures internes limitées à un enregistrement parent.

## Structure académique

Le menu **Structure** regroupe les années scolaires, les niveaux et leurs
séries. Les niveaux et séries doivent exister avant de créer des classes ou
d'importer des élèves.

- Une année est identifiée par son nom (`2026-2027`) à l'intérieur de l'école ;
  une seule année peut être marquée **Courante**.
- Un niveau porte un code stable (`10`, `11`, `TLE`) et un ordre d'affichage.
- Une série est rattachée à un niveau ; son niveau est verrouillé en
  modification pour éviter de déplacer des classes et des coefficients.
- Les codes sont normalisés en majuscules et contrôlés en unicité.
- Aucune suppression n'est proposée pour l'instant : les données liées
  (classes, inscriptions, coefficients) seraient perdues en cascade.
- Les formulaires valident l'appartenance à l'école ; une année, un niveau ou
  une série d'une autre école renvoie 404.

## Élèves, tuteurs et inscriptions

- **Élèves** : création et modification de l'identité, du statut et des
  coordonnées. Le matricule est unique par école ; laissé vide à la création,
  il est généré automatiquement. Il reste obligatoire en modification.
- **Tuteurs** : annuaire partagé par les écoles d'une même organisation.
  Un tuteur peut être créé depuis la fiche élève ou rattaché à un tuteur
  existant, avec lien de parenté, tuteur principal et responsable financier.
- Un seul tuteur principal est conservé par élève ; déclarer un nouveau
  principal retire ce statut au précédent.
- Retirer un lien ne supprime pas le tuteur.
- **Inscriptions** : une seule inscription par élève et par année. À la
  modification, l'élève et l'année sont verrouillés ; seule la classe, le
  statut et les dates restent modifiables.
- La liste des inscriptions se filtre par année, classe, statut et recherche.

## Matières, coefficients et classes

- **Matières** : référentiel par école, codes normalisés en majuscules et
  uniques dans l'école.
- **Coefficients** : un programme par année, niveau et série. Une page unique
  permet de créer le programme puis d'y ajouter les matières avec coefficient
  et volume horaire.
- **Classes** : identifiées par année, niveau, série et section. À la
  création, les matières du programme de coefficients sont reprises
  automatiquement dans les affectations de la classe.
- Dès qu'une classe compte des inscriptions, année, niveau, série et section
  sont verrouillés.
- **Affectations** : chaque matière de la classe peut être confiée à un
  enseignant actif de l'école. La fiche de classe affiche la liste des élèves,
  les effectifs, le remplissage et les enseignants.
- **Exports** : la liste de classe est imprimable et exportable en `.xlsx`
  (matricule, identité, sexe, naissance, tuteur principal et téléphone).

## Utilisateurs, rôles et enseignants

- La gestion des comptes est réservée aux administrateurs plateforme, client
  et école.
- Un compte peut cumuler plusieurs rôles, avec une portée limitée à une école
  ou étendue à toute l'organisation.
- Un administrateur client peut attribuer des rôles dans l'école courante ou
  au niveau de l'organisation ; pour une autre école, il ouvre directement
  l'URL de cette école.
- Un directeur d'école ne peut pas ouvrir la fiche d'un compte uniquement
  rattaché à l'organisation : les administrateurs client restent hors de sa
  portée.
- Les protections empêchent l'auto-désactivation, le retrait de son propre
  accès à la gestion des utilisateurs et la modification de son propre rôle
  actif depuis la liste.
- La réinitialisation de mot de passe est disponible pour les comptes dans le
  périmètre autorisé.
- La page **Enseignants** liste les rôles enseignants de l'école (y compris
  les portées organisation) et le nombre d'affectations de l'année courante.

## Notes et bulletins

Le menu **Notes et bulletins** permet de configurer les périodes par école et
année scolaire (trimestre, semestre ou libellé personnalisé), de créer des
évaluations par classe et matière, puis de saisir les notes de toute la classe.

- Le barème de chaque évaluation est configurable ; le calcul convertit les
  résultats sur 20 et applique le poids de l'évaluation.
- Une évaluation ne peut être publiée tant que chaque élève actif n'a pas une
  note, un statut d'absence ou un statut de dispense.
- Une évaluation publiée devient non modifiable depuis l'interface et alimente
  les moyennes de matière, les moyennes générales pondérées par les
  coefficients du programme et le classement de la classe.
- Une matière sans coefficient configuré reste visible mais n'entre pas dans
  la moyenne générale ; le bulletin le signale explicitement.
- Les absences et dispenses sans note sont exclues des calculs. Un zéro peut
  être saisi si le règlement de l'établissement prévoit une pénalité.
- Les bulletins affichent les résultats, les coefficients, le rang et les
  absences/dispenses. Ils sont imprimables ou enregistrables en PDF depuis le
  navigateur.
- Un responsable peut saisir la décision du conseil sans seuil de réussite
  automatique. Une correction de note publiée exige un motif et conserve les
  valeurs avant/après, l'auteur et la date.
- Une période ne peut être clôturée que si toutes ses évaluations sont
  publiées. La clôture fige une version des bulletins ; une réouverture exige
  un motif et reste tracée dans l'historique.
- Les enseignants ne voient que leurs classes et évaluations affectées ; les
  rôles de gestion peuvent administrer les périodes et toutes les notes de
  leur périmètre.
- La règle de passage, les appréciations et le modèle officiel malien restent
  à valider avec les écoles pilotes.

## Import Excel

Depuis l'interface : menu **Import Excel**, puis bouton **Télécharger le
modèle**. Le modèle contient les feuilles `Mode d'emploi`, `Matieres`,
`Coefficients`, `Eleves` et `References` (années, niveaux, séries, matières et
classes existantes de l'école).

Feuilles attendues :

- `Matieres` : `Code`, `Nom`.
- `Coefficients` : `Niveau`, `Série`, `Matière`, `Coefficient`, `Heures`.
- `Eleves` : identité, classe et tuteur.

Règles d'import :

- les codes sont normalisés en majuscules ;
- les niveaux, séries et matières sont acceptés par code ou par nom ;
- le matricule est obligatoire et sert d'identifiant stable ;
- les dates acceptent `JJ/MM/AAAA` ou `AAAA-MM-JJ` ;
- une classe absente peut être créée automatiquement avec une capacité de 100 ;
- l'import est transactionnel : une seule ligne invalide annule tout ;
- l'interface lance une simulation par défaut.

Ligne de commande équivalente :

```powershell
.venv\Scripts\python.exe manage.py excel_template --sortie modele.xlsx --organisation demo --ecole DEMO-A
.venv\Scripts\python.exe manage.py import_excel modele.xlsx --organisation demo --ecole DEMO-A --annee 2026-2027 --dry-run
.venv\Scripts\python.exe manage.py import_excel modele.xlsx --organisation demo --ecole DEMO-A --annee 2026-2027
```

Options utiles : `--annee`, `--dry-run`, `--sans-creation-classes`.

## Configuration de production

- `DJANGO_DEBUG=0` exige un `DJANGO_SECRET_KEY` explicite.
- `DJANGO_SECURE_SSL=0` convient à un nœud local en HTTP sur le réseau de
  l'école.
- `DJANGO_SECURE_SSL=1` active HTTPS, HSTS et les cookies sécurisés pour le
  cloud derrière un reverse proxy.
- Les nœuds locaux ne doivent pas activer HSTS s'ils servent du HTTP en LAN.

## Tests

```powershell
.venv\Scripts\python.exe manage.py test
```

La suite couvre notamment :

- écoles homonymes identifiées par leur code ;
- classes parallèles et capacité par défaut de 100 élèves ;
- matricule unique par école ;
- tuteurs partagés entre plusieurs écoles d'une même organisation ;
- inscription unique par élève et par année ;
- cohérence école / année / classe d'une inscription ;
- contrôle d'accès aux écoles et aux organisations ;
- listes et tableaux de bord filtrés par école ;
- import Excel : matières, coefficients par série, élèves, tuteurs et
  inscriptions ;
- simulation, rollback intégral en cas d'erreur et téléchargement du modèle ;
- idempotence du jeu de démonstration.
- managers fermés sans contexte et isolation ORM par organisation/école.
- structure académique : listing, création et modification des années,
  niveaux et séries, unicité des codes, année courante unique, refus des
  rôles non gestionnaires et isolation entre écoles ;
- élèves et tuteurs : création, matricule automatique ou obligatoire,
  doublons, liaison d'un tuteur, tuteur principal unique et retrait d'un lien ;
- inscriptions : création, doublon élève/année, verrouillage de l'élève et de
  l'année, filtres et absence d'année scolaire ;
- matières, coefficients et classes : unicité, reprise des matières du
  programme, verrouillage après inscription, affectations et export `.xlsx` ;
- utilisateurs et rôles : portées école/organisation, refus d'escalade,
  auto-protection, réinitialisation de mot de passe et liste des enseignants ;
- notes et bulletins : pondération, publication, corrections motivées,
  délibérations, clôture avec versions figées, réouverture motivée et
  immuabilité des archives.

## Structure

```text
config/                  Paramètres et URLs Django
apps/common/             Modèles abstraits (UUID, horodatage)
apps/tenancy/            Organisations, écoles, sites, rôles, accès web
apps/academics/          Années, niveaux, séries, matières, classes
apps/students/           Élèves, tuteurs, inscriptions
apps/grading/            Périodes, évaluations, notes et bulletins
templates/               Interface française
static/css/              Feuille de style locale, sans CDN
docs/cadrage/            Cadrage fonctionnel et technique
docs/decisions/          Décisions d'architecture (ADR)
```

## Règles d'identité

- Une organisation est identifiée par son `slug`, unique globalement.
- Une école est identifiée par `(organization, code)`. Deux écoles peuvent
  porter le même nom.
- Un site est identifié par `(school, code)`.
- Une classe est identifiée par
  `(school, academic_year, level, series, section)`.
- Un élève est identifié par `(school, matricule)`.
- Une inscription est unique par `(student, academic_year)`.

Le nom d'une école ou d'une classe n'est jamais utilisé comme clé.

## Documentation

- [Cahier des spécifications ERP](docs/cadrage/Cahier_des_specifications_ERP_scolaire_Mali_v1_2.docx)
- [Planification des sprints ERP](docs/cadrage/Planification_sprints_ERP_scolaire_Mali_v1.docx)
- [Cadrage](docs/cadrage/erp-scolaire.md)
- [ADR-001 — Architecture multi-site](docs/decisions/ADR-001-architecture-multi-site.md)
- [ADR-002 — Flotte de nœuds locaux](docs/decisions/ADR-002-flotte-noeuds-locaux.md)
- [ADR-003 — Multi-tenancy Django](docs/decisions/ADR-003-multi-tenancy-django.md)
- [ADR-004 — Identité des écoles et classes](docs/decisions/ADR-004-identite-ecoles-classes.md)

## Prochaines étapes

1. Vérifier les règles de calcul et modèles de bulletin avec les écoles pilotes.
2. Ajouter le PDF serveur des bulletins.
3. Sauvegardes, restauration et recette de déploiement du nœud local.
4. Frais scolaires, paiements, synchronisation locale/cloud et portail parent.

## Points à confirmer

- Grille officielle des matières, coefficients et modèles de bulletins par
  série.
- Nombre exact d'écoles et de sites par client.
- Statut des écoles homonymes : deux établissements ou deux campus.
- Comptes marchands Orange Money, Wave et Mobicash, et contrats API.
