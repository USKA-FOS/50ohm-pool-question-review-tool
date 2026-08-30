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
| `MEDIA-001` | `ready` | Références graphiques de question | Autoriser une campagne à déclarer séparément les champs `picture_*` modifiables dans `editable_picture_fields`. Présenter ces références dans le même onglet conditionnel que les métadonnées, avec des libellés métier et les aperçus résolus par `media.refs.json`, sans exposer la structure JSON au réviseur. | Seuls les champs déclarés sont modifiables. Le choix est limité aux médias déjà déclarés et valides dans `media.refs.json`. Le même `Commit` enregistre atomiquement contenu, référence graphique, métadonnées éventuelles, commentaire et statut. L'importeur contrôle l'autorisation, la divergence canonical et l'existence du média avant toute écriture. La création ou l'ajout d'un nouveau média reste hors de cette entrée. |

## Décisions fonctionnelles validées

### `UI-001` - hauteur des champs

- ajuster la hauteur de la question et des quatre réponses éditables au
  chargement et après un rafraîchissement ;
- utiliser une ligne comme hauteur minimale de tous les champs texte
  éditables : question, réponses, commentaire, justifications et motivation ;
- agrandir automatiquement un champ pendant la saisie lorsque son contenu
  déborde, sans le réduire automatiquement pendant la même session ;
- préserver le redimensionnement vertical manuel ;
- recalculer complètement la hauteur au chargement suivant ;
- utiliser une ligne comme hauteur minimale du commentaire et l'agrandir
  automatiquement selon son contenu.

### `UI-002` - identifiant canonique

- afficher le numéro visible et le `question_id` sur la même ligne ;
- afficher le `question_id` en police monospace atténuée ;
- fournir une petite commande de copie avec une confirmation discrète ;
- autoriser un retour à la ligne uniquement lorsque la largeur disponible ne
  permet pas de conserver les deux identifiants côte à côte.

### `META-001` - contrat initial des métadonnées

`editable_metadata_fields` utilise des chemins JSON Pointer. Le premier registre
de champs pris en charge est :

```json
"editable_metadata_fields": [
  "/class_level",
  "/HB/rationale",
  "/HB/motivation"
]
```

Les widgets associés sont :

- `/class_level` : sélection parmi `0 - NOVICE`, `1 - CEPT` et
  `9 - UNDEFINED` ;
- `/HB/rationale` : liste structurée de textes pouvant être ajoutés ou
  supprimés ;
- `/HB/motivation` : texte facultatif.

Un chemin inconnu rend la campagne invalide. L'interface ne fournit pas
d'éditeur JSON générique. Les onglets `Content` et `Metadata` apparaissent
uniquement lorsqu'au moins un champ de détail est modifiable ; `Content` est
l'onglet initial. Une question approuvée doit être rouverte avant toute
modification. Un champ facultatif vidé est retiré proprement du JSON.

Le même `Commit` enregistre atomiquement le contenu, les métadonnées, le
commentaire éventuel et le passage de la langue active à `approved`. `Reopen`
ne restaure ni le texte ni les métadonnées et modifie seulement le statut.

Les métadonnées étant communes aux langues, une modification autorisée est
importable une seule fois au niveau de la question dès qu'au moins une langue
modifiable de cette question est `approved`. Elle conserve les contrôles de
divergence par rapport à la révision canonical exportée et ne remplace jamais
`question.meta.json` en bloc.

### `UI-003` - affichage des justifications

- afficher les valeurs actuelles de `HB.rationale` sous les commentaires sous
  forme de liste en lecture seule ;
- garder cet affichage distinct de l'éditeur éventuel de
  `/HB/rationale` dans l'onglet `Metadata` ;
- ne pas afficher de bloc lorsque la campagne n'autorise aucun champ de détail
  ou lorsque `HB.rationale` est absent ou vide ;
- ne pas attribuer ces valeurs à l'auteur d'un commentaire de campagne.

### `MEDIA-001` - limite de portée

Cette entrée concerne uniquement le remplacement d'une référence `picture_*`
par un média déjà disponible dans le manifeste de campagne. La création d'un
nouvel objet média, l'extension de `media.refs.json` et les changements
coordonnés avec `50ohm-contents-ch` restent définis séparément dans
`QUESTION_REVIEW_MEDIA_CHANGE_WORKFLOW.fr.md` à la racine du workspace.

`editable_picture_fields` contient uniquement les noms canoniques suivants :

```json
"editable_picture_fields": [
  "picture_question_url",
  "picture_answer_a_url",
  "picture_answer_b_url",
  "picture_answer_c_url",
  "picture_answer_d_url"
]
```

La liste peut n'en autoriser qu'un sous-ensemble. Un nom inconnu rend la
campagne invalide. Chaque champ appartient au fichier
`question.<langue-active>.json` et suit donc l'approbation et l'import de cette
langue, contrairement aux métadonnées communes de `question.meta.json`.

Le widget permet de conserver la référence, de sélectionner un autre média du
manifeste ou de choisir l'absence de média (`null`). Il affiche l'aperçu courant
et l'aperçu sélectionné. La validation refuse une réponse textuelle `null` si
sa référence graphique correspondante devient elle aussi `null`. Les champs
`picture_*` non déclarés et les fichiers des autres langues restent inchangés.
