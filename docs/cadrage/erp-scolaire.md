# Cadrage — Plateforme SaaS de gestion scolaire (Mali)

| | |
|---|---|
| **Statut** | Cadrage validé — socle en construction |
| **Date** | 2026-11-12 |
| **Pays** | Mali |
| **Modèle** | SaaS, 50 clients |
| **Écoles** | 50 à 100, certains clients ont deux écoles homonymes |
| **Sites** | 2 à 5 établissements multi-sites |
| **Niveaux** | 10ème, 11ème, Terminale |
| **Séries** | 10ème CG ; 11ème Lettres / Sciences / Sciences Économiques ; Terminale TSE, TSExp, TSEco, TSS, TLL, TAL (à confirmer) |
| **Classes** | Parallèles : 1ère A, 1ère B… ; 100 élèves par classe |
| **Paiements** | Orange Money, Wave, Mobicash, espèces, virement, chèque |
| **Stack** | Django 6.x, PostgreSQL, HTMX, Django Ninja |
| **Contrainte** | Internet peu stable, électricité, flotte de 50+ sites |

## 1. Décisions validées

- **SaaS multi-tenant** : 50 clients, pas un groupe unique.
- **Écoles homonymes autorisées** : le nom n'est jamais une clé. L'identité est `organization.slug` + `school.code`.
- **Classes parallèles** : une classe = niveau + série + section (A, B, C…). Le libellé « 1ère A » est un affichage.
- **Capacité par défaut** : 100 élèves par classe, surchargeable.
- **Django** : monolithe modulaire, PostgreSQL, pas de microservices.
- **Hors ligne** : nœud local par site + synchronisation cloud.

## 2. Diagnostic

À 50 clients, le problème n'est pas « coder un ERP ». C'est :

- isoler les données de 50 clients sans fuite ;
- gérer des écoles homonymes sans ambiguïté ;
- supporter 100 élèves par classe et des classes parallèles ;
- configurer les séries, matières, coefficients et bulletins sans coder en dur ;
- faire fonctionner les opérations critiques sans Internet ;
- exploiter 50 à 100 nœuds sans support manuel ;
- intégrer des paiements dont les comptes marchands ne sont pas encore clarifiés.

Le risque principal n'est pas la technique : c'est de livrer des bulletins faux ou de mélanger les données de deux clients.

## 3. Modèle de données

### Hiérarchie

```
Organization (client)
└── School (école, code unique par client)
    ├── Site (campus, code unique par école)
    └── AcademicYear
        └── Level → Series
            └── SchoolClass (niveau + série + section)
                └── Enrollment → Student
```

### Identité

- `Organization.slug` : unique globalement.
- `School.code` : unique par organisation. Deux écoles peuvent avoir le même `name`.
- `School.slug` : unique par organisation.
- `Site.code` : unique par école.
- `SchoolClass` : unique par `(school, academic_year, level, series, section)`.
- `Student.matricule` : unique par école.
- `Enrollment` : unique par `(student, academic_year)`.

### Modèles Django

- `tenancy` : `Organization`, `School`, `Site`, `Membership`.
- `academics` : `AcademicYear`, `Level`, `Series`, `Subject`, `Curriculum`, `CurriculumSubject`, `SchoolClass`, `ClassSubject`.
- `students` : `Student`, `Guardian`, `StudentGuardian`, `Enrollment`.
- `grading` : première version intégrée (périodes, évaluations, notes, calculs
  et bulletins imprimables).
- À venir : `finance`, `sync`, `fleet`, `audit`.

## 4. Multi-tenancy

**Schéma partagé, isolation par ligne** : `organization_id` sur les tables client, `school_id` sur les tables scolaires. Pas de schéma PostgreSQL par client : les migrations et la synchronisation de 50 à 100 nœuds deviendraient ingérables.

Règles :

- Aucune requête métier sans filtre client/école.
- Managers « fail closed » : sans contexte tenant, la requête ne retourne rien.
- Contraintes d'unicité toujours scopées par client/école.
- Tests d'isolation obligatoires : un client ne voit jamais les données d'un autre.
- RLS PostgreSQL en défense en profondeur avant la montée en charge.
- Admin Django : filtres explicites, jamais de liste globale non filtrée.

## 5. Structure académique

- **Niveau** : 10, 11, TLE.
- **Série** : rattachée à un niveau (CG en 10ème, LET/SCI/SECO en 11ème, TSE/TSExp/TSEco/TSS/TLL/TAL en Terminale).
- **Curriculum** : par année, niveau et série ; matières, coefficients, volumes horaires.
- **Classe** : niveau + série + section, capacité 100, site, professeur principal.
- **Inscription** : un élève dans une classe pour une année.
- **Règles de calcul** : configurables par niveau/série, jamais codées en dur.
- **Bulletins** : modèles versionnés par série.

