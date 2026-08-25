# Analyse de la situation originale

## Portée

Cette analyse décrit le fonctionnement du prototype original avec le dépôt
sandbox `50-ohm-review-sandbox-GLiddFioGw`. Elle distingue les données réellement
utilisées par l'application des fichiers historiques présents dans le dépôt.

Aucune conclusion de ce document ne constitue une demande de suppression. Les
fichiers historiques doivent être conservés tant que leur rôle dans la
reproductibilité du processus initial n'a pas été formellement décidé.

## Représentation des questions

Le sandbox contient deux formes de données qui peuvent sembler redondantes :

```text
questions_de.json
questions/<question_id>.json
```

Elles ne jouent cependant pas le même rôle.

### Catalogue allemand agrégé

Le fichier `questions_de.json`, placé à la racine du sandbox, contient toutes
les questions allemandes dans un seul tableau JSON. Il correspond probablement
à une source intermédiaire utilisée lors de la préparation initiale du dépôt.

Le code de l'application ne référence jamais ce fichier. Il n'est utilisé ni
pour construire la table des matières, ni pour afficher une question, ni pour
enregistrer une révision.

Le blob Git de `questions_de.json` est strictement identique dans les trois
références consultées par le prototype :

```text
german_orig:questions_de.json     76f5c13ff9cbec53db303d5d645f4743ad8f559b
FR_orig_DeepL:questions_de.json   76f5c13ff9cbec53db303d5d645f4743ad8f559b
WIP:questions_de.json             76f5c13ff9cbec53db303d5d645f4743ad8f559b
```

Il s'agit donc d'un artefact historique stable, et non d'une version de travail
mise à jour par l'application.

### Fichiers individuels par question

Le répertoire `questions/` contient un fichier JSON par question, par exemple :

```text
questions/AF101.json
questions/AF102.json
questions/NB703.json
```

Le même chemin représente des contenus différents selon la référence Git :

```text
german_orig:questions/<question_id>.json
    version allemande originale

FR_orig_DeepL:questions/<question_id>.json
    traduction française initiale produite par DeepL

WIP:questions/<question_id>.json
    traduction française en cours de révision
```

Par exemple, les blobs de `questions/AF101.json` sont différents :

```text
german_orig    2338a7a3c89d9b77628a0ee53d9b7c26a63d32e9
FR_orig_DeepL  c2068b44ac3923cc7c6b7f4ac54aca5cb9411ef8
WIP            612b6bf937b2612182a28e3ba70eeef2baa696bc
```

L'application charge exclusivement ces fichiers individuels. Dans `main.py`,
la fonction `fetch()` lit `questions/<question_id>.json`, puis l'éditeur appelle
cette fonction avec les références `german_orig`, `FR_orig_DeepL` et `WIP`.

Lors d'une sauvegarde, l'application modifie uniquement :

```text
WIP:questions/<question_id>.json
```

### Table des matières

La table des matières ne provient ni de `questions_de.json` ni directement du
répertoire `questions/`. Elle est construite à partir de :

```text
fragenkatalog3b.json
```

Ce fichier est embarqué dans le dépôt de l'application, et non lu depuis le
sandbox. Le prototype précise que son contenu sert uniquement à structurer la
navigation et ne représente pas la version courante des questions.

### Conclusion sur la duplication

Pour le fonctionnement actuel du prototype :

- `questions/<question_id>.json` est nécessaire ;
- `questions_de.json` n'est pas utilisé à l'exécution ;
- `fragenkatalog3b.json` reste nécessaire pour la navigation.

La suppression de `questions_de.json` ne devrait pas affecter directement
l'application. Il est néanmoins préférable de le conserver tant que la
provenance et la reproductibilité du processus original n'ont pas été
documentées autrement. Une suppression dans `WIP` créerait également un
changement parasite dans la comparaison avec `FR_orig_DeepL`.

## Graphiques et figures

### Références dans les questions

Les fichiers de questions ne contiennent pas directement les graphiques. Ils
stockent seulement des identifiants numériques dans les champs suivants :

```json
{
  "picture_question": 500,
  "picture_a": 408,
  "picture_b": 409,
  "picture_c": 410,
  "picture_d": 411
}
```

Une valeur `null` indique qu'aucune image n'est associée à l'élément concerné.

### Images effectivement affichées

Le template `templates/editor.html` construit des URLs externes à partir des
identifiants :

```text
https://50ohm.uska.online/images_fr/<image_id>.svg
https://50ohm.uska.online/images_de/<image_id>.svg
```

Les images affichées par le navigateur proviennent donc du site
`50ohm.uska.online`. Elles ne sont ni chargées par l'API GitHub du prototype, ni
servies par le conteneur de l'application.

### Branche `images_fr`

Le sandbox possède une branche Git séparée :

```text
images_fr
```

Cette branche contient 92 sources graphiques sous la forme :

```text
images/500.tex
images/501.tex
images/590.tex
```

Ces fichiers sont des sources LaTeX, notamment basées sur TikZ et Circuitikz.
La branche ne contient pas les SVG attendus par le navigateur. Les 193 autres
fichiers de cette branche sont les fichiers JSON de questions hérités de son
point de départ, pour un total de 285 fichiers suivis.

Aucune collection `images_de` et aucun ensemble équivalent de SVG allemands
n'ont été trouvés dans les branches ou tags du sandbox.

### Conclusion sur les images

La situation originale comporte deux niveaux distincts :

```text
sandbox / branche images_fr / images/*.tex
    sources graphiques françaises

50ohm.uska.online/images_fr et images_de
    SVG effectivement consommés par l'application
```

Le lien de génération ou de publication entre les sources `.tex` et les SVG du
site externe n'est pas implémenté dans le dépôt de l'application. Le prototype
dépend donc d'un service externe pour afficher toutes les figures françaises et
allemandes.

## Risques constatés

- `questions_de.json` est une duplication historique sans consommateur dans le
  code actuel.
- La table des matières repose sur une copie locale distincte des données
  révisées.
- Les sources graphiques et les images réellement publiées sont séparées.
- Les SVG dépendent d'un domaine externe codé en dur dans le template.
- Les figures allemandes ne sont pas conservées dans le sandbox examiné.
- Le processus transformant les sources `.tex` en SVG publiés n'est pas présent
  dans ce dépôt.

Ces points doivent être pris en compte lors de la définition du futur workflow
canonical/sandbox, mais ils ne doivent pas être corrigés isolément avant que le
nouveau contrat de données soit validé.
