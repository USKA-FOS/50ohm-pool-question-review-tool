# Glossaire

## API

**Application Programming Interface**, interface de programmation.

Dans cet outil, l'API GitHub permet au serveur de lire des fichiers, comparer
des versions et créer des commits sans utiliser directement l'interface web de
GitHub.

## CDN

**Content Delivery Network**, réseau de distribution de contenu.

Le prototype télécharge actuellement KaTeX depuis un service externe spécialisé
dans la distribution rapide de fichiers JavaScript et CSS.

## CSRF

**Cross-Site Request Forgery**, falsification de requête intersite.

C'est une attaque où un site malveillant amène le navigateur d'un utilisateur
déjà connecté à exécuter une action non désirée. Un jeton CSRF permet au serveur
de vérifier que le formulaire provient bien de son propre site.

## CSS

**Cascading Style Sheets**, feuilles de style en cascade.

CSS définit la présentation visuelle des pages HTML.

## HTML

**HyperText Markup Language**, langage de balisage utilisé pour construire les
pages web.

Une insertion HTML non échappée peut devenir une faille XSS.

## HTTP et HTTPS

**HyperText Transfer Protocol** est le protocole utilisé pour échanger des
pages et des données sur le web. HTTPS est sa version chiffrée et authentifiée.

L'outil doit imposer HTTPS afin de protéger la session et les échanges avec les
réviseurs.

## JSON

**JavaScript Object Notation**, format texte structuré utilisé pour stocker et
échanger les questions, réponses et métadonnées.

## OAuth

Protocole d'autorisation permettant à l'utilisateur de se connecter avec
GitHub sans communiquer son mot de passe GitHub à l'outil de révision.

OAuth fournit un jeton d'accès dont les permissions doivent être limitées et
qui doit rester secret.

## PR

**Pull Request**, demande d'intégration d'une branche Git dans une autre.

Une PR permet de contrôler les modifications, d'exécuter les validations et de
faire approuver les changements avant leur intégration au canonical.

## SHA

**Secure Hash Algorithm**, famille de fonctions d'empreinte numérique.

GitHub fournit une empreinte SHA pour identifier précisément une version de
fichier ou un commit. Le prototype l'utilise pour détecter qu'un fichier a été
modifié depuis son chargement.

## UI

**User Interface**, interface utilisateur.

Il s'agit ici des écrans de navigation, comparaison, édition et validation des
questions.

## URL

**Uniform Resource Locator**, adresse d'une ressource sur le web.

## WIP

**Work In Progress**, travail en cours.

Dans le prototype historique, `WIP` est la branche Git recevant directement les
corrections des réviseurs. Cette convention devra être remplacée par un flux
compatible avec le canonical actuel.

## XSS

**Cross-Site Scripting**, injection de script dans une page web.

Cette faille apparaît lorsque du texte contrôlé par un utilisateur est traité
comme du HTML exécutable. Le contenu doit être échappé avant son affichage.
