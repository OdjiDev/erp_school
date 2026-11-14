# Grille de validation Senior Fellow

## Règle

Un livrable est validé au niveau Senior Fellow si **20/20 des critères applicables** sont présents avec une preuve explicite. Un critère non applicable doit être justifié par écrit. Plus de 4 critères non applicables invalident la revue : le niveau d'altitude est probablement trop élevé pour la question.

La validation est binaire : présent ou absent. Pas de crédit partiel. Une intention non écrite est absente.

## Les 20 critères

| # | Critère | Preuve attendue | Emplacement |
|---|---|---|---|
| 1 | **Altitude calibrée** | niveau annoncé et justifié ; pas de sur-scope | SKILL.md, Altitude |
| 2 | **Diagnostic explicite** | contrainte critique, faits, ce qui rendrait le diagnostic faux | Stratégie |
| 3 | **Outcome business** | revenu, coût, risque, vitesse ou option, avec ordre de grandeur | Règles |
| 4 | **Options** | au moins deux options + statu quo / ne rien faire | Conception |
| 5 | **Coût total** | TCO, unit economics, coût d'exploitation | Économie |
| 6 | **Réversibilité** | prix de l'option, décision irréversible identifiée | Décision |
| 7 | **Second ordre** | effets de bord, « et ensuite ? », scénarios de rupture | Systèmes |
| 8 | **Incentives** | Goodhart, métriques de garde-fou, alignement | Systèmes |
| 9 | **Portefeuille** | impact capacité, catégorie, kill criteria | Stratégie |
| 10 | **Build/buy/partner** | comparaison explicite et coût de sortie | Stratégie |
| 11 | **Organisation** | Conway, topologie, charge cognitive | Organisation |
| 12 | **Talent** | bus factor, succession, rétention | Organisation |
| 13 | **Risques** | taxonomie, propriétaire, tripwires | Gouvernance |
| 14 | **Sécurité/conformité** | PII, menaces, régulation applicable | Gouvernance |
| 15 | **Gouvernance** | principes, paved road, exception datée, migration | Gouvernance |
| 16 | **Influence exécutive** | one-pager, décision demandée, pré-alignement | Influence |
| 17 | **Désaccord** | steelman, disagree and commit, escalade avec options | Influence |
| 18 | **Preuves** | sources, confiance, hypothèses falsifiables | Posture |
| 19 | **Exécution** | métriques, jalons, date de revue, critère d'abandon | Déroulé |
| 20 | **Transmission** | ADR, doc, dette, succession | Definition of Done |

## Procédure de revue

1. Lire le livrable sans chercher à l'améliorer.
2. Pour chaque critère, citer la phrase ou la section qui le prouve.
3. Si la preuve est absente, cocher « absent » — ne pas reconstruire l'intention.
4. Vérifier la calibration : un critère d'altitude organisation n'est pas requis pour un correctif trivial ; il doit alors être marqué N/A avec justification.
5. Compter : 20/20 applicables = validé. Sinon, renvoyer avec la liste des critères absents.

## Revue de la calibration

| Question | Si non |
|---|---|
| L'altitude est-elle proportionnée à la demande ? | Sur-scope ou sous-scope |
| Le processus est-il proportionné au risque ? | Bureaucratie ou imprudence |
| Les preuves sont-elles proportionnées à l'enjeu ? | Opinion déguisée en analyse |
| La décision peut-elle être prise avec ce document ? | Document descriptif, pas décisionnel |

## Signature

| | |
|---|---|
| **Relecteur** | |
| **Date** | |
| **Score** | /20 applicables |
| **Verdict** | Validé / Renvoyé |
| **Critères absents** | |
