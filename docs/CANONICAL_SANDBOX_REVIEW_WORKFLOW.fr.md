# Flux de révision entre canonical et sandbox

## Objectif

Le canonical `50ohm-question-pool` reste l'unique source de vérité. La sandbox
sert uniquement d'espace de travail temporaire pour une campagne de révision.
Elle ne doit pas devenir un second pool de référence.

Le modèle conserve la séparation existante :

```text
question.<langue>.json   contenu durable de la question
question.meta.json       statut de révision courant et durable
sandbox                  travail et historique temporaire de la campagne
```

Les informations de révision ne doivent pas être ajoutées aux fichiers de
contenu. Cette séparation permet à un diff de contenu de montrer immédiatement
si une question ou une réponse a changé.

## 1. Création d'une campagne

Un outil lit directement les objets du canonical à une révision Git immuable,
identifiée par un hash ou un tag. Il exporte dans une branche WIP de la sandbox
uniquement les langues et questions concernées.

La copie dans la sandbox est un instantané de travail. Elle n'est ni une source
indépendante ni une copie à maintenir durablement en synchronisation.

Le manifeste minimal de campagne contient seulement :

- le dépôt canonical d'origine ;
- le hash ou tag canonical de départ ;
- la langue révisée ;
- l'identifiant de la campagne ;
- le périmètre des `question_id` concernés.

Chaque donnée a une fonction opérationnelle : retrouver la source exacte,
interpréter les fichiers, isoler la campagne et empêcher l'import d'une
question hors périmètre.

## 2. Révision dans la sandbox

La branche WIP contient les propositions en cours. Le réviseur peut demander
une correction, rejeter une proposition ou l'approuver. Les commentaires et
les décisions intermédiaires restent dans la sandbox.

L'historique de campagne doit rester petit et séparable du contenu. Pour chaque
question, seules les informations suivantes sont nécessaires :

- `question_id` ;
- décision : `approved`, `changes_requested` ou `rejected` ;
- commentaire, uniquement lorsqu'il apporte une information utile.

La langue et la révision source sont déjà définies au niveau de la campagne.
Git fournit l'auteur, la date et l'ordre des modifications ; il est inutile de
les recopier dans chaque objet. Cet historique temporaire peut être supprimé
après intégration et clôture de la campagne.

## 3. Retour dans le canonical

Un importeur contrôlé récupère uniquement les résultats approuvés. Pour chaque
question, il doit :

1. vérifier que le `question_id` appartient à la campagne ;
2. comparer le contenu canonical courant avec celui de la révision de départ ;
3. refuser l'import si ce contenu a changé entre-temps ;
4. remplacer `question.<langue>.json` seulement si le contenu approuvé diffère ;
5. mettre à jour le statut existant dans `question.meta.json` ;
6. exécuter les validations et reconstructions normales du question pool.

Une approbation sans changement de texte peut uniquement faire évoluer le
statut. Les commentaires, décisions intermédiaires et données propres à la
sandbox ne sont pas importés dans le canonical.

## Passage d'information

```text
canonical à un commit ou tag précis
        |
        | export contrôlé
        v
sandbox / branche WIP / historique temporaire
        |
        | résultats approved
        v
import contrôlé avec détection des changements concurrents
        |
        v
canonical : contenu final + statut courant
```

Le lecteur de campagne doit donc prendre les sources directement dans le
canonical, mais les figer à une révision précise. Lire continuellement la tête
courante pendant une révision rendrait la référence mobile et les comparaisons
ambiguës.

## Données volontairement exclues du canonical

- nom du réviseur ;
- date de chaque action ;
- commentaires de travail ;
- copie de l'historique de campagne ;
- champs historiques `review` et `HB.comments` du prototype.

Ces données n'améliorent pas le texte final ni son statut courant. Lorsque leur
consultation temporaire est utile, Git et la sandbox les conservent pendant la
campagne sans polluer le modèle canonical.
