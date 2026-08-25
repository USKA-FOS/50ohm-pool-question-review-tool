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
- table des matières et navigation entre questions et chapitres ;
- affichage des textes, du LaTeX et des dessins ;
- sélection dynamique DE, FR ou IT comme référence et langue active ;
- changement direct, sans machine à états, entre `to_be_reviewed`, `approved`
  et `rejected` ;
- contrôle SHA du fichier de métadonnées lors d'un changement de statut ;
- attribution du statut au commit Git qui a réellement modifié la langue ;
- ajout append-only de commentaires dans `reviews/<question_id>.json` avec
  contrôle SHA et attribution Git ;
- importeur canonical limité au mode `--dry-run`.

## Vérifications réalisées

- les neuf combinaisons de langues sont acceptées ;
- les changements de statut sont idempotents et limités à la langue active ;
- une modification concurrente du même fichier est refusée ;
- le premier test d'approbation a produit un élément `ready`, aucun conflit,
  aucun élément invalide et `canonical_write_performed=false` ;
- aucun fichier sous le canonical `pool/` n'a été modifié par ces essais.

## Limitations intermédiaires

- l'écriture des textes de question et de réponse reste désactivée ;
- l'importeur ne possède encore aucun mode d'application canonical ;
- la progression de la table des matières provient encore de l'index créé à
  l'export et ne reflète pas immédiatement les changements de statut ;
- les médias sont encore affichés par les URL du site existant plutôt que lus
  au commit enregistré dans `media.refs.json` ;
- les commentaires peuvent être ajoutés mais pas modifiés ou supprimés depuis
  l'interface.

Cet état constitue un palier de développement, pas une version de production.
