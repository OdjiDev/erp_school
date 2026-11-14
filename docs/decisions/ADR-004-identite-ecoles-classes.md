# ADR-004 — Identité des écoles et structure académique

- **Statut** : Acceptée
- **Date** : 2026-11-12
- **Décideur(s)** : Direction, direction pédagogique
- **Contexte** : 50 clients, écoles homonymes, classes parallèles de 100 élèves, séries multiples

## Contexte

Certains clients possèdent deux écoles portant le même nom. Les classes peuvent être parallèles : 1ère A, 1ère B, etc. Une classe peut accueillir 100 élèves. Les niveaux vont de la 10ème à la Terminale, avec plusieurs séries. Le nom d'une école ou d'une classe ne peut donc pas servir de clé.

## Décision

### Écoles

- `Organization` (client) → `School` → `Site`.
- `School.name` est un libellé, non unique.
- `School.code` est unique par organisation ; `School.slug` est unique par organisation.
- Les URLs utilisent `organization.slug` + `school.code`, jamais le nom.
- Deux campus d'une même école sont des `Site`, pas deux `School`.

### Classes

- Une classe = `academic_year` + `level` + `series` + `section`.
- `section` : A, B, C… (chaîne courte, normalisée en majuscules).
- `name` est un libellé d'affichage optionnel (« 1ère A »).
- Contrainte unique : `(school, academic_year, level, series, section)`.
- Capacité par défaut : 100, surchargeable ; avertissement au-delà.
- Le site est optionnel si l'école n'a qu'un campus.

### Curriculum

- `Curriculum` : année + niveau + série.
- `CurriculumSubject` : matière + coefficient + volume horaire.
- Les coefficients sont propres à chaque série.
- Aucune règle de calcul codée en dur.

## Alternatives considérées

- **Nom de l'école comme clé** — rejeté : deux écoles homonymes deviennent ambiguës.
- **Nom de classe libre comme clé** — rejeté : « 1ère A » peut exister dans plusieurs écoles et plusieurs années.
- **Une seule classe par niveau** — rejeté : les sections parallèles sont nécessaires.
- **Séries codées en dur** — rejeté : la grille officielle peut évoluer.

## Conséquences

**Positives**
- Écoles homonymes supportées sans ambiguïté.
- Classes parallèles et capacité de 100 gérées nativement.
- Reporting par niveau, série et section.
- curricula configurables sans migration.

**Négatives / coûts**
- Plus de champs et de contraintes à maintenir.
- Les libellés doivent être générés ou saisis avec soin.
- Les imports Excel doivent fournir les codes, pas seulement les noms.

## Règles

- Normaliser les codes en majuscules, sans espaces.
- Ne jamais utiliser `name` dans une clé étrangère, une URL ou une contrainte d'unicité.
- `full_clean()` dans les formulaires et l'admin pour vérifier la cohérence école/niveau/série.
- Tests : écoles homonymes, classes parallèles, doublons, capacité.
