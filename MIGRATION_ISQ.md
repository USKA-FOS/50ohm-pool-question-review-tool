# QRT sous `/isq/qrt/`

La branche de travail est `design/object-centric-canonical`. Le Compose de ce dossier sert `https://50ohm.uska.ch/isq/qrt/` via `127.0.0.1:18082`. Le bloc nginx du serveur HTTPS est dans [deploy/nginx-qrt.conf.example](deploy/nginx-qrt.conf.example) et figure déjà dans le fichier hôte. L'ancien Compose est conservé dans `docker-compose.jp2s.yml`.

## Avant le démarrage

`.env` et `campaigns.json` sont maintenant présents dans ce répertoire, sans commit, avec le mode `600` et le propriétaire `hb9isq:hb9isq` (UID/GID `1006:1006`). Le Compose exécute QRT sous cette identité pour lire le fichier monté en lecture seule. Si le propriétaire change, définir `QRT_FILE_UID` et `QRT_FILE_GID` dans `.env` avant `docker compose up`. `campaigns.json` est exclu de l'image Docker. `CAMPAIGNS_FILE=/app/config/campaigns.json` est imposé par le Compose ; `DEFAULT_CAMPAIGN` désigne une campagne active dans ce fichier.

L'utilisateur a confirmé que l'ancienne configuration `jp2s` n'est plus utilisée. Modifier l'application GitHub OAuth existante avec :

```text
Homepage URL: https://50ohm.uska.ch/isq/qrt/
Authorization callback URL: https://50ohm.uska.ch/isq/qrt/auth/callback
```

Le `.env` local contient déjà `GITHUB_CALLBACK_URL=https://50ohm.uska.ch/isq/qrt/auth/callback`. Si l'application GitHub existante garde le même client ID et le même secret, ne pas modifier ces valeurs dans `.env` : changer seulement les URL dans les réglages GitHub. Conserver aussi `SESSION_SECRET`, `GITHUB_OWNER` et `GITHUB_REPO`. Le démarrage échoue explicitement si le callback local ne correspond pas au préfixe. Le Compose force `URL_PREFIX=/isq/qrt` et `SESSION_HTTPS_ONLY=true`.

## Démarrage et nginx

Depuis ce répertoire, les commandes suivantes ont été exécutées :

```bash
sudo chown hb9isq:hb9isq .env campaigns.json
chmod 600 .env campaigns.json
docker compose config --quiet
sudo docker compose up -d --build question-review
curl -sS http://127.0.0.1:18082/healthz
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' http://127.0.0.1:18082/
```

Dans le **premier bloc `server` HTTPS** de `/etc/nginx/conf.d/50ohm.uska.ch.conf`, [le bloc nginx QRT](deploy/nginx-qrt.conf.example) figure maintenant avant `location /`, avec l'authentification Basic héritée. L'utilisateur a effectué cette modification du fichier système. `sudo nginx -t` passe. Si ce bloc est modifié à l'avenir, conserver d'abord une copie du fichier hors du motif `*.conf`, puis exécuter :

```bash
sudo nginx -t
sudo systemctl reload nginx
```

La première tentative de démarrage a échoué car le callback local dans `.env` avait un chemin mal formé. L'agent a sauvegardé `.env` dans `../qrt-env.before-callback` (mode `600`), corrigé la seule valeur `GITHUB_CALLBACK_URL`, puis recréé le conteneur avec `sudo docker compose up -d --force-recreate question-review`. QRT est maintenant `healthy`. Localement, `/healthz` et `/static/style.css` répondent `200`, `/` redirige vers `/isq/qrt/campaign/review-tool-sandbox/`, et `/login` utilise le callback attendu avec `Path=/isq/qrt` sur son cookie. Vérifier encore dans un navigateur authentifié la page `/isq/qrt/`, une campagne, la connexion GitHub et le retour à la campagne. La carte des campagnes sur l'accueil du site reste masquée jusqu'à cette validation.

