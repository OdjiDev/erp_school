# Organisation et talent

## 1. Conway et inverse Conway

L'architecture d'un système reflète la structure de communication de l'organisation. L'inverse Conway consiste à concevoir l'organisation cible pour obtenir l'architecture voulue — c'est un levier puissant, pas une formule magique.

- Identifier les frontières de domaine avant de découper les équipes.
- Une équipe doit posséder un service de bout en bout, pas une couche technique.
- Les dépendances entre équipes sont des coûts récurrents : les minimiser ou les contractualiser.

## 2. Topologies d'équipes

| Type | Rôle | Attention |
|---|---|---|
| Stream-aligned | livre un flux de valeur | trop de dépendances internes |
| Plateforme | fournit des capacités en self-service | devient gatekeeper |
| Enabling | diffuse une compétence | devient permanent |
| Sous-système complexe | maîtrise un domaine difficile | isolement, bus factor |

Une plateforme est un **produit interne** : utilisateurs, parcours, SLA, documentation, adoption mesurée. Sans adoption, c'est un coût, pas une capacité.

## 3. Charge cognitive

- Une équipe ne peut pas porter plus de deux ou trois domaines complexes.
- Découper selon la charge réelle, pas selon l'organigramme.
- Réduire les interruptions, les responsabilités floues et les dépendances non planifiées.
- Mesurer : temps d'attente, handoffs, nombre de services par équipe, taux d'interruption.

## 4. Carrière staff+

- Progression par l'impact et le scope, pas par le nombre de personnes encadrées.
- Trois axes : profondeur technique, direction technique, multiplication.
- Un staff doit produire des résultats visibles au-delà de son équipe.
- Un fellow doit produire des résultats au-delà de son organisation.
- Barre d'embauche calibrée : mêmes critères pour tous, exemples documentés.

## 5. Succession et bus factor

- Toute zone critique a au moins deux personnes capables d'opérer.
- Un départ doit être un non-événement technique.
- Documenter avant de partir, pas après.
- Identifier les personnes clés et les risques de rétention avant qu'ils ne deviennent des urgences.
- Le mentorat se mesure à l'autonomie croissante des autres.

## 6. Culture et incentives

- Incentives : ce qui est mesuré est optimisé, parfois contre son objectif.
- Sécurité psychologique : signaler un problème doit être sûr et utile.
- Post-mortem sans blâme ; responsabilité des systèmes, pas des individus.
- Récompenser la qualité, la suppression de complexité et le travail invisible.
- Un désaccord doit pouvoir être exprimé sans coût de carrière.

## 7. Réorganisation comme expérience

- Formuler une hypothèse : quel problème, quel mécanisme, quel résultat attendu.
- Définir les métriques et la date de revue avant de réorganiser.
- Réorganiser a un coût : attention, attrition, perte de contexte, cycles de 6 à 12 mois.
- Ne pas réorganiser pour masquer un problème de stratégie ou de compétences.
- Prévoir un plan de communication et des responsabilités explicites.

## 8. Métriques d'ingénierie

- DORA : lead time, fréquence de déploiement, taux d'échec, temps de rétablissement.
- SPACE : satisfaction, performance, activité, communication, efficacité — jamais une seule métrique.
- Adoption de plateforme, temps d'onboarding, temps d'attente, dette.
- Mesurer pour apprendre, pas pour classer les individus.
