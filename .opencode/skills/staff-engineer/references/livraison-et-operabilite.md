# Livraison, opérabilité, incident

## 1. Stratégies de déploiement

| Stratégie | Usage | Risque maîtrisé |
|---|---|---|
| Direct | changement faible risque, réversible | rollback rapide |
| Blue/green | bascule atomique d'environnement | retour instantané |
| Canary | montée progressive du trafic | détection avant impact large |
| Feature flag | activation par cohorte | découplage déploiement/activation |

Règles :
- Un flag a un propriétaire, une date de retrait et un comportement par défaut sûr.
- Déployer et activer sont deux étapes distinctes pour les changements risqués.
- Ne jamais dépendre d'un flag pour la cohérence des données : prévoir les deux états.

## 2. Plan de livraison

Contenu minimal (modèle : `../templates/plan-livraison.md`) :

1. Résumé du changement et risque principal.
2. Pré-requis (migration, config, droits, dépendances).
3. Étapes ordonnées avec vérification après chacune.
4. Observabilité : métriques, logs, dashboard, alertes.
5. Critères de succès et critères d'abandon (seuils chiffrés).
6. Rollback : procédure exacte, temps estimé, perte de données éventuelle.
7. Communication : qui prévenir, quand, avec quel message.

## 3. SLI / SLO / alertes

- **SLI** : mesure du service tel que vu par l'utilisateur (disponibilité, latence, taux d'erreur, fraîcheur).
- **SLO** : cible sur une fenêtre (ex. 99,9 % sur 30 jours).
- **Budget d'erreur** : ce qu'on peut consommer avant de geler les changements risqués.
- Alerter sur la consommation du budget et les symptômes, pas sur chaque cause possible.
- Chaque alerte a un runbook : diagnostic, mitigation, escalade.

## 4. Golden signals

- **Latence** : p50/p95/p99, distinguer succès et erreurs.
- **Trafic** : requêtes/s, messages/s, jobs en attente.
- **Erreurs** : taux, typologie, codes.
- **Saturation** : CPU, mémoire, connexions, files, quotas.

## 5. Incident

Ordre de priorité : **mitiger d'abord, comprendre ensuite**.

1. Déclarer la sévérité et un responsable de coordination.
2. Stabiliser : rollback, flag off, montée en capacité, isolation.
3. Communiquer un statut factuel à intervalle régulier.
4. Préserver les preuves (logs, métriques, versions déployées).
5. Corriger la cause, puis vérifier les métriques de rétablissement.
6. Post-mortem sans blâme : chronologie, causes, facteurs contributifs, actions datées et assignées. Modèle : `../templates/post-mortem.md`.

Ne pas modifier l'état en production pendant un incident sans noter l'heure et l'action : la chronologie est indispensable au post-mortem.

## 6. Runbook

Pour chaque service critique : dépendances, dashboards, alertes, procédures de redémarrage/bascule, accès, contacts, limites connues. Un runbook non testé est une hypothèse, pas une procédure.

## 7. Après livraison

- Vérifier les métriques de succès définies a priori, pas seulement « pas d'erreur ».
- Comparer avant/après sur une fenêtre représentative.
- Retirer les flags et le code mort dans un délai borné.
- Mettre à jour doc, ADR et runbook.
- Consigner la dette assumée et son déclencheur de remboursement.
