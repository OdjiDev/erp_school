# ADR-002 — Flotte de nœuds locaux standardisés pour 50+ sites

- **Statut** : Proposée
- **Date** : 2026-11-12
- **Décideur(s)** : Direction, responsable technique
- **Contexte technique** : 50 établissements, 2 à 5 multi-sites, Internet peu stable, Mali

## Contexte

Le groupe ou la plateforme doit servir environ 50 établissements, dont 2 à 5 possèdent plusieurs sites, soit environ 53 à 55 sites. Les opérations critiques — notes, bulletins, absences, paiements espèces — ne peuvent pas dépendre d'Internet. En même temps, il faut consolider les données, gérer les parents, superviser les sites et mettre à jour le logiciel sans intervenir manuellement sur chaque machine.

## Décision

Déployer **un nœud local standard par site** (ou par petit établissement), supervisé par une **console de flotte centralisée**, et un **cloud multi-tenant** pour la consolidation, le portail parent et les sauvegardes.

Caractéristiques du nœud :

- mini-PC standard, Ubuntu LTS, Docker, PostgreSQL ;
- onduleur et protection électrique ;
- disque chiffré, sauvegarde locale chiffrée + réplication cloud ;
- agent de synchronisation, agent de supervision, agent de mise à jour ;
- enregistrement par jeton, certificat mTLS, identifiant de site ;
- mises à jour signées, déployées par vagues, avec rollback ;
- image système identique pour tous les sites, configuration par variables.

Les petits sites peuvent utiliser une PWA avec cache local ou un nœud mutualisé, selon l'effectif et le nombre d'utilisateurs simultanés.

## Alternatives considérées

- **Cloud uniquement** — rejeté : inutilisable pendant les coupures, fréquentes.
- **Déploiements sur mesure par école** — rejeté : 50 variantes ingérables, support et mises à jour impossibles.
- **PWA offline uniquement** — rejeté pour les sites moyens et grands : conflits multi-utilisateurs, paiements et numérotation de reçus difficiles à garantir.
- **Un serveur par établissement sans supervision** — rejeté : pas de visibilité, pas de mises à jour, sauvegardes non fiables.

## Conséquences

**Positives**
- Opérations critiques hors ligne.
- Consolidation et portail parent.
- Mises à jour et supervision centralisées.
- Coût matériel maîtrisé par standardisation.

**Négatives / coûts**
- Investissement matériel : environ 500–900 USD par site, hors support.
- Logistique : livraison, installation, stock de rechange, remplacement.
- Exploitation : supervision, sauvegardes, mises à jour, support.
- Complexité de synchronisation et de migrations de schéma sur une flotte.

**Neutres**
- Un monolithe modulaire suffit ; pas de microservices ni de Kubernetes par site.

## Règles associées

- Chaque nœud a un `node_id`, un `site_id`, un certificat et un jeton révocables.
- Aucune mise à jour non signée ; rollback automatique si le health check échoue.
- La console de flotte alerte : nœud hors ligne, retard de synchro, disque, sauvegarde, version.
- Sauvegarde quotidienne chiffrée, restauration testée mensuellement.
- Stock de rechange : 5 à 10 % des sites.
- Procédure de remplacement : restaurer la sauvegarde sur un nœud neuf, réenregistrer, resynchroniser.

## Suivi

- Valider le modèle économique (groupe unique ou 50 clients).
- Confirmer les effectifs par site et le budget matériel.
- Piloter 2 à 3 écoles avant le déploiement par vagues.
- Revoir après le pilote : coût réel par site, taux de synchronisation, incidents.