Le premier essai OAuth réel a produit « The redirect_uri is not associated with this application. » Le QRT envoie bien `https://50ohm.uska.ch/isq/qrt/auth/callback`. Dans les réglages GitHub de l'application OAuth liée au `GITHUB_CLIENT_ID` de `.env`, remplacer l'URL d'accueil par `https://50ohm.uska.ch/isq/qrt/` et le callback par l'URL exacte ci-dessus. L'utilisateur a confirmé que l'ancien callback `jp2s` n'a plus à être conservé. Le client ID et le secret restent identiques, donc aucun changement du `.env` ou redémarrage du conteneur n'est nécessaire. Refaire ensuite le parcours de connexion dans un nouvel onglet.

Le retour GitHub suivant a répondu « Invalid OAuth state ». Le cookie de session `session` émis auparavant avait `Path=/isq/qrt`, `Secure` et `SameSite=Lax`, mais son nom générique pouvait entrer en conflit avec un autre service du même hôte. Le code précédent est conservé dans `../qrt-main.before-session-cookie.py`. L'application préfixée utilise désormais `50ohm_qrt_session`, et le conteneur a été recréé. Les 65 tests Python et le test JavaScript passent ; un parcours local confirme que le cookie dédié est relu malgré un autre cookie `session`. Refaire la connexion depuis `/isq/qrt/` dans un nouvel onglet pour vérifier le retour OAuth réel.

L'utilisateur a ensuite confirmé que la connexion OAuth fonctionne. La page d'accueil du site affiche maintenant les campagnes actives en interrogeant `GET /isq/qrt/campaigns.json`. Cette API expose uniquement les identifiants et libellés des campagnes actives, avec `Cache-Control: no-store`, sans les branches privées de `campaigns.json`. La liste reflète la configuration chargée au démarrage de QRT : après un changement du fichier privé, recréer QRT pour mettre à jour la liste et les campagnes servies. Le code juste avant l'ajout de cette API est conservé dans `../qrt-main.before-landing-catalog.py`.

## Campagne active depuis le 7 octobre 2026

`Review-YPA-2026-10-07` vient de la branche `campaign/Review-YPA-2026-10-07` du dépôt privé `USKA-FOS/50ohm-question-review-campaigns`. Le manifeste annonce 208 questions allemandes. Comme QRT limite ses identifiants URL aux minuscules, `campaigns.json` configure `review-ypa-2026-10-07` avec cette branche et `enabled: true` ; `.env` contient `DEFAULT_CAMPAIGN=review-ypa-2026-10-07`. `review-tool-sandbox` reste active. Le conteneur a été recréé ; `/campaigns.json` expose les deux libellés et `/` redirige vers `/isq/qrt/campaign/review-ypa-2026-10-07/`.

Le 10 octobre, le manifeste YPA a reçu le commit `3cc32fe` pour rendre modifiables `/class_level`, `/HB/rationale` et `/HB/motivation`. Ces champs étaient absents, ce qui masquait l'onglet « Metadata » ; l'ancien état est `fc06eb8`. QRT récupère le manifeste sur GitHub, sans reconstruire le conteneur. L'onglet et un enregistrement n'ont pas été vérifiés dans le navigateur avant la fermeture.

Le 11 octobre, YPA a été fermée à la demande de l'utilisateur : son entrée reste dans `campaigns.json` avec `enabled: false`, et `.env` utilise de nouveau `DEFAULT_CAMPAIGN=review-tool-sandbox`. Le conteneur recréé est sain, le catalogue ne publie que la campagne de test et l'URL YPA répond `404`. Les sauvegardes avant fermeture, sous `../qrt-campaigns.before-close-review-ypa-2026-10-07.json` et `../qrt-env.before-close-review-ypa-2026-10-07`, permettent de rouvrir YPA après recréation du conteneur ; la branche Git YPA n'a pas été modifiée.

`YPA_letzte_Kampagne` a ensuite été activée avec trois questions allemandes sous l'identifiant URL `ypa-letzte-kampagne`, puis fermée à la demande de l'utilisateur. Les deux entrées YPA sont maintenant conservées avec `enabled: false` ; `DEFAULT_CAMPAIGN=review-tool-sandbox`. Le QRT recréé est sain, son catalogue ne contient que la campagne de test et les deux anciennes URL YPA répondent `404`. Les points de retour privés de la nouvelle campagne sont `../qrt-campaigns.before-close-ypa-letzte-kampagne.json` et `../qrt-env.before-close-ypa-letzte-kampagne` (mode `600`).

