# Revue de PR — GET /orders/{id}

**Verdict** : Bloquée
**Périmètre relu** : `src/api/orders.ts`, `src/services/order-service.ts`, tests
**Hypothèses** : l'authentification est assurée par le middleware global ; je n'ai pas vérifié la configuration de production.

## Constats

### P0 — bloquants

- `src/api/orders.ts:42` — [P0] aucun contrôle d'autorisation : tout utilisateur authentifié peut lire la commande d'un autre en changeant l'ID → vérifier `order.userId === request.user.id` (ou une règle d'admin explicite) avant de renvoyer → fuite de données personnelles et de commandes.

### P1 — à corriger avant merge

- `src/services/order-service.ts:28` — [P1] N+1 : une requête par ligne de commande dans une boucle → charger les lignes en une requête `WHERE orderId IN (...)` ou une jointure → latence proportionnelle au nombre d'articles.
- `test/orders.test.ts` — [P1] aucun test pour le cas 404 (commande inexistante) ni pour l'accès non autorisé → ajouter les deux cas → la faille P0 serait passée inaperçue.

### P2 — améliorations

- `src/api/orders.ts:55` — [P2] le message d'erreur renvoie l'ID interne de la base → renvoyer un identifiant public ou un message générique → évite de divulguer la structure interne.

### P3 — nitpicks (optionnels)

- `src/api/orders.ts:12` — [P3] `res` pourrait être nommé `response` pour la cohérence avec le reste du fichier.

## Points vérifiés

- [x] Le changement correspond au titre et à la description
- [ ] Cas nominaux, erreurs et limites couverts
- [ ] Sécurité : entrées, autorisation, secrets
- [x] Données : pas de migration
- [ ] Tests pertinents et déterministes
- [x] Observabilité : log ajouté sur l'échec
- [x] Performance : pas de régression évidente hors N+1
- [x] Rollback possible : simple revert

## Questions ouvertes

- Un administrateur doit-il pouvoir lire toutes les commandes ? Si oui, la règle doit être explicite et testée.

## Points positifs

- Découpage clair entre route et service.
- Gestion du 500 correcte, sans fuite de stack trace.
