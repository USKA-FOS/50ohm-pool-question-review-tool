# Petites améliorations à regrouper

## But

Cette liste conserve les améliorations ergonomiques trop petites pour justifier
à elles seules un cycle complet de modification, test, déploiement et contrôle.
Elle ne remplace pas le suivi des bugs.

Lors de chaque correction de bug du review tool :

1. relire les éléments `ready` avant de modifier le code ;
2. intégrer les éléments proches de la zone corrigée, à faible risque et
   couverts par le même cycle de tests ;
3. laisser les autres en `ready` avec une justification courte ;
4. passer les éléments intégrés à `done` en indiquant le commit ;
5. signaler dans le compte rendu quels éléments ont été intégrés ou différés.

Une amélioration ne doit jamais élargir artificiellement une correction urgente
ni retarder un correctif indépendant.

## États

- `ready` : suffisamment défini pour être intégré dans un prochain lot adapté ;
- `deferred` : volontairement reporté avec une raison ;
- `done` : implémenté, testé et rattaché à un commit.

## Liste

| ID | État | Zone | Comportement attendu | Validation |
|---|---|---|---|---|
| `UI-001` | `ready` | Éditeur de texte | Au chargement ou au rafraîchissement d'une question, les champs multilignes éditables ajustent automatiquement leur hauteur au contenu affiché. Ils restent redimensionnables verticalement par l'utilisateur. | Pour chaque question et réponse textuelle, tout le contenu initial est visible sans défilement vertical interne inutile; les tailles minimales actuelles et le redimensionnement manuel restent fonctionnels. |
| `UI-002` | `ready` | En-tête de question | Afficher discrètement le `question_id` canonique sur la même ligne que le numéro lisible, sans introduire de rôle utilisateur ni de ligne supplémentaire. L'identifiant utilise une police monospace atténuée et peut être copié. | Le numéro et le `question_id` restent lisibles côte à côte sur les écrans pris en charge, sans augmenter inutilement la hauteur de l'en-tête; la copie restitue exactement l'identifiant canonique. |
| `META-001` | `ready` | Métadonnées de question | Autoriser une campagne à déclarer des chemins modifiables de `question.meta.json` dans `editable_metadata_fields`. Lorsque cette liste existe, afficher les onglets conditionnels `Content` et `Metadata`; sinon ne pas afficher d'onglets. L'édition est structurée et utilise le même mécanisme Git que le contenu, pas un éditeur JSON brut. | Seuls les champs autorisés sont éditables et importables. Un même `Commit` enregistre atomiquement le texte, les métadonnées, le commentaire éventuel et le statut. Les valeurs exportées et courantes sont comparées, les contrôles SHA et de tête de branche restent actifs, et une divergence canonique du champ produit un conflit sans écrasement. Les détails d'interface propres à chaque type de métadonnée seront définis lors de l'implémentation. |
| `UI-003` | `ready` | Contexte de révision | Lorsque la campagne déclare des métadonnées éditables, afficher les valeurs actuelles de `HB.rationale` sous l'historique des commentaires. Ne pas afficher ce bloc dans les campagnes sans `editable_metadata_fields`. | Le bloc utilise les métadonnées courantes de la question, reste distinct des commentaires de campagne et n'occupe aucune place lorsque l'édition des métadonnées n'est pas activée ou qu'aucune justification n'existe. |