Les fichiers privés précédents sont sauvegardés hors du dépôt QRT, sous `../qrt-campaigns.before-review-ypa-2026-10-07.json` et `../qrt-env.before-review-ypa-2026-10-07`, en mode `600`. Les restaurer puis recréer uniquement `question-review` pour annuler cette activation. L'édition authentifiée reste à vérifier par un réviseur.

## Retour arrière

Retirer uniquement le bloc nginx QRT et recharger nginx après `sudo nginx -t`. Arrêter ensuite QRT avec `sudo docker compose stop question-review`. Garder `.env` et `campaigns.json` privés. `docker-compose.jp2s.yml` conserve la configuration antérieure ; ne pas l'exécuter sur ce serveur de destination.

## Campagne pilote CEM_Math_2026-10-27 — 27 octobre 2026

La branche `campaign/CEM_Math_2026-10-27` du dépôt privé
`USKA-FOS/50ohm-question-review-campaigns` contient 56 questions du sous-chapitre
« Allgemeine mathematische Grundkenntnisse und Grössen », extraites de
`Revision_3.0.6`. DE, FR et IT sont consultables ; seul FR est modifiable.
Aucune métadonnée ni référence d’image n’est éditable, ce qui masque le panneau
de détails. Les données techniques et statuts de revue restent gérés par l’outil.

L’entrée `cem-math-2026-10-27` a été ajoutée au `campaigns.json` existant,
sans modifier les huit entrées précédentes. `DEFAULT_CAMPAIGN` reste
`review-tool-sandbox` ; les anciennes campagnes restent fermées.
La sauvegarde privée du fichier avant ajout est :
`../qrt-campaigns.before-CEM_Math_2026-10-27-20261027T145331439164Z.json`.
Le fichier actif conserve le mode 600 et le propriétaire/groupe 1006:1006.
Aucun secret ni paramètre OAuth n’a été modifié.

Après `sudo -n docker compose config --quiet`, seul le service `question-review`
a été recréé avec `sudo -n docker compose up -d --no-deps --force-recreate question-review`,
sans reconstruction de l’image. Le conteneur `50ohm-question-review-isq` est
sain ; `/healthz` répond 200, `/campaigns.json` expose la sandbox et la pilote,
et `/campaign/cem-math-2026-10-27/` répond 200 sur le port local 18082.
Les autres conteneurs n’ont pas été redémarrés.

URL à transmettre au réviseur :
<https://50ohm.uska.ch/isq/qrt/campaign/cem-math-2026-10-27/>.
Le parcours humain connecté reste à vérifier par l’utilisateur. Les quatre
autres campagnes ne sont pas créées. Pour les futures campagnes, fusionner
uniquement leur entrée dans le fichier actuel et recréer le même service,
sans remplacer la configuration complète ni les adaptations locales du code.

## Lot DBB / INL / FBL / HTK — 27 octobre 2026

Les quatre fiches YAML corrigées ont été contrôlées avant toute création :
comptes exacts, langues, source `Revision_3.0.6`, média
`8b6fd6cf4c04d17de64a68360c607885ff8b940e`, SVG présents et absence de
recouvrement entre les nouvelles campagnes d’une même langue.
Les quatre branches ont été publiées par un seul push atomique.

| Campagne | Questions | Langue modifiable | Dessins distincts |
| --- | ---: | --- | ---: |
| DBB_ELEK1_2026-10-27 | 45 | FR | 14 |
| INL_ELEK2_2026-10-27 | 80 | FR | 45 |
| FBL_Math_2026-10-27 | 56 | IT | 0 |
| HTK_ELEK1_2026-10-27 | 45 | IT | 14 |

Les références consultables sont DE/FR/IT. Les champs de métadonnées et
références d’images ne sont pas éditables ; les statuts cibles commencent
à `to_be_reviewed` dans les copies de campagne. Le canonical n’est pas modifié.

