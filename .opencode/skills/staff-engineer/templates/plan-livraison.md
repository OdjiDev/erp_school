# Plan de livraison — <changement>

| | |
|---|---|
| **Version / commit** | |
| **Responsable** | |
| **Fenêtre prévue** | |
| **Niveau de risque** | Faible / Moyen / Élevé |
| **Ticket / RFC** | |

## 1. Résumé

Ce qui change pour l'utilisateur et pour le système. Risque principal en une phrase.

## 2. Pré-requis

- [ ] Migration de données prête et testée
- [ ] Configuration / secrets en place
- [ ] Droits et accès vérifiés
- [ ] Dépendances déployées
- [ ] Sauvegarde récente
- [ ] Équipe d'astreinte informée

## 3. Étapes

| # | Action | Vérification | Responsable | Durée |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |

## 4. Observabilité

- Dashboard : 
- Métriques à surveiller : p95/p99, taux d'erreur, débit, saturation
- Logs / traces : 
- Alertes actives : 

## 5. Critères de succès

- Métrique : <seuil> atteint dans <délai>.
- Aucune augmentation du taux d'erreur au-delà de <seuil>.

## 6. Critères d'abandon et rollback

- Abandon si : <condition chiffrée>.
- Procédure de rollback : <commandes/étapes exactes>.
- Temps estimé : 
- Impact du rollback (données écrites, messages traités) : 

## 7. Communication

| Moment | Audience | Canal | Message |
|---|---|---|---|
| Avant | | | |
| Pendant | | | |
| Après | | | |

## 8. Post-livraison

- [ ] Vérification à J+1 et J+7
- [ ] Retrait du feature flag planifié
- [ ] Documentation / ADR mises à jour
- [ ] Dette consignée
