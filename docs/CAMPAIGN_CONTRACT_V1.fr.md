# Contrat de campagne de révision, version 1

## Portée

Ce document définit le format minimal d'une campagne de révision de questions.
Il précède l'implémentation de l'exporteur, de l'importeur et l'adaptation de
l'interface.

Le canonical reste `50ohm-question-pool/pool/`. Une campagne en contient un
sous-ensemble de travail, mais ne devient jamais une autre source canonique.

Pendant le développement, le dépôt permanent de campagnes est
`isqsoft/50ohm-question-review-campaigns`. L'outil de révision y accède
directement par l'API GitHub. Aucun checkout local permanent de ce dépôt n'est
requis.

## Structure d'une branche de campagne

```text
campaign.meta.json
media.refs.json
derived/
  navigation.index.json
  question_pool_ch-<langue>.json
pool/
  questions/
    <question_id>/
      question.meta.json
      question.de.json
      question.fr.json
      question.it.json
reviews/
  <question_id>.json       # absent tant qu'aucun commentaire n'existe
```

Le répertoire `derived/` contient obligatoirement les index de navigation
générés depuis le canonical lors de l'export. Chaque langue déclarée dans
`languages` doit avoir exactement un catalogue
`question_pool_ch-<langue>.json`. Sa structure contient toujours trois niveaux
non vides avant les questions : `chapter.sections`, `section.sections`, puis
`subsection.questions`. Cette structure reste obligatoire même pour une
campagne monolingue ou une simple liste explicite de questions ; l'exporteur
crée alors les niveaux synthétiques nécessaires.

`navigation.index.json` relie chaque `number` affiché au `question_id`
canonique. Ses codes doivent couvrir exactement les questions des catalogues
localisés, sans doublon, et ses `question_id` doivent couvrir exactement
`campaign.meta.json.question_ids`.

Ces fichiers ne sont jamais modifiés par les réviseurs et ne sont pas importés
dans le canonical. Toute campagne, quel que soit son filtre de sélection, doit
les régénérer.

Les quatre fichiers placés sous `pool/questions/<question_id>/` gardent
exactement le schéma du canonical. Aucun champ propre à l'outil de révision
n'est ajouté aux fichiers `question.<langue>.json`.

Les valeurs textuelles `null` et `""` restent distinctes. Un `null` n'est
valide que si le champ d'image correspondant est renseigné. Une chaîne vide est
également une valeur canonique existante, notamment pour certaines structures
sans réponses textuelles ; l'exporteur la conserve sans la convertir.

Les questions sont inscrites dans `campaign.meta.json` dans l'ordre de leur
`internal_code`. Cet ordre sert également à la navigation dans l'interface.

## `campaign.meta.json`

Exemple complet :

```json
{
  "schema_version": 1,
  "campaign_id": "fr-terminology-antennas",
  "campaign_branch": "campaign/fr-terminology-antennas",
  "canonical_source": {
    "repository": "USKA-FOS/50ohm-question-pool",
    "source_ref": "Revision_2.4",
    "revision": "<commit>",
    "pool_path": "pool"
  },
  "media_source": {
    "repository": "USKA-FOS/50ohm-contents-ch",
    "source_ref": "<branche-ou-tag>",
    "revision": "<commit>",
    "manifest": "media.refs.json"
  },
  "languages": ["de", "fr", "it"],
  "editable_languages": ["fr"],
  "question_ids": [
    "q_111111111111",
    "q_222222222222"
  ],
  "selection_reasons": {
    "q_111111111111": ["chapter:EG", "terminology"],
    "q_222222222222": ["quality-audit"]
  }
}
```

### Champs obligatoires

- `schema_version` : entier, valeur `1` pour ce contrat ;
- `campaign_id` : identifiant descriptif stable, indépendant des versions du
  site ;
- `campaign_branch` : branche Git commune sur laquelle travaillent les
  réviseurs ;
- `canonical_source.repository` : dépôt ayant fourni les questions ;
- `canonical_source.revision` : commit Git immuable réellement exporté ;
- `canonical_source.pool_path` : valeur `pool` pour le modèle actuel ;
- `media_source.repository` : dépôt public fournissant les médias ;
- `media_source.revision` : commit Git immuable des médias ;
- `media_source.manifest` : chemin de `media.refs.json` ;
- `languages` : langues copiées dans la campagne ;
- `editable_languages` : langues que l'interface peut modifier ;
- `question_ids` : périmètre exhaustif autorisé de la campagne ;
- `selection_reasons` : raisons informatives de la sélection, indexées par
  `question_id`.

`source_ref` conserve le nom de la branche ou du tag fourni à l'exporteur. Il
est informatif. Seul le commit `revision` est normatif.

Une campagne n'a pas de langue de sortie unique. `editable_languages` contient
une à trois langues et définit l'ensemble des langues que la campagne autorise
à modifier. Dans l'interface, `review_language` désigne seulement la langue
active à un instant donné. Changer cette sélection ne retire pas les
modifications ou approbations déjà enregistrées dans les autres langues.
Une campagne peut ne contenir qu'une seule langue dans `languages`; cette
langue sert alors à la fois de référence et de langue à réviser.