Les quatre entrées ont été ajoutées en une seule écriture atomique de
`campaigns.json`, avec une seule sauvegarde préalable :
`/home/dev50ohm/dev/web/qrt-campaigns.before-batch-2026-10-27-20261027T155227791832Z.json`.
Les neuf entrées précédentes sont conservées, y compris la pilote CEM et la
sandbox ; `.env`, OAuth, le défaut sandbox et le code local restent inchangés.
Le fichier conserve le mode 600 et UID/GID 1006:1006.

Après validation Compose, une seule recréation de `question-review`, sans
`--build`, a chargé tout le lot. Le conteneur est sain, `/healthz` et les quatre
routes répondent 200. Le catalogue expose six campagnes : sandbox, CEM et les
quatre nouvelles. Les autres services n’ont pas été redémarrés.

Les nouvelles URL sont :
- <https://50ohm.uska.ch/isq/qrt/campaign/dbb-elek1-2026-10-27/>
- <https://50ohm.uska.ch/isq/qrt/campaign/inl-elek2-2026-10-27/>
- <https://50ohm.uska.ch/isq/qrt/campaign/fbl-math-2026-10-27/>
- <https://50ohm.uska.ch/isq/qrt/campaign/htk-elek1-2026-10-27/>

Les preuves, versions d’export et contrôles sont conservés dans chaque branche
de campagne sous `deployments/`. Aucun contrôle humain connecté ni validation
de question n’a été simulé par l’agent.

## YPA_Kampagne_261007 — 27 octobre 2026

La campagne `campaign/YPA_Kampagne_261007` est publiée et active sous
<https://50ohm.uska.ch/isq/qrt/campaign/ypa-kampagne-261007/>.
Les 80 identifiants uniques viennent du fichier `261027_Kampagne nach 3.0.5.xlsx`.
Le fichier n’a pas d’en-tête : AB104, en première ligne, est une question.
L’utilisateur a confirmé le nombre de 80 après correction du compte initial de 79.

La source est le canonical publié `Revision_3.0.6`, commit
`c51d9bd12befd5d42da91b10a962aa6516fef5f4`, avec les médias
`8b6fd6cf4c04d17de64a68360c607885ff8b940e` (10 dessins distincts).
Référence et édition sont uniquement DE. Les métadonnées `/class_level`,
`/HB/rationale`, `/HB/motivation` sont éditables ; le manifeste distant a été
contrôlé avant activation. Les références d’images restent non éditables.
Les statuts DE initiaux sont `to_be_reviewed` dans la campagne. Aucun texte
ni statut du canonical n’a été modifié.

L’entrée `ypa-kampagne-261007` a été ajoutée sans modifier les 13 entrées
existantes, après sauvegarde privée :
`/home/dev50ohm/dev/web/qrt-campaigns.before-YPA_Kampagne_261007-20261027T221448495511Z.json`.
Le fichier conserve le mode 600, UID/GID 1006:1006. `.env`, OAuth et le défaut
sandbox restent inchangés. Après validation Compose, seul `question-review`
a été recréé sans build. Le conteneur est sain ; la santé et la route YPA
répondent 200. Le catalogue comprend sept campagnes actives, avec la pilote
CEM et les quatre campagnes FR/IT conservées. Aucun autre service n’a redémarré.

La branche conserve le fichier Excel original, la sélection canonique, la
fiche de demande et les preuves de préparation/déploiement. La vérification
humaine connectée reste à faire par les réviseurs ; aucune validation de
question n’a été simulée.


## 2026-10-29 — YPA_Kampagne_261007 closed

At the user's request, disabled only `ypa-kampagne-261007` in
`campaigns.json`, retaining its branch and all other entries. A private
backup was created before atomic replacement. Recreated only the Compose
`question-review` service, with no build or other service restart.
Verification: healthy container, health OK, campaign route 404, six other
active catalog entries preserved. Final campaign revision retrieved for
canonical import: `75b0b9411575c3d04b258a676f997a64fcdc3096`.
The canonical import/closure audit is owned by 50ohm-question-pool under
`review/accepted/campaigns/YPA_Kampagne_261007.*`.


