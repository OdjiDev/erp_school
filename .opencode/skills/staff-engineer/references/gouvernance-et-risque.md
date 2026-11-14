# Gouvernance et risque

## 1. Taxonomie du risque

| Type | Exemples | Propriétaire |
|---|---|---|
| Technique | couplage, SPOF, dette, saturation | architecture |
| Sécurité | faille, secret exposé, supply chain | sécurité |
| Vie privée | PII, consentement, rétention | DPO / legal |
| Réglementaire | secteur, juridiction, audit | conformité |
| Réputationnel | incident public, client, presse | direction |
| Financier | coût cloud, contrat, lock-in | finance / produit |
| Existentiel | perte de données, ban régulateur, dépendance vitale | exécutif |

Un risque sans propriétaire n'est pas géré. Un risque sans appétit explicite ne peut pas être arbitré.

## 2. Registre et indicateurs

- Registre : description, probabilité, impact, propriétaire, mitigation, date de revue.
- KRIs (Key Risk Indicators) : signaux avancés, pas seulement incidents passés.
- Appétit au risque : ce qu'on accepte, ce qu'on refuse, par domaine.
- Revue trimestrielle ; escalade automatique au-delà des seuils.

## 3. Gouvernance qui enable

- **Principes** plutôt que mandats : expliquer le pourquoi, laisser l'implémentation.
- **Paved road** : chemin recommandé, supporté, mesuré ; sortir du chemin reste possible avec justification.
- **Exceptions datées** : toute dérogation a un propriétaire, une raison, une date d'expiration.
- **Fitness functions** : tests automatisés des propriétés d'architecture (latence, couplage, sécurité, coût).
- Éviter le comité gatekeeper : la gouvernance doit accélérer les décisions, pas les enterrer.

## 4. Sécurité et vie privée

- Modélisation des menaces (STRIDE) aux frontières et sur les flux de données.
- Classification des données : publique, interne, confidentielle, réglementée.
- Moindre privilège, séparation des devoirs, rotation des secrets.
- Chaîne d'approvisionnement : dépendances, signatures, provenance, scripts d'installation.
- PII : minimisation, finalité, durée de conservation, droit à l'effacement.
- Tests de sécurité proportionnés au risque : revue, SAST/DAST, pentest, bug bounty.

## 5. Résilience

- RTO/RPO définis par service et par scénario, testés.
- Sauvegardes restaurées régulièrement, pas seulement créées.
- Game days, chaos testing ciblé, exercices de crise.
- Concentration : fournisseur, région, compte, équipe, modèle.
- Plan de sortie pour toute dépendance critique.
- Communication de crise préparée : qui parle, à qui, avec quels faits.

## 6. Réglementation

- Identifier les régimes applicables : données personnelles, secteur financier, santé, IA, cybersécurité.
- Cartographier les obligations en exigences techniques testables.
- Documenter les décisions et les contrôles : l'audit se prépare avant l'audit.
- Associer legal/conformité tôt ; ne pas improviser une interprétation.
- Les exigences évoluent : date de revue et veille.

## 7. Risque existentiel

- Que pourrait tuer l'entreprise ou le service ? Perte de données, faille majeure, dépendance unique, ban régulateur, départ d'une équipe clé.
- Pour chaque scénario : prévention, détection, mitigation, plan de continuité.
- Ne pas noyer les risques existentiels dans un registre de 200 lignes : les isoler et les traiter au niveau exécutif.

## 8. Reporting exécutif

- Trois à cinq risques majeurs, avec impact chiffré et décision attendue.
- Tendances, pas seulement instantané.
- Ce qui a changé depuis la dernière revue.
- Ce qui nécessite un arbitrage, pas seulement une information.
