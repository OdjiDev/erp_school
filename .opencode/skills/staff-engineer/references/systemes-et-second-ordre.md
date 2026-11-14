# Systèmes et second ordre

## 1. Penser en systèmes

- **Stocks** : ce qui s'accumule (dette, backlog, confiance, trésorerie, compétences).
- **Flux** : entrées et sorties (demandes, livraisons, attrition, revenus).
- **Boucles** : renforcement ou équilibrage (croissance virale, saturation, réputation).
- **Délais** : entre l'action et l'effet (recrutement, réputation, dette, régulation).

La contrainte réelle n'est pas toujours là où l'on regarde. Chercher le goulot, pas le symptôme.

## 2. Incentives

- **Goodhart** : quand une mesure devient un objectif, elle cesse d'être une bonne mesure.
- **Campbell** : toute mesure utilisée pour décider sera corrompue.
- **Principal-agent** : les intérêts de l'agent divergent de ceux du principal.
- **Cobra effect** : une incitation produit l'inverse de l'effet voulu.
- **Moral hazard** : le risque est porté par quelqu'un d'autre que le décideur.

Toute métrique de performance doit être accompagnée d'une métrique de garde-fou.

## 3. Local vs global

- Optimiser une équipe peut dégrader le système : files, handoffs, duplication.
- Un gain local sans mesure globale est une hypothèse, pas un résultat.
- Les coûts de coordination augmentent avec le nombre d'interfaces, pas linéairement.
- La vitesse locale se paie souvent en dette globale.

## 4. Path dependence et lock-in

- Les choix passés contraignent les choix futurs.
- Le lock-in vient des données, des contrats, des compétences, des intégrations, pas seulement de la technologie.
- Estimer le coût de sortie avant d'entrer.
- Préférer les standards ouverts quand la différenciation ne vient pas du format.

## 5. Coût de la complexité

- Chaque service, abstraction, dépendance et option a un coût de portage.
- La complexité se paie en incidents, onboarding, latence de décision et attrition.
- Supprimer est une fonction technique de premier ordre.
- Une plateforme qui n'est pas adoptée est une complexité nette négative.

## 6. Second ordre

Poser trois fois « et ensuite ? » :

1. On automatise le déploiement → et ensuite ? Moins d'erreurs, mais qui comprend le pipeline ?
2. On découpe en microservices → et ensuite ? Autonomie, mais coût de coordination et de debug.
3. On externalise le support → et ensuite ? Coût variable, mais perte de signal produit.

Chercher aussi : effets de bord, coûts cachés, incitations inversées, dépendances nouvelles, risques de réputation.

## 7. Red team et pré-mortem

- Pré-mortem : « dans 18 mois, c'est un échec ; pourquoi ? ».
- Red team : demander à quelqu'un de démonter la décision, pas de l'améliorer.
- Documenter les scénarios de rupture et les tripwires.
- Une décision qui ne peut pas être critiquée n'est pas une décision, c'est une croyance.

## 8. Archétypes fréquents

| Archétype | Symptôme | Sortie |
|---|---|---|
| Shifting the burden | on traite le symptôme, la cause s'aggrave | traiter la cause, accepter le coût initial |
| Limits to growth | la croissance sature | lever la contrainte ou changer de modèle |
| Tragedy of the commons | ressource partagée épuisée | règles, quotas, propriété |
| Success to the successful | le gagnant capte tout | réallouer, protéger les options |
| Fixes that fail | le correctif crée un nouveau problème | second ordre, délai, boucle |
