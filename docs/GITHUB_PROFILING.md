# Profilage des opérations GitHub

## Activation

Le profilage est désactivé par défaut. Il s'active avec :

```text
GITHUB_PROFILE=true
```

Avec Docker, suivre uniquement les mesures avec :

```bash
docker logs --follow 50ohm-question-review-local 2>&1 \
  | grep -E '\[(github|request)_profile\]'
```

Le profiler n'enregistre ni jeton OAuth, ni payload JSON, ni texte de question.
Il conserve le type d'opération et le chemin du fichier GitHub afin de rendre
les lectures répétées visibles.

## Appel GitHub

Chaque appel produit une ligne `github_profile` :

```text
[github_profile] request_id=19ef0e8a method=GET operation=contents.read resource=campaign.meta.json status=200 duration_ms=142.7 github_request_id=... rate_remaining=4872
```

Les opérations possibles sont :

- `contents.read` : lecture d'un fichier à un commit ou sur la branche ;
- `contents.write` : création d'un commit GitHub par écriture de fichier ;
- `commits.list` : lecture de l'historique d'un chemin pour déterminer un
  auteur ;
- `commits.oldest` : résolution initiale de la version exportée d'un fichier
  pour le diff ; cette résolution et le contenu original sont ensuite mis en
  cache ;
- `rate_limit.read` : lecture du quota GitHub ;
- `oauth.token` et `oauth.user` : authentification GitHub.

`request_id` relie les appels appartenant au même chargement de page ou à la
même action. `github_request_id` permet de retrouver une requête côté GitHub.

## Synthèse de la page

La fin de chaque requête de l'application produit une ligne
`request_profile` :

```text
[request_profile] request_id=19ef0e8a method=GET path=/edit/NF101 status=200 duration_ms=1840.3 github_calls=12 github_ms=1712.8 breakdown=commits.list:2/280.1ms,contents.read:10/1432.7ms
```

- `duration_ms` : temps total vu par l'application ;
- `github_calls` : nombre d'appels GitHub ;
- `github_ms` : somme de leur durée ;
- `breakdown` : nombre d'appels et durée cumulée par type.

La réponse HTTP contient également un en-tête `Server-Timing` avec les durées
totale et GitHub, visible dans les outils de développement du navigateur.

## Analyse attendue

Comparer en priorité :

1. le nombre de `contents.read` par affichage de question ;
2. le coût de `commits.list` et des lectures historiques utilisées pour les
   auteurs ;
3. le nombre de `contents.write` d'un `Commit` avec ou sans commentaire ;
4. la différence entre `duration_ms` et `github_ms`, qui représente le rendu et
   le traitement local.

Ces mesures permettent ensuite de décider sur des faits s'il faut mettre en
cache le manifeste et les index, mémoriser les auteurs, regrouper les écritures
ou charger certaines informations à la demande.
