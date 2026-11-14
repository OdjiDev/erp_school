# Cadrage, priorisation, estimation

## 1. Cadrer le problème

Répondre par écrit, en dix lignes maximum :

- **Problème** : quel utilisateur, quel parcours, quelle douleur observable ?
- **Preuve** : donnée, ticket, incident, retour client — pas une intuition.
- **Succès** : quel comportement mesurable change ? (métrique + seuil + horizon)
- **Non-goals** : ce qu'on ne fait pas maintenant, explicitement.
- **Contraintes** : stack, compatibilité, délai, équipe, budget, réglementation.
- **Risque principal** : ce qui peut faire échouer le projet.

Si une réponse manque et bloque, poser une question ciblée. Sinon, écrire l'hypothèse et prévoir sa validation.

## 2. Critères d'acceptation

Formuler en comportements observables, pas en tâches techniques :

```gherkin
Étant donné <contexte>
Quand <action>
Alors <résultat observable>
Et <cas d'erreur ou limite>
```

Un critère = un test futur. S'il n'est pas testable, il est trop vague.

## 3. Découper en tranches verticales

- Chaque tranche traverse toutes les couches (UI → API → données) et livre seule une valeur.
- Ordonner par risque technique d'abord, puis valeur, puis dépendances.
- La première tranche doit être la plus petite qui prouve le concept de bout en bout.
- Éviter les tranches horizontales (« toute la base », « toute l'API ») qui ne livrent rien.

## 4. Prioriser

Matrice simple : impact utilisateur × confiance ÷ effort. Pour les arbitrages lourds :

| Critère | Question |
|---|---|
| Valeur | quel revenu, quelle rétention, quel coût évité ? |
| Urgence | que se passe-t-il si on attend trois mois ? |
| Risque | probabilité et coût d'échec ? |
| Effort | jours-ingénieur + coût d'exploitation |
| Réversibilité | peut-on revenir en arrière facilement ? |

Ne pas confondre urgence (pression) et importance (impact). Rendre la décision visible au décideur (voir `influence-et-alignement.md`).

## 5. Estimer

- Estimer en **fourchette** (optimiste / probable / pessimiste), jamais en point unique.
- Découper jusqu'à des unités ≤ 2 jours ; au-delà, l'incertitude domine.
- Inclure tests, revue, documentation, déploiement et aléas (20–30 %).
- Nommer les inconnues qui feraient varier l'estimation d'un facteur 2.
- Une estimation n'est pas un engagement ; un engagement inclut une marge explicite.

## 6. Pré-mortem

Avant de démarrer : « Dans trois mois, le projet a échoué. Pourquoi ? » Lister cinq causes, puis pour chacune : prévention ou détection précoce. Convertir les plus probables en tâches du plan.

## 7. Rituel de suivi

- Une source de vérité unique (board, doc) ; pas de statut parallèle.
- Statut = fait / en cours / bloqué + prochain pas + échéance.
- Un blocage remonte en moins de 24 h avec une demande explicite.