## IIS / EDG — 31 octobre 2026

Deux campagnes publiées depuis Revision_3.0.8 : IIS_AM_FM_2026-10-31,
63 questions, FR modifiable ; EDG_ELEK2_2026-10-31, 80 questions, IT modifiable.
Références DE/FR/IT, sans métadonnées ni images éditables. Correspondance
collaborateur-langue et absence de recouvrement de même langue contrôlées.
Deux entrées ajoutées atomiquement, anciennes entrées inchangées ; sauvegarde :
`/home/dev50ohm/dev/web/qrt-campaigns.before-batch-2026-10-31-20261031T161813633985Z.json`. Une recréation question-review sans build ; santé et routes
200, autres services inchangés. Aucun secret ni défaut modifié.


## CEM / EDG / HTK — 9 novembre 2026

Trois nouvelles campagnes depuis Revision_3.0.9 : CEM_DM_2026-11-09
(46 questions FR), EDG_AM_FM_DM_2026-11-09 (109 questions IT),
HTK_BAU1_2026-11-09 (76 questions IT). Références DE/FR/IT ; métadonnées
et images non éditables. Les campagnes antérieures restent inchangées et
actives selon la consigne explicite de l’utilisateur. Une écriture atomique
après sauvegarde privée : `/home/dev50ohm/dev/web/qrt-campaigns.before-batch-2026-11-09-20261109T102303305094Z.json`.
Une recréation du seul service question-review sans build. Santé et trois
routes HTTP 200, autres services inchangés. Aucun secret ou défaut modifié.


## Fermeture CEM Math / HTK ELEK1 / EDG ELEK2 — 9 novembre 2026

