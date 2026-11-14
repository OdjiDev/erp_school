# Stratégie technique 2027–2029 — Plateforme de paiement NovaPay

| | |
|---|---|
| **Horizon** | 2027–2029 |
| **Altitude** | Organisation |
| **Décideur** | COMEX |
| **Propriétaire** | CTO |
| **Date de revue** | 2027-06-30 |

## 1. Diagnostic

NovaPay traite 2,4 M de transactions par jour pour 18 000 marchands européens. La croissance est de 35 % par an, mais :

- 62 % des incidents viennent de trois composants couplés (auth, ledger, notifications).
- Le coût d'infrastructure par transaction a augmenté de 28 % en 18 mois.
- La mise en production prend 11 jours en moyenne ; les marchands attendent 4 à 6 semaines pour une évolution.
- 70 % de la connaissance du ledger repose sur deux personnes.

La contrainte critique n'est ni la fonctionnalité ni le marché : c'est la **fiabilité et la vitesse de changement** du cœur de paiement. Continuer à croître sans traiter cette contrainte expose la licence et la réputation.

Ce qui rendrait le diagnostic faux : une baisse de la croissance sous 15 %, ou une migration cloud qui réduirait mécaniquement le coût sans toucher à l'architecture.

## 2. Politique directrice

Payer la fiabilité et la modularité avant la croissance : découpler le ledger, réduire le couplage, automatiser la livraison. Accepter de ralentir les nouvelles fonctionnalités pendant deux trimestres pour supprimer la dette qui limite la vitesse.

## 3. Où jouer / comment gagner

- **Où** : PME et scale-ups européennes, paiements récurrents et reconciliation.
- **Comment** : fiabilité vérifiable (99,99 %), délai d'intégration, conformité native.
- **Pourquoi nous** : expertise ledger, réseau de partenaires, données de reconciliation.
- **Anti-goals** : pas d'expansion US avant 2029, pas de hardware, pas de multi-cloud actif-actif en H1.

## 4. Portefeuille et capacité

| Catégorie | Part | Initiatives | Décision |
|---|---|---|---|
| Paris | 20 % | ledger-as-a-service, IA de reconciliation | financer par petits tickets |
| Cœur | 65 % | découplage ledger, fiabilité, coût | priorité absolue |
| Utilitaires | 10 % | conformité, sécurité | maintenir |
| Déclin | 5 % | connecteurs legacy | sortie progressive |

## 5. Actions cohérentes

| Horizon | Action | Propriétaire | Métrique | Échéance |
|---|---|---|---|---|
| H1 | Découpler auth / ledger / notifications | Staff platform | couplage mesuré, incidents | 2027-Q2 |
| H1 | Tests de caractérisation du ledger | Ledger team | couverture des parcours critiques | 2027-Q1 |
| H1 | Réduire le délai de mise en production à 2 jours | Platform | lead time | 2027-Q3 |
| H2 | Extraire le ledger en service à contrat stable | Ledger team | % trafic migré | 2028-Q1 |
| H2 | Réduire le coût par transaction de 20 % | Platform / FinOps | coût/transaction | 2028-Q2 |
| H3 | Option ledger-as-a-service | Incubation | 3 clients pilotes | 2029 |

## 6. Risques et tripwires

| Risque | Impact | Propriétaire | Tripwire |
|---|---|---|---|
| Migration ledger interrompue | double run prolongé, coût | CTO | si > 6 mois de retard, réévaluer le découpage |
| Perte des deux experts ledger | blocage critique | VP Eng | si attrition > 1, gel des départs |
| Coût cloud non maîtrisé | marge | CFO | si coût/transaction +10 %, revue |
| Régulation paiement | licence | Legal | veille trimestrielle |

## 7. Décisions demandées

| Décision | Coût | Délai | Conséquence de l'inaction |
|---|---|---|---|
| Geler 30 % des nouvelles features en H1 | 1,8 M€ de revenu différé | 2 trimestres | incidents et dette croissants |
| Recruter 2 ingénieurs ledger | 400 k€/an | 6 mois | bus factor de 1 maintenu |
| Budget migration 2,4 M€ | 2027–2028 | 18 mois | plafond de croissance atteint |

## 8. Ce qui doit survivre

ADR du ledger, tests de caractérisation, runbook de migration, documentation des contrats, deux personnes formées par composant critique. La stratégie doit rester lisible et exécutable si le CTO part.
