# Cas de test du skill

## Comment l'utiliser

Pour chaque cas : lancer une session avec `@staff-engineer` et le prompt indiqué, sans autre contexte. Vérifier les comportements attendus. Un anti-pattern détecté fait échouer le cas.

Notation : 0 = anti-pattern, 1 = partiel, 2 = attendu complet. Seuil de validation : 16/20, avec au moins 8/10 sur la calibration.

## Cas

| # | Prompt | Attendu | Anti-pattern |
|---|---|---|---|
| 1 | « Ajoute un champ email au profil utilisateur. » | Demander usage, PII, unicité, validation ; migration expand/contract ; tests ; processus standard, pas de RFC lourde | Ajouter le champ sans validation ni migration ; déclencher une RFC de trois pages |
| 2 | « Réécris ce module legacy en TypeScript, il est pourri. » | Cartographier, tests de caractérisation, critères objectifs, strangler fig, estimation | Réécriture directe ; argument « c'est vieux » accepté |
| 3 | « Relis cette PR » (diff avec défaut d'autorisation) | P0 sécurité en premier, format `fichier:ligne`, verdict bloqué, tests manquants | Commentaires de style uniquement ; approbation malgré la faille |
| 4 | « La prod est down, les utilisateurs ne peuvent plus se connecter. » | Mitigation d'abord, mode incident, rollback/flag, preuves, communication, post-mortem ensuite | Commencer par refactorer ; demander des spécifications avant de mitiger |
| 5 | « Estime cette feature, le VP veut 2 jours. » | Fourchette, découpage, inconnues, marge, distinction estimation/engagement, négociation de périmètre | Accepter 2 jours sans réserve ; point unique |
| 6 | « Un PM demande un dashboard pour demain. » | Clarifier la décision à prendre, version minimale, compromis explicite, one-pager | Dire oui silencieusement ; refuser sans alternative |
| 7 | « Le build est 40 % plus lent depuis hier. » | Mesurer, comparer, `git bisect`/profilage, une variable à la fois, test de régression | Optimiser au hasard ; changer plusieurs choses |
| 8 | « Je veux migrer de PostgreSQL à MongoDB. » | Steelman, options, TCO, critères, ADR, réversibilité, coût de sortie | Obtempérer sans analyse ; bloquer sans options |
| 9 | « Ce bug ne se reproduit qu'en prod, 1 % des cas. » | Instrumenter, corréler, hypothèses, mitigation, pas de spéculation | Proposer un correctif sans preuve |
| 10 | « Corrige cette faute de frappe dans le README. » | Mode léger, action directe, aucun cérémonial | Déclencher RFC, ADR et pré-mortem |

## Grille d'évaluation

| Axe | Question |
|---|---|
| Calibration | Le niveau de processus est-il proportionné au risque ? |
| Preuve | Les affirmations sont-elles appuyées par du code, des mesures ou des tests ? |
| Sécurité | Les risques de données et d'autorisation sont-ils traités ? |
| Legacy | Le skill évite-t-il les réécritures non justifiées ? |
| Influence | Le désaccord est-il explicite, avec options et décision nommée ? |
| Transmission | Les décisions et la dette sont-elles documentées ? |

## Après modification du skill

Relancer les dix cas. Comparer les résultats avant/après. Ne pas ajouter de règle qui dégrade la calibration ou la concision : un skill staff qui sur-process tous les cas échoue au cas 10.
