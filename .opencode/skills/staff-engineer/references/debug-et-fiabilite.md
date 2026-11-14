# Debug et fiabilité

## 1. Méthode

1. **Reproduire** : environnement, version, données, fréquence, utilisateurs affectés.
2. **Stabiliser** : réduire au plus petit cas reproductible.
3. **Observer** : logs, traces, métriques, profiler, état du système.
4. **Formuler une hypothèse falsifiable** — pas une intuition.
5. **Expérimenter** : un changement à la fois.
6. **Corriger** au minimum, ajouter un test de régression.
7. **Vérifier** en conditions réelles, puis surveiller.

## 2. Questions de départ

- Quand ça a commencé ? Qu'est-ce qui a changé : deploy, config, données, trafic, dépendance ?
- Qui est impacté, où, dans quelle proportion ?
- Ça se reproduit en local ? En staging ? Avec quelles données ?
- Quelle est la différence exacte entre le cas qui marche et celui qui échoue ?
- Le problème est-il stable ou intermittent ? Quelle est la période ?

## 3. Outils

- `git bisect` pour les régressions ; comparer les versions déployées.
- Corrélation par request ID / trace ID sur toute la chaîne.
- Profilage CPU, mémoire, allocations avant toute optimisation.
- Requêtes lentes : plan d'exécution, index, volume, verrous.
- Files : profondeur, âge du plus vieux message, dead letter queue.
- Réseau : DNS, TLS, timeouts, pertes, latence par segment.

## 4. Failure modes distribués

| Mode | Symptôme | Mitigation |
|---|---|---|
| Retry storm | pic de charge après une erreur | backoff exponentiel + jitter |
| Thundering herd | tous les clients au même instant | jitter, cache, rate limiting |
| Partial failure | résultat partiel présenté comme complet | erreurs explicites, compensation |
| Poison message | message rejoué en boucle | dead letter queue, quarantaine |
| Backpressure absente | file qui grandit sans fin | bornes, load shedding |
| Timeout mal choisi | retries en cascade | budget de timeout par appel |
| Doublon de livraison | effet appliqué deux fois | clé d'idempotence |
| Cache froid | latence au démarrage | préchauffage, stale-while-revalidate |

## 5. En production

- Mitiger d'abord : rollback, flag off, montée en capacité, isolation.
- Préserver les preuves : logs, métriques, versions, heures des actions.
- Communiquer factuellement à intervalle régulier.
- Ne pas modifier l'état sans noter l'heure et l'action.
- Post-mortem sans blâme ensuite : `../templates/post-mortem.md`.

## 6. Prévention

- SLO et alertes sur les symptômes utilisateur, pas sur chaque cause possible.
- Runbooks testés ; game days et chaos testing ciblés.
- Budget d'erreur : geler les changements risqués quand il est consommé.
- Revue des incidents récurrents : une cause racine, pas seulement un correctif.