La grille officielle (matières, coefficients, format des bulletins) reste à fournir et à valider. C'est le principal risque de conformité.

## 6. Périmètre — quatre tranches

### Tranche 0 — Socle plateforme

- Organisations, écoles, sites, années scolaires.
- Utilisateurs, rôles, permissions, audit.
- Nœud local, synchronisation, console de flotte, sauvegardes.
- **Critère** : un site est provisionné, opérationnel hors ligne, supervisé et sauvegardé.

### Tranche 1 — Socle école

- Niveaux, séries, curricula, matières, classes.
- Élèves, tuteurs, inscriptions.
- Enseignants, affectations.
- Import Excel des matières, coefficients par série, élèves, tuteurs et
  inscriptions, avec simulation et transaction tout-ou-rien.
- **Critère** : une école complète est importée et gérée sans Excel parallèle.

### Tranche 2 — Évaluation et bulletins

- Évaluations, notes, coefficients, moyennes, rang.
- Bulletins PDF par série.
- Délibérations, verrouillage, corrections tracées.
- **Critère** : un trimestre produit des bulletins vérifiés, hors ligne, pour toutes les séries.

**État de l'incrément initial** : la saisie des évaluations et des notes, le
calcul des moyennes pondérées, le rang, l'impression navigateur des bulletins,
la saisie manuelle des décisions du conseil et l'historique motivé des
corrections de notes publiées sont intégrés. La validation des règles
officielles, la clôture des périodes, les versions figées des bulletins, le
rendu PDF serveur et le fonctionnement hors ligne restent à réaliser.

### Tranche 3 — Finances et portail parent

- Frais, échéanciers, paiements, reçus, impayés, clôture de caisse.
- Orange Money, Wave, Mobicash, espèces, virement, chèque.
- Portail parent cloud, notifications.
- **Critère** : solde fiable au franc CFA, caisse justifiée, paiement rapproché.

## 7. Architecture

```
50–100 écoles ── nœud local Django + PostgreSQL ── sync HTTPS ── cloud central Django
                                                                 ├─ consolidation
                                                                 ├─ portail parent
                                                                 ├─ console de flotte
                                                                 └─ sauvegardes
```

- **Nœud local** : Ubuntu, Docker, PostgreSQL, Django, onduleur, disque chiffré.
- **Cloud** : Django multi-tenant, PostgreSQL, portail parent, reporting, supervision.
- **Sync** : asynchrone, idempotente, reprenable ; écritures critiques append-only.
- **Reçus** : numérotation locale par site, sans trou.
- **Migrations** : expand/contract, car les nœuds ne sont pas tous à la même version.

### Stack Django

- Django 6.x, PostgreSQL 16+, psycopg 3.
- Interface : templates Django + HTMX + Alpine ; PWA légère.
- API de synchronisation : Django Ninja.
- PDF : WeasyPrint (ou Playwright si rendu complexe).
- Imports : openpyxl.
- Tâches : worker `sync` basé sur PostgreSQL (`SKIP LOCKED`), pas de broker pour la v1.
- Tests : Django TestCase + tests d'isolation multi-tenant.

## 8. Paiements

- Abstraction fournisseur : `cash`, `orange_money`, `wave`, `mobicash`, `bank_transfer`, `cheque`.
- **Comptes marchands** : chaque école encaisse sur son compte ; la plateforme ne fait pas transiter les frais scolaires. La redevance SaaS est facturée séparément.
- Intégration directe ou agrégateur (à vérifier pour le Mali).
- Jamais de paiement marqué « confirmé » sans confirmation opérateur.
- Espèces : reçu hors ligne, clôture de caisse, écart justifié.
- Montants en XOF, entiers.

## 9. Risques

| Risque | Impact | Mitigation |
|---|---|---|
| Fuite entre clients | perte de confiance, légal | isolation par ligne, tests, RLS, audit |
| Écoles homonymes mal identifiées | données mélangées | code unique, jamais le nom |
| Règles académiques mal comprises | bulletins faux | grille officielle, tests dorés, validation terrain |
| 100 élèves par classe | lenteur de saisie | saisie en masse, pagination, index |
| Flotte de 50+ nœuds | support ingérable | image standard, console, mises à jour par vagues |
| Synchronisation | pertes ou doublons | append-only, idempotence, tests de coupure |
| Comptes marchands flous | paiements impossibles | clarifier avant intégration |
| Coupures électriques | corruption | onduleur, arrêt propre, WAL, sauvegardes |

## 10. Questions restantes

