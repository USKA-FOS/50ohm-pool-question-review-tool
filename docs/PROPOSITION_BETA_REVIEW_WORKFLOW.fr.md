# Proposition de révision itérative par campagnes (historique)

Ce document expose la proposition initiale et ses phases de déploiement. Le
mode dry-run exclusif décrit ci-dessous a depuis été complété par un import réel
contrôlé. Le manuel opérateur courant se trouve dans
`50ohm-question-pool/docs/QUESTION_REVIEW_CAMPAIGNS.md`.

## Statut

Ce document décrit l'architecture proposée. Il doit être validé avant toute
adaptation du prototype. Aucun import réel dans le canonical n'est prévu durant
la première phase.

## Objectif

Publier rapidement une première version bêta du site, puis améliorer les
questions par campagnes successives. Le nombre de campagnes, leur périmètre et
leur motif restent des décisions humaines et ne sont pas imposés par le
programme.

Le canonical de `50ohm-question-pool` reste l'unique source de vérité pour le
contenu publié. Le dépôt de révision conserve durablement la mémoire du travail
humain, mais ne remplace pas le canonical.

## Cycle général

1. Un état versionné du canonical produit une version bêta du site.
2. Un filtre ou une liste explicite sélectionne les questions d'une campagne.
3. L'exporteur copie leur contenu et leurs métadonnées dans une branche du
   dépôt de révision.
4. Les réviseurs modifient ensemble cette branche avec l'outil de révision.
5. L'importeur compare les résultats avec la source canonical de la campagne.
6. En première phase, l'importeur fonctionne obligatoirement avec `--dry-run`.
7. Après validation du processus, les résultats choisis pourront être
   réintégrés dans le canonical, puis les sites reconstruits.
8. Une nouvelle campagne peut ensuite être créée selon un autre critère.

Le nom d'une campagne décrit son objet. Il est indépendant du tag ou du numéro
de la version bêta publiée, par exemple :

```text
campaign/fr-terminology-antennas
campaign/it-chapter-ne-review
campaign/multilingual-ai-quality-findings
```

## Composants et responsabilités

### `50ohm-question-pool`

Ce dépôt contient :

- le canonical DE, FR et IT ;
- les outils d'export et d'import de campagne ;
- les outils de sélection ou filtres ;
- les validations de structure et de cohérence ;
- la reconstruction des catalogues utilisés par le générateur.

L'exporteur et l'importeur de campagne n'existent pas encore. Ils doivent être
créés dans ce dépôt, car lui seul connaît le modèle canonical et ses règles.

### Dépôt de révision permanent

Ce dépôt Git contient le travail des campagnes et leur historique. Ce n'est
pas un espace jetable : il garde la mémoire des sélections, modifications,
commentaires et validations effectués pendant les révisions.

Le dépôt de développement retenu est
`isqsoft/50ohm-question-review-campaigns`. Il est hébergé sur GitHub dès les
essais : l'application le lit et l'écrit directement par l'API GitHub. Il n'est
donc pas nécessaire de maintenir un checkout local permanent. Un clone
temporaire peut être utilisé par les outils en ligne de commande, mais GitHub
reste le stockage persistant. Le dépôt pourra ensuite être transféré vers son
emplacement de production sans modifier le contrat ni perdre son historique.

Tous les réviseurs d'une campagne travaillent sur une branche commune. Il n'y
a pas de branche par réviseur.

### `50ohm-pool-question-review-tool`

L'outil de révision :

- ouvre une campagne du dépôt de révision ;
- charge les questions exportées ;
- permet de choisir dynamiquement la langue de référence ;
- permet de choisir dynamiquement la langue à réviser ;
- affiche la comparaison entre ces deux langues ;
- permet de modifier la langue révisée et ses informations de révision ;
- enregistre les changements dans la branche commune avec contrôle du SHA Git ;
- affiche, à partir de l'historique Git, l'auteur des commentaires et du dernier
  changement de statut ;
- affiche les images et le LaTeX déjà présents dans les données.