L'export échoue si une langue modifiable n'est pas dans `languages`, si une
question est répétée, absente du canonical, ou si les références Git ne peuvent
pas être résolues en commits.

## Initialisation des statuts

Le canonical stocke déjà les statuts dans :

```json
{
  "review": {
    "de": "approved",
    "fr": "to_be_reviewed",
    "it": "to_be_reviewed"
  }
}
```

L'export copie toute la métadonnée de la question, puis met uniquement le
statut des `editable_languages` à `to_be_reviewed` dans la copie de campagne.
Les autres langues et métadonnées restent inchangées.

L'interface de campagne utilise seulement deux états actifs :

- `to_be_reviewed` : travail ouvert ou correction encore demandée ;
- `approved` : représentation prête à être proposée à l'import ;

Une question ouverte est terminée par une seule action `Commit`, qui enregistre
le texte, le commentaire éventuel et l'approbation. Une question approuvée peut
être remise au travail avec `Reopen`. Il n'existe ni bouton de statut séparé,
ni bouton d'ajout de commentaire, ni action `Reject`. Pour écarter une
proposition, le réviseur conserve ou restaure le texte d'origine puis le
commite. La valeur historique `rejected` reste tolérée par l'importeur, mais la
nouvelle interface ne la produit pas.

Les autres valeurs canoniques restent valides dans les langues non modifiables,
mais l'interface ne les invente pas comme étapes supplémentaires. Ces statuts
informent le processus ; ils ne bloquent jamais les autres questions de la
campagne.

## Commentaires de travail

Un commentaire n'est enregistré que lorsqu'il apporte une information utile.
Il est placé hors du sous-ensemble canonical :

```json
{
  "schema_version": 1,
  "question_id": "q_111111111111",
  "comments": {
    "fr": [
      "Vérifier la terminologie de l'antenne avec le glossaire."
    ]
  }
}
```

Le fichier est absent lorsqu'aucun commentaire n'existe. Il ne contient ni nom
de réviseur ni date : Git fournit déjà l'auteur, la date, le diff et l'ordre des
opérations. Le répertoire `reviews/` n'est jamais importé dans le canonical.
L'importeur du question pool recopie toutefois les commentaires, par question
et par langue, dans ses rapports JSON et Markdown. Cette copie constitue une
trace d'audit liée au commit de campagne, pas une donnée canonique.

L'interface affiche néanmoins l'auteur de chaque commentaire. Elle le déduit du
commit Git qui a introduit l'entrée correspondante dans
`reviews/<question_id>.json`. Le nom affiché vient de l'identité GitHub du
commit, pas d'un champ recopié dans le JSON.

## `media.refs.json`

Les champs `picture_question_url` et `picture_answer_a_url` à
`picture_answer_d_url` désignent actuellement des dessins. Le générateur les
charge depuis `contents/drawings/<id>.svg`.

Il ne faut pas déterminer le type d'un média en recherchant seulement son
identifiant numérique : des identifiants identiques existent dans les dessins
et les photos. L'exporteur résout chaque référence de question comme un dessin
et enregistre explicitement l'objet choisi.

Exemple :

```json
{
  "schema_version": 1,
  "repository": "USKA-FOS/50ohm-contents-ch",
  "revision": "<commit>",
  "items": {
    "546": {
      "kind": "drawing",
      "object_id": "dr_aaaaaaaaaaaa",
      "variants": {
        "de": {
          "path": "canonical/drawings/dr_aaaaaaaaaaaa/546.de.svg",
          "source_language": "de",
          "media_type": "image/svg+xml"
        },
        "fr": {
          "path": "canonical/drawings/dr_aaaaaaaaaaaa/546.de.svg",
          "source_language": "de",
          "media_type": "image/svg+xml"
        },
        "it": {
          "path": "canonical/drawings/dr_aaaaaaaaaaaa/546.de.svg",
          "source_language": "de",
          "media_type": "image/svg+xml"
        }
      }
    }
  }
}
```

Pour chaque langue, l'exporteur sélectionne d'abord la variante de cette langue.
Si elle n'existe pas, il inscrit explicitement la variante allemande comme
repli avec `source_language: "de"`. L'interface utilise uniquement le chemin
résolu dans le manifeste et ne refait pas cette décision.

L'export échoue si l'identifiant n'a aucun dessin canonique, si le fichier
annoncé est absent ou si aucune variante allemande n'est disponible. Le schéma
autorise `kind: "photo"` pour une évolution future, mais aucune référence de
question actuelle ne doit être convertie implicitement en photo.

## Enregistrement et conflits Git

L'outil écrit directement dans la branche commune indiquée par
`campaign_branch`. Chaque sauvegarde fournit le SHA Git du fichier lu. Si ce
SHA n'est plus courant, GitHub refuse l'écriture et l'interface demande de
recharger la question. Aucun écrasement automatique n'est autorisé.