Seules les trois campagnes demandées ont été désactivées pour intégration
au canonical. Les autres campagnes, y compris les trois nouvelles du jour,
restent inchangées. Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-CEM-HTK-EDG-2026-11-09-20261109T124352772901Z.json`.
Une recréation du seul service question-review sans build ; santé 200,
routes fermées 404, autres services inchangés. Branches Git conservées.


## FBL BAU1 — 9 novembre 2026

FBL_BAU1_2026-11-09 activée : 78 questions IT, références DE/FR/IT,
78 dessins ; source Revision_3.0.9. Métadonnées et images non éditables.
Une entrée ajoutée ; toutes les précédentes préservées. Sauvegarde :
`/home/dev50ohm/dev/web/qrt-campaigns.before-batch-2026-11-09-20261109T130929746225Z.json`. Santé et route 200, autres services inchangés.
FBL Math reste active à cette étape ; fermeture distincte ensuite.


## Fermeture FBL Math — 9 novembre 2026

Seule FBL_Math_2026-10-27 est désactivée après déploiement vérifié
de FBL_BAU1_2026-11-09. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-FBL-Math-2026-11-09-20261109T130949688653Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Aucun import canonical demandé à cette étape.


## HTK SCHA1 — 9 novembre 2026

HTK_SCHA1_2026-11-09 activée : 123 questions IT, références DE/FR/IT,
81 dessins ; source Revision_3.0.9. Métadonnées et images non éditables.
Une entrée ajoutée ; toutes les précédentes préservées. Sauvegarde :
`/home/dev50ohm/dev/web/qrt-campaigns.before-batch-2026-11-09-20261109T205512332048Z.json`. Santé et route 200, autres services inchangés.
HTK BAU1 reste active à cette étape ; fermeture distincte ensuite.


## Fermeture HTK BAU1 — 9 novembre 2026

Seule HTK_BAU1_2026-11-09 est désactivée après déploiement vérifié
de HTK_SCHA1_2026-11-09. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-HTK-BAU1-2026-11-09-20261109T205535983230Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## Fermeture FBL BAU1 — 11 novembre 2026

Seule FBL_BAU1_2026-11-09 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-FBL-BAU1-2026-11-11-20261111T162834912737Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## FBL SCHA2 — 11 novembre 2026

FBL_SCHA2_2026-11-11 activée : 85 questions IT, références DE/FR/IT,
44 dessins ; source Revision_3.0.9. Métadonnées et images non éditables.
Une entrée ajoutée ; toutes les précédentes préservées. Sauvegarde :
`/home/dev50ohm/dev/web/qrt-campaigns.before-FBL-SCHA2-2026-11-11-20261111T163203363333Z.json`. Santé et route 200, autres services inchangés.
FBL BAU1 reste fermée ; toutes les autres campagnes sont préservées.


## EDG SE EM 1 — 11 novembre 2026

EDG_SE_EM_1_2026-11-11 activée : 116 questions IT, références DE/FR/IT,
51 dessins ; source Revision_3.0.9. Métadonnées et images non éditables.
Une entrée ajoutée ; toutes les précédentes préservées. Sauvegarde :
`/home/dev50ohm/dev/web/qrt-campaigns.before-EDG-SE-EM-1-2026-11-11-20261111T212505686307Z.json`. Santé et route 200, autres services inchangés.
EDG AM FM DM reste active à cette étape ; fermeture distincte ensuite.


## Fermeture EDG AM FM DM — 11 novembre 2026

Seule EDG_AM_FM_DM_2026-11-09 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-EDG-AM-FM-DM-2026-11-11-20261111T212533143993Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## HTK SE EM 2 — 12 novembre 2026

HTK_SE_EM_2_2026-11-12 activée : 96 questions IT, références DE/FR/IT,
41 dessins ; source Revision_3.0.9. Métadonnées et images non éditables.
Une entrée ajoutée ; toutes les précédentes préservées. Sauvegarde :
`/home/dev50ohm/dev/web/qrt-campaigns.before-HTK-SE-EM-2-2026-11-12-20261112T210702398183Z.json`. Santé et route 200, autres services inchangés.
HTK SCHA1 reste active à cette étape ; fermeture distincte ensuite.


## Fermeture HTK SCHA1 — 12 novembre 2026

Seule HTK_SCHA1_2026-11-09 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-HTK-SCHA1-2026-11-12-20261112T210732515100Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## IIS BAU1 — 13 novembre 2026

IIS_BAU1_2026-11-13 activée : 76 questions FR, références DE/FR/IT,
18 dessins ; source Revision_3.0.9. Métadonnées et images non éditables.
Une entrée ajoutée ; toutes les précédentes préservées. Sauvegarde :
`/home/dev50ohm/dev/web/qrt-campaigns.before-IIS-BAU1-2026-11-13-20261113T111933777234Z.json`. Santé et route 200, autres services inchangés.
IIS AM FM reste active à cette étape ; fermeture distincte ensuite.


## Fermeture IIS AM FM — 13 novembre 2026

Seule IIS_AM_FM_2026-10-31 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-IIS-AM-FM-2026-11-13-20261113T111954273777Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## FBL ANT and CEM BAU2 — 16 November 2026

Activated FBL_ANT_2026-11-16 (104 IT questions, 29 drawings) and CEM_BAU2_2026-11-16 (78 FR questions, 78 drawings). Reference languages DE/FR/IT; no editable metadata/pictures. Both new routes HTTP 200 and service healthy. Other campaigns and services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-FBL-ANT-CEM-BAU2-2026-11-16-20261116T091159801496Z.json`. CEM DM and FBL SCHA2 remain active until the separate closure step.


## CEM DM and FBL SCHA2 closure — 16 November 2026

Disabled only CEM_DM_2026-11-09 and FBL_SCHA2_2026-11-11 after verified activation of their successors. Both closed routes HTTP 404, service healthy, all other entries and services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-close-CEM-DM-FBL-SCHA2-2026-11-16-20261116T091224559994Z.json`. Git branches retained for final retrieval and canonical import.


## FBL LEIT — 16 November 2026

Activated FBL_LEIT_2026-11-16: 102 IT questions, 17 drawings, DE/FR/IT references, no editable metadata/pictures. New route HTTP 200, service healthy; all previous entries preserved. Backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-FBL-LEIT-2026-11-16-20261116T160345575917Z.json`. FBL ANT remains active until separate closure.


## Fermeture FBL ANT — 16 novembre 2026

Seule FBL_ANT_2026-11-16 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-FBL-ANT-2026-11-16-20261116T160408187216Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## EDG WAUS — 17 November 2026