Le prototype tourne actuellement sur le serveur de l'utilisateur. Son
déploiement dans Google Cloud n'est pas une condition de cette adaptation.
L'architecture ne dépend pas d'un disque serveur persistant et reste compatible
avec un déploiement serverless ultérieur dans Google Cloud.

### `50ohm-contents-ch`

Ce dépôt public fournit les ressources graphiques référencées par les
questions :

- `canonical/drawings/` pour les dessins, principalement au format SVG ;
- `canonical/photos/` pour les photographies et autres images matricielles.

Ces ressources restent sous la responsabilité de `50ohm-contents-ch`. Elles
ne sont pas copiées dans le dépôt de révision. Une campagne enregistre le
nom de la branche source et le commit exact de `50ohm-contents-ch` utilisé. Un
petit manifeste résout les identifiants numériques `picture_*_url` vers les
fichiers canoniques concernés.

La branche actuelle est une branche de travail séparée. Son nom n'est donc pas
codé en dur dans le contrat : il est fourni à l'exporteur et conservé comme
information de provenance. Lors du prochain merge, une nouvelle campagne
pourra utiliser le nouveau nom de branche sans modifier le format d'export.

### Filtres de campagne

Les filtres appartiennent à `50ohm-question-pool`, mais ils ne constituent pas
une liste figée imposée par le programme. Une campagne peut être construite à
partir de :

- chapitres ;
- numéros ou `question_id` explicites ;
- statuts de révision ;
- modifications depuis une révision Git ;
- résultats d'un audit automatique ou IA ;
- faiblesses linguistiques ;
- incohérences entre langues ;
- toute autre sélection produisant le contrat attendu.

Quelle que soit la méthode, le résultat du filtre est matérialisé par une liste
explicite de `question_id`. Cela rend la campagne reproductible.

## Structure du dépôt de révision

Le format normatif proposé est détaillé dans
[`CAMPAIGN_CONTRACT_V1.fr.md`](CAMPAIGN_CONTRACT_V1.fr.md).

La branche principale contient uniquement la documentation, les schémas et les
éventuels outils propres au dépôt de révision. Chaque campagne utilise une
branche dédiée :

```text
main
campaign/fr-terminology-antennas
campaign/it-chapter-ne-review
```

Le premier commit d'une branche de campagne contient l'export initial :

```text
campaign.meta.json
media.refs.json
pool/
  questions/
    <question_id>/
      question.meta.json
      question.de.json
      question.fr.json
      question.it.json
```

Le répertoire `pool/questions/` est un sous-ensemble du canonical. Il conserve
la séparation actuelle entre contenu et métadonnées. Les fichiers de contenu
gardent le même schéma que dans le canonical.

La branche entière constitue le WIP de la campagne :

- le premier commit est l'état exporté depuis le canonical ;
- le `HEAD` courant contient l'état révisé ;
- Git fournit le diff, l'auteur et l'historique ;
- les commentaires temporaires restent dans le dépôt de révision ;
- aucune modification n'est écrite directement dans le canonical.

Cette organisation évite un second répertoire WIP et les branches par
réviseur. Deux personnes travaillant sur des questions différentes modifient
des fichiers différents. Une modification simultanée de la même question est
détectée par le SHA Git et doit être résolue explicitement.

`media.refs.json` ne contient pas les fichiers graphiques. Il conserve
seulement, pour les médias effectivement utilisés par les questions de la
campagne, leur type, leur identifiant d'objet, leurs variantes linguistiques et
leurs chemins dans `50ohm-contents-ch`.

## Contrat d'export

L'exporteur reçoit :

- les pools DE, FR et IT, complets ou partiels ;
- une référence canonical immuable, sous forme de commit ou de tag ;
- une liste explicite de `question_id` et les raisons informatives de leur
  sélection ;
- une branche ou une référence Git source de `50ohm-contents-ch`, résolue en
  commit immuable par l'exporteur ;
- un nom de campagne descriptif ;
- le dépôt et la branche de révision cibles.

