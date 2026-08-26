# Transfert du depot de campagnes vers USKA-FOS

## Objet

Ce document decrit le transfert futur de
`isqsoft/50ohm-question-review-campaigns` vers
`USKA-FOS/50ohm-question-review-campaigns`.

Le transfert change le proprietaire GitHub du depot, mais pas son historique,
ses commits ni ses branches. Les campagnes existantes ne doivent pas etre
reexportees. En particulier, les branches suivantes restent valides :

- `campaign/multilingual-empfaenger-sinus-signals-example` ;
- `campaign/antennas`.

## Preconditions

L'operateur doit disposer :

- du droit d'administration sur le depot source ;
- du droit de creer ou de recevoir un depot dans `USKA-FOS` ;
- d'un acces administrateur a la configuration OAuth et aux droits du depot
  cible ;
- d'un acces au fichier `.env` prive du serveur de revision.

Le depot cible `USKA-FOS/50ohm-question-review-campaigns` ne doit pas deja
exister, ni etre un fork occupant ce nom.

## 1. Transferer le depot

Dans GitHub, ouvrir le depot source puis :

1. ouvrir `Settings` ;
2. ouvrir `General` ;
3. atteindre `Danger Zone` ;
4. choisir `Transfer ownership` ;
5. definir `USKA-FOS` comme nouveau proprietaire ;
6. conserver le nom `50ohm-question-review-campaigns` ;
7. confirmer le transfert.

Documentation GitHub :
<https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository>

GitHub redirige normalement les anciennes URL Git et Web vers le nouveau
depot. Ne pas recreer ensuite un depot sous l'ancien chemin
`isqsoft/50ohm-question-review-campaigns`, car cela supprimerait les
redirections.

## 2. Verifier le contenu transfere

Verifier dans `USKA-FOS/50ohm-question-review-campaigns` :

- la branche principale et la documentation ;
- toutes les branches `campaign/*` ;
- l'historique complet de chaque branche ;
- les fichiers `campaign.meta.json`, `media.refs.json`, `pool/` et `derived/` ;
- l'absence de changement non attendu dans les SHA des branches.

Exemples de controles :

```bash
git ls-remote \
  git@github.com:USKA-FOS/50ohm-question-review-campaigns.git \
  'refs/heads/*'
```

## 3. Retablir les droits des reviseurs

Dans `Settings -> Collaborators and teams`, verifier chaque reviseur. Pour
utiliser `Commit` et `Reopen`, il doit disposer du role GitHub `Write`, soit :

- directement comme collaborateur ;
- par l'intermediaire d'une equipe `USKA-FOS`.

Verifier aussi les rulesets et protections applicables dans `USKA-FOS`. Ils ne
doivent pas interdire les commits directs de l'outil sur les branches de
campagne.

## 4. Autoriser l'application OAuth

Le callback reste unique et inchange :

```dotenv
GITHUB_CALLBACK_URL=https://qrt.jp2s.ch/auth/callback
```

Si `USKA-FOS` restreint les applications OAuth, un proprietaire de
l'organisation doit approuver l'application de revision pour l'acces au depot
prive. Les reviseurs doivent ensuite se deconnecter puis se reconnecter a
l'outil. Si un SSO est impose, ils doivent aussi autoriser leur jeton pour
`USKA-FOS`.

Documentation GitHub :
<https://docs.github.com/en/organizations/managing-oauth-access-to-your-organizations-data/about-oauth-app-access-restrictions>

## 5. Adapter le serveur

Dans le `.env` prive du deploiement, remplacer uniquement le proprietaire du
depot :

```dotenv
GITHUB_OWNER=USKA-FOS
GITHUB_REPO=50ohm-question-review-campaigns
```

Conserver le callback, les secrets et la table de campagnes. Exemple :

```dotenv
CAMPAIGNS_JSON={"receiver-signals":{"branch":"campaign/multilingual-empfaenger-sinus-signals-example","label":"Receiver and sinusoidal signals"},"antennas":{"branch":"campaign/antennas","label":"Antennas"}}
DEFAULT_CAMPAIGN=receiver-signals
```

La modification de ces variables ne necessite pas de reconstruire l'image.
Recreer seulement le conteneur afin de relire `.env` :

```bash
docker compose up -d --no-deps --force-recreate question-review
```

## 6. Verifier le deploiement

Verifier la configuration chargee sans afficher les secrets :

```bash
docker exec 50ohm-question-review \
  python -c 'import main; print(main.OWNER, main.REPO, main.CAMPAIGNS)'
```

Verifier ensuite :

```bash
curl -fsS https://qrt.jp2s.ch/healthz
```

Puis tester dans le navigateur :

- `https://qrt.jp2s.ch/campaign/receiver-signals/` ;
- `https://qrt.jp2s.ch/campaign/antennas/` ;
- l'authentification GitHub ;
- l'affichage de la table des matieres, du LaTeX et des dessins ;
- l'ouverture d'une question ;
- `Commit` et `Reopen` sur une question de test ;
- l'auteur du statut et des commentaires.

En cas de reponse `403`, verifier d'abord le role du reviseur, l'approbation
OAuth de l'organisation et l'autorisation SSO eventuelle.

## 7. Mettre a jour les clones

Les redirections GitHub sont temporaires du point de vue operationnel et ne
doivent pas remplacer une configuration explicite. Dans chaque clone du depot
de campagnes :

```bash
git remote set-url origin \
  git@github.com:USKA-FOS/50ohm-question-review-campaigns.git

git remote -v
git fetch origin
```

Les outils d'export et d'import utilisent un checkout local du depot de
campagnes. Ils ne necessitent aucune transformation des fichiers exportes.

## 8. Mettre a jour la documentation

Apres le transfert valide, remplacer les references operationnelles a
`isqsoft/50ohm-question-review-campaigns` dans :

- le README et les documents actifs de l'outil de revision ;
- `50ohm-question-pool/docs/QUESTION_REVIEW_CAMPAIGNS.md` ;
- la documentation principale du depot de campagnes.

Ne pas modifier les anciennes entrees de `HISTORY.md` : elles decrivent la
situation historique au moment des travaux.

## Criteres de fin

Le transfert est termine seulement lorsque :

- les branches et leurs SHA ont ete verifies ;
- les reviseurs disposent du role `Write` ;
- l'application OAuth est autorisee dans `USKA-FOS` ;
- le serveur charge `GITHUB_OWNER=USKA-FOS` ;
- les deux campagnes s'affichent et acceptent une ecriture controlee ;
- les clones et la documentation operationnelle utilisent la nouvelle URL.

