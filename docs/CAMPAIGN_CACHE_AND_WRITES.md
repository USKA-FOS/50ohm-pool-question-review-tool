# Cache de campagne et écritures atomiques

## Objectif

GitHub reste la source de vérité et la mémoire permanente des révisions. Il
n'est plus utilisé comme un système de fichiers distant pour chaque affichage.

## Initialisation

Au premier accès authentifié à une campagne, l'application :

1. résout le SHA courant de la branche de campagne ;
2. résout le commit ayant introduit `campaign.meta.json` ;
3. télécharge une archive JSON de la branche courante ;
4. télécharge une archive JSON du commit d'export ;
5. calcule localement les SHA Git des blobs et conserve les deux snapshots en
   mémoire.

Le snapshot d'export est immuable et alimente les différences
original/commité. Le snapshot courant alimente le manifeste, la navigation,
les questions, les métadonnées et les commentaires.

## Navigation

Pendant la durée de validité du snapshot, l'affichage et la navigation ne font
aucun appel GitHub. Au maximum une fois toutes les
`CAMPAIGN_REFRESH_SECONDS`, l'application contrôle le SHA de tête. Si celui-ci
a changé, elle recharge uniquement l'archive courante. La valeur par défaut est
30 secondes.

Chaque campagne possède son propre snapshot, indexé par l'identifiant présent
dans l'URL. Une actualisation ou une écriture dans une campagne ne remplace pas
le snapshot d'une autre campagne.

Le cache est éphémère. Une nouvelle instance ou un cache invalidé reconstruit
toujours son état depuis GitHub.

## Commit et Reopen

L'application prépare localement tous les fichiers modifiés, puis utilise la
mutation GraphQL `createCommitOnBranch` :

- texte, commentaire éventuel et statut sont écrits dans un seul commit ;
- `expectedHeadOid` doit correspondre au SHA du snapshot ;
- un changement concurrent refuse toute l'opération ;
- après réussite seulement, les fichiers et le SHA du cache sont actualisés.

Il n'existe donc aucun état où seul le texte ou seul le commentaire aurait été
commité. En cas de conflit, le cache est invalidé et le rechargement suivant
récupère la branche courante.

## Auteurs

Les auteurs déjà résolus depuis Git sont mis en cache par SHA de blob. Après
une écriture réussie, l'identité GitHub de la session est associée directement
au nouveau statut et au nouveau commentaire. Le cache d'auteur reste dérivé et
jetable ; les fichiers de campagne ne reçoivent aucun champ d'auteur.

## Invariants

- aucune donnée locale n'est considérée persistée avant la réussite GitHub ;
- les snapshots et caches dérivés sont isolés par campagne ;
- aucune écriture ne remplace silencieusement un commit concurrent ;
- les originaux d'export ne sont jamais modifiés ;
- le cache peut être supprimé sans perte de travail ;
- GitHub reste l'unique source de vérité durable.
