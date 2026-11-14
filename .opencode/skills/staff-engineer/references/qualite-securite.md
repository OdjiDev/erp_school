# Qualité et sécurité

## 1. Stratégie de tests

Tester au niveau où le risque se situe, pas par symétrie :

| Niveau | Ce qu'on couvre | Quand |
|---|---|---|
| Unitaire | logique métier, règles, calculs, transformations | toujours |
| Intégration | frontières (DB, HTTP, files, cache), transactions | dès qu'une frontière existe |
| Contrat | compatibilité API/producteur-consommateur | APIs publiques et services partagés |
| E2E | parcours critiques, smoke tests | peu nombreux, stables |
| Non-régression | bugs corrigés | un test par bug corrigé |

Règles :
- Un test doit échouer si le comportement change ; sinon il est décoratif.
- Pas de test dépendant de l'horloge, du réseau ou de l'ordre d'exécution.
- Mocker aux frontières, pas la logique testée.
- Les tests sont du code : lisibilité et maintenance comptent.
- Couverture = indicateur, pas objectif. Une ligne couverte sans assertion ne prouve rien.

## 2. Sécurité — checklist

### Authentification et autorisation
- [ ] Authentification vérifiée sur chaque point d'entrée protégé.
- [ ] Autorisation par ressource (pas seulement par rôle global).
- [ ] Sessions/tokens : expiration, rotation, révocation, stockage sûr.
- [ ] Principe du moindre privilège pour les comptes de service et les tokens.

### Entrées et sorties
- [ ] Validation de schéma aux frontières ; rejet explicite du non conforme.
- [ ] Requêtes paramétrées (SQL/NoSQL), pas de concaténation.
- [ ] Encodage contextuel des sorties (HTML, URL, shell, JSON).
- [ ] Téléversements : type, taille, nom, stockage hors racine web.
- [ ] URL externes : liste blanche / protection SSRF.

### Données
- [ ] Secrets hors du dépôt ; variables d'environnement ou coffre.
- [ ] Données personnelles minimisées, durée de conservation définie.
- [ ] Pas de PII dans les logs, traces ou messages d'erreur.
- [ ] Chiffrement en transit ; au repos si la donnée est sensible.
- [ ] Sauvegardes testées, restauration documentée.

### Exploitation
- [ ] Limitation de débit / protection anti-abus sur les endpoints coûteux.
- [ ] Dépendances maintenues ; veille sur les vulnérabilités.
- [ ] Erreurs internes non exposées au client.
- [ ] Accès administrateur tracé et restreint.

## 3. Observabilité

- **Logs** : structurés (JSON), corrélés par requête, sans secret ni PII ; niveau cohérent.
- **Métriques** : taux d'erreur, latence (p50/p95/p99), débit, saturation ; par parcours critique.
- **Traces** : aux frontières (HTTP, DB, file) pour localiser les goulets.
- **Alertes** : sur symptôme utilisateur (SLO), pas sur chaque pic interne ; actionnable et avec runbook.
- Un nouveau parcours critique sans observabilité n'est pas livrable.

## 4. Performance

- Définir un budget avant d'optimiser : latence cible, mémoire, coût par requête.
- Mesurer en conditions réalistes (volume, concurrence), pas sur un jeu de dix lignes.
- Chercher d'abord : N+1, requêtes non indexées, appels réseau synchrones, sérialisation inutile.
- Mettre en cache seulement après avoir identifié un coût réel ; prévoir l'invalidation.
- Documenter les compromis (fraîcheur vs latence, mémoire vs CPU).

## 5. Accessibilité et UX (si interface)

- Navigation clavier, focus visible, contrastes suffisants.
- Libellés de formulaires associés, messages d'erreur explicites.
- États de chargement, vide et erreur traités explicitement.
- Pas de perte de saisie sur erreur réseau.

## 6. Definition of Done qualité

- [ ] Tests nominaux, erreurs et limites présents et pertinents.
- [ ] Lint, typage et build verts.
- [ ] Pas de secret ni de PII introduits.
- [ ] Observabilité ajoutée sur le nouveau parcours.
- [ ] Documentation/ADR à jour.
- [ ] Rollback possible et documenté.