Une sauvegarde peut modifier :

- `question.<langue>.json` pour une langue modifiable ;
- `review.<langue>` dans `question.meta.json` ;
- le fichier facultatif `reviews/<question_id>.json`.

Les identifiants, références externes, niveaux de classe, autres langues et
autres statuts ne sont pas modifiables dans l'interface.

À côté du statut, l'interface affiche le réviseur qui l'a défini. Elle parcourt
l'historique Git de `question.meta.json` et retient le dernier commit ayant
effectivement changé `review.<langue>`. Le dernier auteur du fichier ne suffit
pas, car un autre champ de métadonnée peut avoir été modifié plus récemment.

Si l'auteur ne peut pas être résolu, l'interface affiche un auteur inconnu sans
inventer de nom et sans empêcher la révision. La lecture de ces informations ne
modifie aucun fichier de campagne.

Les outils en ligne de commande d'export et d'import peuvent utiliser un clone
ou un worktree temporaire sous un répertoire `work/` non suivi. Ils doivent
terminer leur opération GitHub avant de considérer l'export comme réussi. Ce
répertoire temporaire n'est ni une sauvegarde ni une source de vérité.

## Règle d'import

L'import est évalué séparément pour chaque couple `(question_id, langue)`.
L'importeur parcourt toutes les langues de `editable_languages`, indépendamment
de la dernière langue active dans l'interface. Une même campagne peut donc
proposer simultanément des modifications allemandes, françaises et italiennes.
Seul un statut de campagne `approved` rend ce couple importable. Un statut
`to_be_reviewed` ou `rejected` produit un élément ignoré dans le rapport, sans
bloquer les autres résultats.

Pour un résultat approuvé, l'importeur :

1. charge le contenu de base à `canonical_source.revision` ;
2. charge le canonical courant ;
3. compare le fichier de la langue visée et `review.<langue>` ;
4. signale un conflit si l'un de ces éléments a changé dans le canonical ;
5. valide le contenu de campagne ;
6. propose le remplacement du seul fichier linguistique et la mise à jour du
   seul statut concerné.

Les autres champs de `question.meta.json` ne sont jamais remplacés en bloc.
Une approbation sans modification de texte peut donc proposer uniquement le
passage du statut à `approved`.

## Rapport `--dry-run`

Le rapport JSON est normatif. Un Markdown lisible est généré à partir du même
rapport sans contenir d'information supplémentaire.

```json
{
  "schema_version": 1,
  "dry_run": true,
  "canonical_write_performed": false,
  "campaign_id": "fr-terminology-antennas",
  "campaign_revision": "<commit>",
  "canonical_base_revision": "<commit>",
  "canonical_current_revision": "<commit>",
  "summary": {
    "ready": 1,
    "skipped_not_approved": 1,
    "conflict": 0,
    "invalid": 0
  },
  "items": [
    {
      "question_id": "q_111111111111",
      "internal_code": "EG101",
      "language": "fr",
      "status": "approved",
      "outcome": "ready",
      "content_changed": true,
      "status_changed": true,
      "changed_fields": ["question", "answer_b"],
      "messages": []
    }
  ]
}
```

Les valeurs de `outcome` sont limitées à :

- `ready` : import possible, avec ou sans modification textuelle ;
- `skipped_not_approved` : statut différent de `approved` ;
- `conflict` : la base canonical visée a changé ;
- `invalid` : contrat ou contenu non valide.

Le rapport contient toutes les questions et langues modifiables, y compris les
éléments ignorés. Le mode `--dry-run` ne modifie aucun fichier du canonical et
ne crée aucun commit.

## Application contrôlée

L'import réel est une commande distincte et exige l'option explicite `--apply`.
Elle recommence toute l'analyse du dry-run contre les commits et arbres de
travail actuels. Elle ne se fie donc jamais à un ancien rapport.

Seuls les couples classés `ready` sont appliqués. Pour chacun, l'importeur
remplace au besoin le seul fichier `question.<langue>.json` concerné et met
uniquement `review.<langue>` à `approved`. Les éléments
`skipped_not_approved`, `conflict` et `invalid` restent inchangés et sont
conservés dans le rapport d'application.

Tous les contenus sont préparés avant la première écriture. Chaque fichier est
remplacé atomiquement. Une erreur de préparation ne modifie rien ; une erreur
de remplacement déclenche la restauration des fichiers déjà remplacés. La
commande ne crée aucun commit Git, ne pousse rien et ne reconstruit aucun build.

## Hors contrat version 1

La version 1 ne définit pas :

- une branche par réviseur ;
- une machine à états de premier et second contrôle ;
- une base de données ;
- des réservations de questions ;
- l'édition des chapitres, dessins ou photos ;
- la publication automatique d'une version bêta.

Ces fonctions ne seront ajoutées que si un besoin observé les justifie.
