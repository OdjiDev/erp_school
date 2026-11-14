# Revue de code

## 1. Priorités

| Niveau | Signification | Action |
|---|---|---|
| **P0** | Bug bloquant, faille, perte de données, corruption | Bloquer le merge |
| **P1** | Défaut réel à corriger avant merge | Corriger dans la PR |
| **P2** | Amélioration souhaitable, non bloquante | Ticket ou follow-up |
| **P3** | Nitpick, goût personnel | Optionnel, ne pas insister |

Format : `fichier:ligne — [P1] problème → correction proposée → pourquoi`.
Une remarque sans impact démontrable reste P3.

## 2. Ce qu'on vérifie, dans l'ordre

### Correction
- Le code fait-il ce que dit le titre de la PR, ni plus ni moins ?
- Cas limites : vide, nul, un seul élément, très grand volume, doublons.
- Erreurs : que se passe-t-il si la dépendance échoue, time out, renvoie du partial ?
- Concurrence : accès partagés, transactions, double soumission, ordre des événements.
- Ressources : fermeture des connexions/fichiers, fuites mémoire, boucles non bornées.

### Sécurité
- Entrées validées à la frontière ; sorties encodées selon le contexte (HTML, SQL, shell, URL).
- Autorisation vérifiée côté serveur, pas seulement masquée dans l'UI.
- Pas de secret, token ou donnée personnelle dans le code, les logs ou les messages d'erreur.
- Requêtes paramétrées ; pas de concaténation SQL.
- Dépendances ajoutées : maintenues, licences compatibles, surface minimale.

### Données
- Migration réversible ou plan de retour arrière explicite.
- Contraintes d'intégrité en base, pas seulement dans le code applicatif.
- Index adaptés aux requêtes ajoutées ; pas de requête N+1.
- Format persisté compatible avec les versions déjà déployées.

### API et contrats
- Compatibilité ascendante ; champs optionnels plutôt que renommages.
- Codes d'erreur stables et documentés.
- Idempotence des écritures rejouables.
- Validation du schéma aux frontières (entrée et sortie).

### Tests
- Les tests échouent-ils si le comportement change ? (sinon ils ne prouvent rien)
- Cas nominal + cas d'erreur + cas limite.
- Pas de mock de l'implémentation testée ; mocker aux frontières.
- Tests déterministes : pas de dépendance à l'horloge, au réseau ou à l'ordre d'exécution.

### Maintenabilité
- Nommage et structure cohérents avec le dépôt.
- Pas de duplication introduite sans raison ; pas d'abstraction prématurée.
- Commentaires utiles (pourquoi), pas de bruit (quoi).
- Complexité cyclomatique raisonnable ; fonctions courtes si possible.
- Logs et métriques ajoutés aux nouveaux parcours critiques.

### Performance
- Pas d'optimisation sans mesure ; mais pas de boucle O(n²) ou de requête non bornée introduite.
- Budget respecté si la zone est sensible (latence, mémoire, coût).

## 3. Comment formuler

- Commencer par le constat, pas par le jugement : « Cette requête n'est pas bornée » plutôt que « c'est mauvais ».
- Proposer une correction concrète ou une piste.
- Poser une question quand l'intention n'est pas claire, plutôt que supposer.
- Regrouper les remarques similaires ; ne pas inonder la PR.
- Reconnaître explicitement ce qui est bien fait quand c'est utile, sans flatterie.
- La revue est aussi un acte de mentorat : expliquer le pourquoi, laisser l'auteur corriger (voir `mentorat-et-multiplication.md`).

## 4. Ce qu'on ne commente pas

- Le style déjà tranché par le formateur/linter du projet.
- Les préférences personnelles sans impact (ordre des imports, nommage local).
- Les refactors hors périmètre : ouvrir un ticket, ne pas bloquer.
- Ce qu'on n'a pas lu ou compris : demander plutôt que deviner.

## 5. Checklist avant de rendre la revue

- [ ] J'ai lu la description et le contexte de la PR.
- [ ] J'ai vérifié les tests et leur pertinence.
- [ ] J'ai cherché les cas d'erreur et les cas limites.
- [ ] J'ai vérifié la sécurité et les données.
- [ ] Chaque constat a un niveau et un impact.
- [ ] Mon verdict est explicite : approuvé, approuvé avec réserves, ou bloqué.
