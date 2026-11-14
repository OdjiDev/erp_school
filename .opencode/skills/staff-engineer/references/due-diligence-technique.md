# Due diligence technique

## 1. Quand l'utiliser

Acquisition, investissement, partenariat, choix de fournisseur critique, migration majeure, audit avant scale. Adapter la profondeur au montant, à l'irréversibilité et au risque.

## 2. Dimensions

| Dimension | Questions | Preuves |
|---|---|---|
| Architecture | composants, couplage, SPOF, scalabilité | schémas, code, entretiens |
| Sécurité | vulnérabilités, secrets, accès, supply chain | audit, scans, incidents |
| Données | qualité, PII, rétention, souveraineté | schémas, contrats, politiques |
| Conformité | régimes applicables, audits, contrôles | certifications, rapports |
| Équipe | compétences, bus factor, rétention | organigramme, entretiens |
| Coût | infra, licences, run, migration | factures, contrats |
| Lock-in | fournisseurs, formats, contrats | architecture, clauses |
| Delivery | tests, CI/CD, incidents, vélocité | métriques, journaux |

## 3. Preuves

- Lire le code critique, pas seulement les slides.
- Vérifier les métriques réelles : latence, erreurs, disponibilité, coûts.
- Interroger les incidents passés et les post-mortems.
- Vérifier les licences et la provenance des dépendances.
- Tester la restauration des sauvegardes, pas seulement leur existence.
- Parler aux personnes qui partent et à celles qui restent.

## 4. Red flags

- Aucun test automatisé sur le cœur métier.
- Documentation absente ou obsolète.
- Une seule personne comprend un composant critique.
- Dette de sécurité non traitée, secrets dans le code.
- Dépendance forte à un fournisseur sans clause de sortie.
- Shadow IT, environnements non reproductibles.
- Incidents récurrents sans actions de fond.
- Métriques de vanité, pas de métriques opérationnelles.

## 5. Sortie

- Registre de risques : description, probabilité, impact, preuve, coût de remédiation.
- Scénarios : intégration, migration, statu quo, arrêt.
- Conditions à la transaction : actions préalables, garanties, escrow, plan de rétention.
- Recommandation claire : go, go avec conditions, no-go.
- Synthèse exécutive d'une page + annexes techniques.

## 6. Processus

- Périmètre et questions écrits avant de commencer.
- Confidentialité, clean room, accès limité.
- Séparer les faits des opinions ; citer les sources.
- Ne pas conclure au-delà des preuves ; marquer les inconnues.
- Revue contradictoire avant remise.

## 7. Intégration

- Plan de migration technique et organisationnel.
- Compatibilité des cultures et des pratiques d'ingénierie.
- Propriétaires, jalons, métriques, critères d'abandon.
- Coût de la dette et du double run.
- Communication aux équipes dès que possible.
