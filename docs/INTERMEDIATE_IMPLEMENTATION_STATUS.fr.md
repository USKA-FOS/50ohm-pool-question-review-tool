# État intermédiaire de l'implémentation

## Portée vérifiée

Le serveur local lit actuellement la branche
`campaign/multilingual-empfaenger-sinus-signals-example` du dépôt privé
`isqsoft/50ohm-question-review-campaigns`. Cette campagne contient 42 questions
des chapitres `Empfänger` et `Sinusförmige Signale` dans les trois langues DE,
FR et IT.

Le canonical `50ohm-question-pool/pool/` reste l'unique source publiée. La
branche de campagne conserve le travail intermédiaire et son historique Git.

## Langues

- `languages` énumère les langues présentes et utilisables comme référence ;
- `editable_languages` contient une à trois langues modifiables par la
  campagne ;
- la langue de référence et la langue active de révision peuvent être
  identiques, notamment DE→DE, FR→FR et IT→IT ;
- `review_language` est uniquement la sélection active dans l'interface ;
- il n'existe aucune langue de sortie unique pour une campagne.

Les modifications enregistrées dans une langue restent dans la campagne
lorsque l'utilisateur sélectionne une autre langue. Le dry-run examine tous les
couples `(question_id, langue)` de toutes les langues déclarées dans
`editable_languages`. Tous les couples au statut `approved` peuvent donc être
proposés ensemble à la réintégration canonical.

## Fonctions actives

- authentification GitHub OAuth ;
- lecture directe d'une branche de campagne privée ;
- snapshot mémoire courant et original chargé par archives GitHub, avec
  contrôle périodique du SHA de branche ;
- table des matières et navigation entre questions et chapitres ;
- mémorisation locale des deux langues sélectionnées et de la dernière question
  ouverte, avec validation des préférences contre la campagne active ;
- affichage des textes, du LaTeX et des dessins ;
- affichage des différences entre la première version Git du texte localisé
  dans la campagne et le texte actuellement commité, sans exiger un accès
  OAuth au dépôt canonical séparé ;
- sélection dynamique DE, FR ou IT comme référence et langue active ;
- action unique `Commit` pour enregistrer le texte, ajouter le commentaire
  éventuel et passer la langue active à `approved` ;
- action `Reopen` pour remettre une langue approuvée à `to_be_reviewed` ;
- contrôles SHA du contenu, des métadonnées et des commentaires avant écriture ;
- commit GraphQL atomique du texte, du commentaire éventuel et du statut ;
- attribution du statut au commit Git qui a réellement modifié la langue ;
- ajout append-only de commentaires dans `reviews/<question_id>.json` avec
  contrôle SHA et attribution Git ;
- indicateur bloquant `Please wait. Working with GitHub...` pendant les
  formulaires et la navigation interne, masqué explicitement à la fin du
  chargement ou lors de la restauration d'une page ;
- mise en page large en trois colonnes égales, avec la langue source marquée
  `(Reference)`, le statut et l'historique en colonne latérale, et le
  commentaire à côté de l'éditeur ;
- importeur canonical avec contrôle `--dry-run` puis application explicite des
  seuls couples `ready`.

## Vérifications réalisées

- les neuf combinaisons de langues sont acceptées ;
- `Commit` ne modifie que le contenu et le statut de la langue active ;
- `Reopen` ne modifie que le statut de la langue active ;
- les valeurs `null`, les médias et les autres champs canonical sont préservés ;
- une modification concurrente du même fichier est refusée ;
- le premier test d'approbation a produit un élément `ready`, aucun conflit,
  aucun élément invalide et `canonical_write_performed=false` ;
- les tests automatisés couvrent l'import réel, les conflits partiels et une
  panne de préparation sans écriture canonique.

## Limitations intermédiaires

- l'import réel reste une commande opérateur séparée et ne déclenche ni build,
  ni commit, ni publication automatiquement ;
- les médias sont encore affichés par les URL du site existant plutôt que lus
  au commit enregistré dans `media.refs.json` ;
- les commentaires peuvent être ajoutés avec `Commit`, mais pas modifiés ou
  supprimés depuis l'interface.

Cet état constitue un palier de développement, pas une version de production.