Les trois langues sont exportées afin que la langue de référence et la langue à
réviser puissent être choisies dans l'interface. Une campagne peut néanmoins
déclarer un sous-ensemble de langues modifiables.

Exemple minimal de `campaign.meta.json` :

```json
{
  "schema_version": 1,
  "campaign_id": "fr-terminology-antennas",
  "canonical_repository": "50ohm-question-pool",
  "canonical_revision": "<commit-ou-tag>",
  "media_repository": "USKA-FOS/50ohm-contents-ch",
  "media_branch": "<branche-au-moment-de-l-export>",
  "media_revision": "<commit>",
  "media_manifest": "media.refs.json",
  "languages": ["de", "fr", "it"],
  "editable_languages": ["fr"],
  "question_ids": ["q_...", "q_..."],
  "selection_reasons": {
    "q_...": ["chapter:EG", "terminology"]
  }
}
```

La référence canonical sert à identifier exactement la base de comparaison et
à détecter une modification concurrente lors de l'import. Les métadonnées sont
nécessaires pour conserver les identifiants stables et les statuts de révision.

`media_branch` indique d'où provenait l'export, mais n'identifie pas à lui seul
les fichiers utilisés. `media_revision` est la référence normative : elle doit
être un commit, et non une branche mobile. Une campagne reste ainsi
reproductible si la branche est renommée, fusionnée ou supprimée, et lorsque
des dessins ou des photos sont modifiés ultérieurement dans
`50ohm-contents-ch`.

## Langues dans l'interface

La langue de référence et la langue à réviser ne sont pas codées en dur.

Exemples :

- référence DE, révision FR ;
- référence DE, révision IT ;
- référence FR, révision IT ;
- référence IT, révision DE.

L'interface ne doit rendre modifiable que la langue à réviser. Changer la
langue de référence ne modifie aucune donnée.

## Images et LaTeX

Le prototype sait déjà afficher des images et du LaTeX. L'adaptation ne part
donc pas du principe que leur rendu est incorrect. Elle doit seulement vérifier
que le chargement depuis la structure canonical conserve :

- les références d'images ;
- les réponses `null` représentées par une image ;
- les macros LaTeX utilisées dans les questions et les réponses ;
- le rendu lors d'un changement dynamique de langue.

### Résolution des médias

Les champs `picture_question_url` et `picture_answer_a_url` à
`picture_answer_d_url` contiennent actuellement un identifiant numérique, pas
un chemin Git. Le générateur interprète ces champs comme des dessins et les
charge depuis `contents/drawings/`. Lors de l'export, le résolveur recherche
donc l'identifiant dans les `object.meta.json` de `canonical/drawings/`.

Il inscrit le résultat exact dans `media.refs.json`. L'interface n'a donc pas à
parcourir tout le dépôt GitHub à chaque affichage.

Pour une langue donnée, le manifeste désigne la variante canonique adaptée,
par exemple un SVG localisé pour un dessin ou une image matricielle pour une
photo. L'absence d'une référence, d'un objet ou d'une variante requise est une
erreur explicite de préparation de campagne ; elle ne doit pas produire une
image vide silencieuse.

### Lecture depuis le dépôt public

L'outil lit les fichiers directement depuis le dépôt public GitHub, à la
révision enregistrée dans la campagne. Il ne construit pas les URL à partir de
`media_branch`. Une URL immuable prend par exemple la forme :

```text
https://raw.githubusercontent.com/USKA-FOS/50ohm-contents-ch/<commit>/canonical/drawings/<object_id>/<fichier.svg>
```

Cette lecture ne nécessite ni copie des médias dans la campagne ni jeton GitHub
pour les fichiers publics. Le serveur peut ajouter un cache technique, mais la
clé de ce cache doit inclure le commit et le chemin complet. Le cache n'est pas
une nouvelle source de vérité.

Les identifiants numériques ne suffisent pas à distinguer un dessin d'une
photo : certaines valeurs existent dans les deux collections. La version 1 ne
convertit donc jamais implicitement une référence de question en photo. Une
future référence de photo devra porter un type explicite avant son export.

