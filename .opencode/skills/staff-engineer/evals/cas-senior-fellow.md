# Cas de test — niveau Senior Fellow

## Comment l'utiliser

Lancer chaque cas avec `@staff-engineer` et le prompt seul. Vérifier les comportements attendus. Un anti-pattern détecté fait échouer le cas.

Notation : 0 = anti-pattern, 1 = partiel, 2 = attendu complet. Seuil : 20/24, avec au moins 10/12 sur la calibration et aucun cas à 0.

## Cas

| # | Prompt | Attendu | Anti-pattern |
|---|---|---|---|
| 1 | « Le CEO veut tout migrer chez un seul fournisseur cloud pour économiser 20 %. » | TCO complet incluant coût de sortie, risque de concentration, options, scénarios, décision progressive avec tripwires | Accepter l'économie affichée sans coût de sortie ; refuser sans alternative chiffrée |
| 2 | « Comment réorganiser 200 ingénieurs après l'acquisition ? » | Hypothèse causale, Conway, topologies, charge cognitive, culture, métriques, plan de communication, date de revue | Organigramme posé comme solution ; réorganisation sans métrique |
| 3 | « Faut-il construire notre propre LLM ? » | Build/buy/partner, différenciation, TCO, compétences, risque modèle, optionnalité, pilote à faible coût | Oui/non binaire ; « tout le monde le fait » |
| 4 | « Le board demande un plan technique à 3 ans. » | Diagnostic, politique directrice, H1/H2/H3, anti-goals, capacité, risques, métriques, one-pager | Liste de projets ; slideware sans diagnostic |
| 5 | « Une équipe veut Kubernetes partout. » | Plateforme comme produit, golden path, charge cognitive, TCO, migration, adoption mesurée, exceptions | Mandat global ; adoption sans coût ni support |
| 6 | « Due diligence avant d'acquérir cette startup. » | Dimensions, preuves, red flags, registre de risques chiffré, conditions, scénarios | Avis fondé sur les slides ; conclusion sans preuve |
| 7 | « Notre plateforme legacy freine toutes les équipes. » | Portefeuille, strangler fig, tests de caractérisation, financement, séquencement, métriques, organisation | Réécriture big bang ; « c'est vieux » |
| 8 | « Un staff menace de partir. » | Risque de personne clé, succession, incentives, conversation honnête, plan de rétention, bus factor | Contre-offre immédiate sans traiter la cause |
| 9 | « Réduis les coûts cloud de 30 % en 6 mois. » | FinOps, unit economics, quick wins vs structurel, garde-fous SLO, risque de couper la fiabilité | Coupes aveugles ; optimisation sans mesure |
| 10 | « Faut-il ouvrir notre API publiquement ? » | Stratégie écosystème, différenciation, coût de support, sécurité, versionnement, modèle économique, optionnalité | Ouverture par mode ; refus sans analyse |
| 11 | « Le régulateur demande un plan IA pour l'AI Act. » | Gouvernance, classification des risques, données, documentation, contrôles, legal, jalons, incertitudes | Interprétation juridique improvisée ; plan hors délai |
| 12 | « Corrige cette faute de frappe dans le README. » | Mode léger, action directe, aucun cérémonial | RFC, ADR, comité, analyse de portefeuille |

## Grille d'évaluation

| Axe | Question |
|---|---|
| Altitude | Le niveau est-il calibré à la question ? |
| Diagnostic | La contrainte critique est-elle nommée avant la solution ? |
| Business | L'outcome et l'ordre de grandeur sont-ils explicites ? |
| Options | Le statu quo et la réversibilité sont-ils traités ? |
| Second ordre | Les effets de bord et incentives sont-ils considérés ? |
| Organisation | Conway, charge cognitive et talent sont-ils pris en compte ? |
| Risque | Propriétaires, tripwires et scénarios existent-ils ? |
| Exécution | Métriques, kill criteria et date de revue sont-ils définis ? |
| Influence | La décision demandée est-elle claire et pré-alignée ? |
| Transmission | Ce qui doit survivre est-il documenté ? |

## Après modification

Relancer les 12 cas. Un skill fellow qui sur-process le cas 12 a échoué, même si les 11 autres sont parfaits.
