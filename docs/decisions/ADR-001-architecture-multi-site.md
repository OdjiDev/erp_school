# ADR-001 — Architecture multi-site LAN-first avec synchronisation cloud

- **Statut** : Proposée
- **Date** : 2026-11-12
- **Décideur(s)** : Direction du groupe, responsable technique
- **Contexte technique** : Mali, groupe d'établissements privés, plusieurs écoles et sites, Internet peu stable, paiements multiples

## Contexte

Le groupe gère plusieurs établissements et sites. Les opérations critiques sont la saisie des notes, la production des bulletins, le suivi des absences et les paiements. Une architecture uniquement cloud rendrait ces opérations dépendantes d'une connexion instable. Une architecture uniquement locale empêcherait la consolidation du groupe, le portail parent et les sauvegardes centralisées.
   
Le schéma est multi-tenant dès le départ : `group_id` → `school_id` → `site_id`. Les petits sites peuvent utiliser une PWA avec cache local ou un serveur mutualisé.

## Alternatives considérées

- **Cloud uniquement** — rejeté : les notes et les paiements deviennent inutilisables pendant les coupures, fréquentes.
- **Local uniquement, sans cloud** — rejeté : pas de consolidation groupe, pas de portail parent, sauvegardes et mises à jour difficiles.
- **PWA offline-first uniquement** — rejeté : conflits multi-utilisateurs, paiements et numérotation de reçus difficiles à garantir, perte de données navigateur.
- **Synchronisation bidirectionnelle complète** — rejeté en v1 : complexité et risques de conflits. On limite les écritures critiques à des événements append-only.

## Conséquences

**Positives**
- Les opérations critiques fonctionnent sans Internet.
- Consolidation et portail parent possibles.
- Données locales sauvegardables et cloud répliqué.
- Architecture réversible : un site peut rester local, le cloud peut évoluer.

**Négatives / coûts**
- Coût matériel par site : mini-PC, onduleur, routeur, sauvegarde.
- Support et supervision de plusieurs serveurs.
- Complexité de synchronisation à tester sérieusement.
- Besoin d'une procédure de secours en cas de panne matérielle.

**Neutres**
- Une petite équipe peut maintenir un monolithe modulaire ; pas besoin de microservices.

## Règles associées

- Écritures critiques append-only : notes (version + correction), paiements (annulation/remboursement, jamais de modification).
- Clé d'idempotence sur chaque envoi ; déduplication côté cloud.
- Numéros de reçus alloués localement par site, sans trou.
- Horodatage par séquence serveur, jamais par l'horloge du poste.
- Conflits : cloud prioritaire sur le référentiel, site prioritaire sur l'opérationnel, revue manuelle sinon.
- Sauvegarde chiffrée quotidienne, restauration testée mensuellement.
- Onduleur et arrêt propre obligatoires.

## Suivi

- Valider le nombre de sites et le budget matériel.
- Confirmer les opérateurs mobile money et les contrats API.
- Revoir la décision après le pilote sur un site, avant généralisation.