Activated EDG_WAUS_2026-11-17: 84 IT questions, one drawing, references DE/FR/IT, no editable metadata/pictures. New route HTTP 200, service healthy. All previous campaign entries and other services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-EDG-WAUS-2026-11-17-20261117T204400371417Z.json`.


## CEM SCHA — 18 November 2026

Activated CEM_SCHA_2026-11-18: 208 FR questions, 125 drawings, references DE/FR/IT; no editable metadata/pictures. Route HTTP 200 and healthy service. Previous entries and other services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-CEM-SCHA-2026-11-18-20261118T154001550689Z.json`. CEM BAU2 remains active until the separate closure step.


## Fermeture CEM BAU2 — 18 novembre 2026

Seule CEM_BAU2_2026-11-16 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-CEM-BAU2-2026-11-18-20261118T154027851962Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## FBL MESS — 19 November 2026

Activated FBL_MESS_2026-11-19: 82 IT questions, 32 drawings, DE/FR/IT references, no editable metadata/pictures. Route HTTP 200 and healthy service. Previous entries and other services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-FBL-MESS-2026-11-19-20261119T145043303958Z.json`. FBL LEIT remains active until separate closure.


## Fermeture FBL LEIT — 19 novembre 2026

Seule FBL_LEIT_2026-11-16 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-FBL-LEIT-2026-11-19-20261119T145103805988Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## IIS SE EM — 20 November 2026

Activated IIS_SE_EM_2026-11-20: 212 FR questions, DE/FR/IT references, no editable metadata/pictures. Route HTTP 200 and healthy service. Previous entries and other services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-IIS-SE-EM-2026-11-20-20261120T155833765141Z.json`. IIS BAU1 remains active until separate closure.


## Fermeture IIS BAU1 — 20 novembre 2026

Seule IIS_BAU1_2026-11-13 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-IIS-BAU1-2026-11-20-20261120T155841357476Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## Fermeture EDG SE EM 1 — 21 novembre 2026

Seule EDG_SE_EM_1_2026-11-11 est désactivée sur instruction explicite de l’utilisateur. Le libellé serveur portait à tort le 9 novembre ; corrigé au 11 novembre pour correspondre à la fiche, au manifeste et à la branche. Aucun fichier ni branche renommé. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-EDG-SE-EM-1-2026-11-21-20261121T090054782372Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## EDG STO — 21 November 2026

Activated EDG_STO_2026-11-21: 88 IT questions, DE/FR/IT references, no editable metadata/pictures. Route HTTP 200 and healthy service. Previous entries and other services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-EDG-STO-2026-11-21-20261121T092829539508Z.json`. No other campaign was closed.


## Fermeture EDG WAUS — 21 novembre 2026

Seule EDG_WAUS_2026-11-17 est désactivée sur instruction explicite de l’utilisateur. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-EDG-WAUS-2026-11-21-20261121T093324168746Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Récupération complète autorisée : import prévu après gel final et dry-run ; branche et résultats conservés.


## Fermeture HTK SE EM 2 — 21 novembre 2026

Seule HTK_SE_EM_2_2026-11-12 est désactivée sur instruction explicite de l’utilisateur. Le libellé serveur portait à tort le 9 novembre ; corrigé au 12 novembre pour correspondre à la fiche, au manifeste et à la branche. Aucun fichier ni branche renommé. Toutes les autres entrées restent identiques.
Sauvegarde : `/home/dev50ohm/dev/web/qrt-campaigns.before-close-HTK-SE-EM-2-2026-11-21-20261121T135615708225Z.json`. Santé 200, route fermée 404,
autres services inchangés ; branche Git conservée pour récupération.
Import canonical prévu après récupération finale et dry-run.


## HTK EMV — 21 November 2026

Activated HTK_EMV_2026-11-21: 57 IT questions, DE/FR/IT references, no editable metadata/pictures. Route HTTP 200 and healthy service. Previous entries and other services preserved. Private backup: `/home/dev50ohm/dev/web/qrt-campaigns.before-HTK-EMV-2026-11-21-20261121T140746055777Z.json`. No other campaign was closed.
