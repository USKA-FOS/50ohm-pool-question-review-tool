Démarche recommandée

Il faut distinguer le serveur de l’application du dépôt Git de révision. L’application peut tourner localement, mais le prototype utilise l’API GitHub pour lire et écrire les questions. Pour tester le processus réel sans développer un backend local
jetable, le dépôt de révision doit donc être accessible sur GitHub.

### 1. Stabiliser le contrat

1. Valider et commiter la proposition actuelle.
2. Définir précisément campaign.meta.json.
3. Définir media.refs.json.
4. Définir les statuts minimaux et le format des commentaires.
5. Définir le rapport produit par l’importeur --dry-run.

Aucun code applicatif avant validation de ces contrats.

### 2. Créer le dépôt de révision

1. Créer le dépôt GitHub permanent
   `isqsoft/50ohm-question-review-campaigns`.
2. Ajouter sur main uniquement :
    - un README ;
    - les schémas de campagne ;
    - la documentation.

3. Faire lire et écrire ce dépôt directement par l’API GitHub du prototype.
4. N’utiliser un clone local que temporairement pour les outils en ligne de
   commande et conserver le même historique lorsque le dépôt sera transféré
   vers son emplacement de production.

Le dépôt peut être privé pendant les essais. Il ne s’agit pas encore d’un
déploiement en production. Aucun checkout local permanent n’est requis.

### 3. Construire les outils de campagne

Dans 50ohm-question-pool :

1. Créer l’exporteur de campagne.
2. Lui fournir une sélection réduite, par exemple 5 à 10 questions.
3. Exporter les trois langues avec leurs métadonnées.
4. Résoudre les références graphiques dans 50ohm-contents-ch.
5. Enregistrer la branche et le commit des deux dépôts sources.
6. Créer media.refs.json.
7. Créer une branche descriptive dans le dépôt de révision.
8. Y commiter l’état initial de la campagne.

Ensuite, créer l’importeur uniquement en mode --dry-run. À ce stade, aucune écriture canonical ne doit être possible.

### 4. Adapter localement le prototype

L’adaptation doit être progressive :

1. Remplacer les branches codées en dur FR_orig_DeepL, german_orig et WIP.
2. Charger campaign.meta.json depuis une branche de campagne.
3. Lire les objets sous pool/questions/<question_id>/.
4. Afficher une question sans permettre sa modification.
5. Ajouter les sélecteurs de langue de référence et de langue à réviser.
6. Charger les dessins et photos depuis GitHub au commit enregistré.
7. Vérifier les réponses textuelles, les réponses null, les images et le LaTeX.
8. Autoriser ensuite la modification de la langue sélectionnée.
9. Enregistrer dans la branche commune avec vérification du SHA.
10. Ajouter les statuts et commentaires réellement nécessaires.

### 5. Lancer le serveur local

Le serveur local utilisera une application OAuth GitHub dédiée au développement, avec une URL de callback locale.

Les variables existantes sont :

GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET
GITHUB_OWNER
GITHUB_REPO
SESSION_SECRET

Il faudra probablement ajouter une configuration explicite pour la branche de campagne ou la sélectionner depuis l’interface. Les secrets restent dans .env et ne sont jamais transférés par Git.

### 6. Effectuer un test complet

Le premier essai doit couvrir :

1. export de 5 à 10 questions ;
2. création de la branche de campagne ;
3. ouverture dans l’interface locale ;
4. affichage DE/FR/IT ;
5. affichage des dessins et photos ;
6. modification d’une question ;
7. modification concurrente simulée ;
8. sauvegarde GitHub ;
9. rapport d’import --dry-run ;
10. vérification qu’aucun fichier canonical n’a changé.

### 7. Préparer le transfert au serveur

Le transfert doit se faire par commits, pas par copie manuelle du workspace.

Il faudra fournir à l’autre agent :

1. Lire docs/PROPOSITION_BETA_REVIEW_WORKFLOW.fr.md.
2. Ne modifier ni le contrat de campagne ni le modèle canonical.
3. Récupérer les commits indiqués de 50ohm-question-pool et
   50ohm-pool-question-review-tool.
4. Configurer les secrets GitHub localement, sans les commiter.
5. Pointer GITHUB_REPO vers le dépôt permanent de révision.
6. Déployer exactement la version testée localement.
7. Vérifier lecture, authentification, médias, LaTeX et sauvegarde SHA.
8. Ne lancer aucun import canonical réel : utiliser uniquement --dry-run.
9. Documenter toute différence liée au serveur avant de la corriger.

Le document de transfert devra aussi contenir les branches, les commits exacts, les commandes de test et les résultats obtenus.

### 8. Passer en production

Seulement après le test serveur :

1. déplacer ou renommer le dépôt de révision si nécessaire ;
2. adapter sa configuration sans changer son historique ;
3. effectuer une campagne pilote réelle ;
4. vérifier le rapport --dry-run ;
5. autoriser ensuite explicitement l’import canonical réel.

Le prochain travail concret devrait donc être la définition détaillée de campaign.meta.json et media.refs.json, avant toute adaptation du prototype.
