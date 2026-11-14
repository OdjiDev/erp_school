# Legacy et brownfield

## 1. Avant de toucher

- Cartographier : points d'entrée, flux, dépendances, données, jobs, dashboards, alertes.
- Identifier les zones chaudes : churn × complexité × incidents.
- Lire l'historique git, les ADR, les runbooks, les tickets récurrents.
- Parler aux personnes qui maintiennent : elles savent ce que la doc ignore.
- Vérifier ce qui est réellement utilisé avant de supprimer quoi que ce soit.

## 2. Tests de caractérisation

- Écrire des tests qui capturent le comportement actuel, même imparfait.
- Le but est de détecter les régressions, pas de valider le design.
- Couvrir les parcours critiques et les cas bizarres documentés.
- Si le code est impossible à tester, extraire d'abord un seam.

## 3. Seams

- Isoler une frontière derrière une interface pour pouvoir tester et remplacer.
- Injecter les dépendances : horloge, réseau, base, aléatoire.
- Ne pas réécrire pour tester ; tester pour pouvoir réécrire.
- Un seam mal choisi fuit les détails d'implémentation : viser un contrat métier.

## 4. Strangler fig

1. Router une petite partie du trafic vers le nouveau chemin.
2. Double écriture ou comparaison de résultats pour vérifier la parité.
3. Mesurer les écarts fonctionnels et les corriger.
4. Augmenter progressivement la proportion.
5. Couper l'ancien après une période de recouvrement.
6. Supprimer le code mort et les flags.

Chaque étape est déployable et réversible. Jamais de bascule big bang sans filet.

## 5. Réécriture

Critères objectifs : coût de maintenance, fréquence des incidents, vélocité, sécurité, dépendances mortes, compétences disponibles.

Estimer : migration + double run + formation + imprévus. Refuser « c'est vieux » comme argument. Une réécriture sans tests de caractérisation est une prise de risque non mesurée.

## 6. Dépendances

- Versions, licences, vulnérabilités, mainteneur, bus factor.
- Plan de sortie pour toute dépendance critique abandonnée.
- Verrouiller les versions en production ; mettre à jour régulièrement, pas en urgence.
- Surveiller la chaîne d'approvisionnement (typosquatting, scripts post-install).

## 7. Documentation

- Carte du système : composants, flux, données, propriétaires.
- ADR rétroactives pour expliquer les décisions existantes.
- Runbook pour les opérations courantes et les incidents.
- Documenter ce qu'on découvre en chemin : c'est le meilleur moment.

## 8. Règles

- Un pas à la fois, chaque pas déployable.
- Ne pas mélanger migration et nouvelle fonctionnalité.
- Toujours un plan de retour.
- Mesurer avant/après : latence, erreurs, coût, vélocité.
- Ne pas laisser une migration à moitié faite sans date de reprise.
