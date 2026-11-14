# Conception, ADR, migrations, API

## 1. Du problème à la solution

1. Reformuler le problème et les contraintes (voir cadrage).
2. Décrire le **statu quo** : comment fait-on aujourd'hui, pourquoi ça ne suffit pas.
3. Proposer 2–3 options, dont « ne rien faire » ou « solution minimale ».
4. Évaluer avec une matrice ; recommander une option et assumer le compromis.
5. Écrire la décision (ADR) avant de coder.

## 2. Matrice de trade-offs

| Critère | Option A | Option B | Option C |
|---|---|---|---|
| Complexité | | | |
| Coût initial | | | |
| Coût d'exploitation | | | |
| Réversibilité | | | |
| Risque | | | |
| Délai | | | |
| Compétences requises | | | |

Pondérer les critères selon le contexte. Une option qui gagne partout est suspecte : chercher le coût caché.

## 3. Règles de conception

- **Plus simple d'abord** : pas d'abstraction avant le deuxième cas d'usage réel.
- **Frontières explicites** : modules découplés par des contrats stables, pas par des détails d'implémentation.
- **Une source de vérité** par donnée ; éviter la duplication d'état.
- **Échecs explicites** : erreurs typées, pas de `null` ambigu ni de `catch` silencieux.
- **Idempotence** pour tout traitement rejouable (webhooks, files, retries).
- **Cohérence** : préférer les patterns existants du dépôt, sauf raison documentée.

## 4. ADR

Une ADR tient en une page : contexte, décision, alternatives, conséquences. Elle est immuable : on la remplace par une nouvelle ADR plutôt que de la réécrire. Modèle : `../templates/adr.md`.

Décisions qui méritent une ADR : choix de stockage, contrat d'API public, découpage de service, stratégie d'authentification, format de données persistant, dépendance structurante, mécanisme de migration.

## 5. Migrations de données et de schéma

Toujours en trois temps (**expand → migrate → contract**) :

1. **Expand** : ajouter le nouveau champ/table/service sans casser l'existant ; écrire dans les deux formats si nécessaire.
2. **Migrate** : backfill par lots, idempotent, reprenable, supervisé ; vérifier la cohérence.
3. **Contract** : supprimer l'ancien après une période de recouvrement et vérification.

Règles : sauvegarde avant, script rejouable, batchs bornés, métriques de progression, rollback prévu. Jamais d'`ALTER` bloquant sur une table chaude sans stratégie.

## 6. API

- Contrat d'abord (OpenAPI ou schéma typé), implémentation ensuite.
- Compatibilité ascendante : ajouter des champs optionnels, ne pas changer le sens d'un champ existant.
- Erreurs : statut HTTP correct + code stable + message actionnable ; pas de fuite interne.
- Pagination : curseur pour les grands volumes, pas d'offset profond.
- Écritures : clé d'idempotence pour les opérations sensibles aux retries.
- Autorisation vérifiée côté serveur à chaque requête, pas seulement dans l'UI.
- Versionner seulement ce qui est public ; documenter les dépréciations avec date.

## 7. Dette technique

Toute dette assumée est écrite : cause, coût actuel, coût futur, déclencheur de remboursement. Pas de « on verra plus tard » implicite. Critères économiques : `economie-et-arbitrages.md`.
