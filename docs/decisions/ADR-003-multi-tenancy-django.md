# ADR-003 — Multi-tenancy par ligne avec Django

- **Statut** : Acceptée
- **Date** : 2026-11-12
- **Décideur(s)** : Direction technique
- **Contexte** : 50 clients SaaS, 50 à 100 écoles, nœuds locaux, petite équipe Django

## Contexte

La plateforme sert 50 clients, dont certains possèdent deux écoles. Chaque client doit être isolé. Les sites fonctionnent hors ligne sur un nœud local, puis synchronisent vers un cloud central. Les migrations doivent être simples à déployer sur une flotte de 50 à 100 nœuds.

## Décision

Utiliser **un schéma PostgreSQL partagé avec isolation par ligne** :

- `organization_id` sur toutes les tables appartenant à un client ;
- `school_id` sur les tables scolaires ;
- `site_id` sur les tables opérationnelles ;
- managers « fail closed » : sans contexte tenant, aucune donnée n'est retournée ;
- contraintes d'unicité scopées par client/école ;
- tests d'isolation systématiques ;
- RLS PostgreSQL ajouté en défense en profondeur avant la montée en charge.

## Alternatives considérées

- **`django-tenants`, un schéma par client** — rejeté : migrations sur 50 à 100 schémas, synchronisation complexe, reporting inter-clients difficile.
- **Une base par client** — rejeté : exploitation et sauvegardes ingérables pour une petite équipe.
- **Un déploiement par client** — rejeté : 50 variantes, mises à jour impossibles.
- **Isolation applicative seule sans tests** — rejeté : une requête sans filtre suffit à provoquer une fuite.

## Conséquences

**Positives**
- Un seul schéma, migrations et synchronisation simples.
- Reporting consolidé possible.
- Coût d'exploitation maîtrisé.
- Compatible avec les nœuds locaux.

**Négatives / coûts**
- Risque de requête non filtrée : doit être couvert par les managers, les tests et RLS.
- Index composites nécessaires (`organization_id`, `school_id`, clés métier).
- Admin Django à configurer avec des filtres explicites.

**Neutres**
- Les identifiants restent UUID ; aucun changement pour les clients.

## Règles

- Aucune requête métier ne lit un modèle client sans contexte ; le routage et
  le contrôle d'accès peuvent utiliser `all_objects` avec des filtres explicites.
- `TenantManager.get_queryset()` retourne `none()` si le contexte est absent.
- `all_objects` réservé au routage/contrôle d'accès, aux migrations, à l'admin
  plateforme, aux tâches système et aux lectures internes bornées par une clé
  parente.
- Toute contrainte d'unicité inclut `organization_id` ou `school_id`.
- Un test d'isolation par modèle exposé.
- Les logs incluent `organization_id`, `school_id`, `site_id`.

## Suivi

- Managers fail-closed, accès `all_objects` explicite et tests d'isolation ORM implémentés.
- Activer RLS avant le pilote multi-clients.
- Revoir après les 10 premiers clients.