## Statuts et historique

Les statuts de révision restent dans `question.meta.json`, comme actuellement.
Ils donnent une information sur l'état du contenu, sans imposer une machine à
états rigide.

Un petit historique de campagne séparé peut conserver les opérations utiles
pendant les travaux. Git fournit déjà l'auteur, la date et le diff ; il n'est
pas nécessaire de recopier ces informations dans chaque objet canonical.

Lors de l'import définitif, seuls les contenus et statuts expressément retenus
sont transférés. L'historique détaillé de campagne reste dans le dépôt de
révision et peut être archivé indépendamment du canonical.

## Catalogues compatibles avec le générateur

Si une prévisualisation avec le générateur est nécessaire, les catalogues DE,
FR et IT sont reconstruits depuis la branche de campagne dans un répertoire
dérivé :

```text
derived/
  question_pool_ch-de.json
  question_pool_ch-fr.json
  question_pool_ch-it.json
```

Ces fichiers ont le format consommé par le générateur. Ils ne constituent pas
la représentation éditable et ne doivent pas être modifiés manuellement.

## Contrat d'import

L'importeur appartient à `50ohm-question-pool`. Pour chaque question retenue,
il doit :

1. vérifier que le `question_id` appartient à la campagne ;
2. retrouver l'état canonical indiqué par `canonical_revision` ;
3. comparer cet état avec le canonical actuel ;
4. signaler les conflits question par question ;
5. présenter les contenus et statuts qui seraient importés ;
6. laisser toutes les autres questions et langues intactes ;
7. exécuter les validations du question pool.

Pendant la première phase, `--dry-run` est obligatoire. Il ne modifie aucun
fichier canonical, aucun statut et aucun commit. Le passage à un import réel
fera l'objet d'une validation explicite ultérieure.

## Publication des versions bêta

Une version bêta est créée après une intégration validée dans le canonical :

1. commiter l'état canonical ;
2. identifier cet état par le tag de publication retenu ;
3. reconstruire les pools DE, FR et IT ;
4. reconstruire et publier les trois sites.

Le nom d'une campagne ne dépend pas de ce tag. Plusieurs campagnes peuvent
alimenter une même version bêta, et une campagne peut être intégrée dans une
version ultérieure à celle envisagée lors de sa création.

## Mise en place par étapes

### Étape 1 : contrat et dépôt de révision

- valider `campaign.meta.json` et la structure objet ;
- créer localement le dépôt de révision permanent ;
- définir et tester `media.refs.json` à partir de `canonical/drawings/` et
  `canonical/photos/` à une révision Git figée ;
- rendre la branche source de `50ohm-contents-ch` configurable et vérifier sa
  résolution vers un commit avant l'export ;
- créer un exporteur de campagne dans `50ohm-question-pool` ;
- créer un importeur limité au `--dry-run` ;
- vérifier les diffs et conflits sur des données de test.

### Étape 2 : adaptation de l'outil

1. charger et afficher les questions d'une branche de campagne ;
2. choisir dynamiquement la langue de référence et la langue à réviser ;
3. enregistrer la version modifiée directement dans les fichiers canonical
   copiés sur cette branche ;
4. gérer les commentaires, statuts et conflits SHA utiles.

### Étape 3 : prototype opérationnel

- faire fonctionner le prototype sur le serveur actuel ;
- exécuter une campagne complète sans import réel ;
- contrôler l'export, la révision, l'historique Git et le rapport `--dry-run` ;
- adapter le processus à partir des problèmes observés ;
- déplacer ou publier ensuite le dépôt de révision dans l'environnement de
  production ;
- n'autoriser l'import réel qu'après validation explicite.

## Points restant à valider

Le contrat version 1 propose désormais le schéma des manifestes, les trois
statuts de campagne, les commentaires séparés, l'approbation avant import, le
contrôle SHA et le repli explicite vers le dessin allemand. Restent à décider
après l'essai local :

- le mécanisme de clôture ou d'archivage d'une campagne ;
- l'emplacement final du dépôt de révision en production.
