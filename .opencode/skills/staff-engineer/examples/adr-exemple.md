# ADR-014 — PostgreSQL comme base du service Commandes

- **Statut** : Acceptée
- **Date** : 2026-03-12
- **Décideurs** : équipe Commandes, responsable plateforme
- **Contexte technique** : service commandes, 4 développeurs, PostgreSQL déjà exploité

## Contexte

Le service Commandes gère 50 000 commandes par jour et doit garantir des transactions multi-tables (commande, lignes, paiement, stock). L'équipe connaît PostgreSQL ; personne n'exploite de base documentaire en production. Le reporting nécessite des requêtes ad hoc et des jointures.

## Décision

Utiliser PostgreSQL 16 : une instance primaire, un réplica de lecture pour le reporting, partitionnement mensuel au-delà de 10 millions de lignes.

## Alternatives considérées

- **MongoDB** — schéma flexible, mais transactions multi-documents moins naturelles, reporting par jointures coûteux, aucune compétence interne.
- **DynamoDB** — scalabilité forte, mais lock-in, requêtes ad hoc limitées et modèle de coût difficile à prévoir.
- **Conserver MySQL legacy** — version en fin de support, migrations bloquées, pas de gain fonctionnel.

## Conséquences

**Positives**
- ACID natif, compétences existantes, reporting SQL.
- Sauvegardes et runbooks déjà maîtrisés.

**Négatives / coûts**
- Scaling vertical limité ; partitionnement à opérer.
- Migrations de schéma à gérer avec attention.

**Neutres**
- Pas de changement d'infrastructure ni de nouvelle dépendance.

## Suivi

- Revoir si le débit dépasse 5 000 écritures/s ou 50 millions de lignes.
- Former deux développeurs au partitionnement avant le premier seuil.
- Vérifier le runbook de restauration au prochain trimestre.