1. Nombre exact d'écoles et de sites par client ; les deux écoles homonymes sont-elles deux entités ou deux campus ?
2. Grille officielle des matières, coefficients et bulletins pour chaque série.
3. Comptes marchands Orange Money, Wave, Mobicash : qui les détient, quels contrats API ?
4. Effectifs réels par classe (100 est la référence) et utilisateurs simultanés.
5. Équipe, budget matériel par site et budget cloud.

## 11. Méthodologie agile de développement

La méthode proposée est un développement Agile par incréments, organisé en cycles Scrum légers de deux semaines au départ. La durée sera ajustée à la capacité de l’équipe. Le Kanban servira au suivi des incidents et demandes urgentes. Chaque cycle doit produire une amélioration utilisable, démontrable et validée par un représentant métier.

### Gouvernance et responsabilités

- **Responsable produit métier** : priorise la valeur, précise les règles, répond aux questions métier et accepte ou refuse les critères de recette.
- **Facilitateur de cycle** : prépare la planification, rend visibles les blocages et organise revue et rétrospective.
- **Responsable technique** : maintient l’architecture modulaire, les ADR, l’isolation multi-tenant, les migrations et les intégrations.
- **Équipe de réalisation** : développe, relit, documente et vérifie les parcours de bout en bout.
- **Référent d’établissement pilote** : fournit les cas réels, valide les écrans et résultats, et signale les écarts aux pratiques de l’école.

Dans une petite équipe, une personne peut porter plusieurs responsabilités; la responsabilité de décision reste explicite.

### Backlog et préparation

Le backlog est organisé en domaines, fonctionnalités puis récits utilisateurs. Chaque récit décrit un rôle, une action, un résultat et des critères d’acceptation observables. Exemple : « En tant que gestionnaire, je peux créer un dossier élève en brouillon avec les informations disponibles. Les champs inconnus restent vides; seuls les champs requis par le profil bloquent l’étape de validation concernée. »

Un élément est prêt à être planifié lorsque le besoin, le rôle, le parcours normal et les erreurs principales sont décrits; que les champs universellement obligatoires, facultatifs ou conditionnels sont précisés; que les droits, la confidentialité, le mode hors ligne et les dépendances sont connus; et qu’un référent peut vérifier des critères d’acceptation concrets. Les décisions métier ouvertes sont inscrites dans le journal des décisions, et les décisions d’architecture dans un ADR.

### Cycle de deux semaines

1. **Planification** : choisir un objectif et des éléments prêts, puis convenir de la démonstration attendue.
2. **Réalisation continue** : intégrer fréquemment les changements, faire les revues et rendre les blocages visibles.
3. **Revue** : démontrer le parcours en préproduction avec des données de démonstration ou anonymisées; consigner validations et écarts.
4. **Rétrospective** : décider d’une amélioration concrète pour le cycle suivant.

Une demande urgente suit une voie Kanban priorisée. Elle ne remplace pas silencieusement l’objectif du cycle : le responsable produit arbitre le changement.

### Ordre de réalisation

- **Tranche 0 — plateforme** : organisations, écoles et sites, rôles, isolation, audit, sauvegarde et restauration. Éprouver tôt un parcours technique local vers cloud, avec reprise et déduplication.
- **Tranche 1 — socle école** : structure académique, élèves, tuteurs, inscriptions, personnel, import Excel et école pilote.
- **Tranche 2 — résultats** : saisie, calculs, bulletins imprimables, décisions manuelles et corrections de notes historisées sont intégrés ; compléter la clôture, les versions figées, le PDF serveur et la conformité après validation des règles officielles par niveau et série.
- **Tranche 3 — finances et portail** : frais, paiements, reçus, caisse, rapprochement et accès parent. Confirmer les comptes marchands et contrats avant d’engager les intégrations opérateurs.
- Les modules de transport, internat, bibliothèque, restauration et achats sont activés et livrés selon le profil de l’établissement.

### Critères de fin et mise en production

Un récit est terminé lorsque ses critères métier sont acceptés, que le code est relu et démontré, que les droits et l’isolation sont contrôlés, que les tests automatisés couvrent les règles modifiées, et que la migration, l’audit et la documentation sont à jour. Les parcours distribués vérifient également la reprise et l’idempotence. Les changements sont d’abord déployés en préproduction, puis dans une école pilote, enfin par vagues. Aucun défaut critique d’isolation ou de calcul ne doit rester ouvert; la sauvegarde et le retour arrière doivent être vérifiables.

La revue périodique suit les récits acceptés, les défauts par gravité, la qualité des imports, les écarts financiers, les opérations de synchronisation en attente, les restaurations et les retours des utilisateurs. La cadence ne doit pas compromettre la sécurité ni l’exactitude scolaire.

## 12. Prochain pas

Socle Django Tranche 0/1 : modèles `tenancy`, `academics`, `students`, contraintes d'unicité, tests d'isolation, admin. Puis import Excel et première école pilote.
