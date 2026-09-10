# interopRapprochement

## Objectif
Création d'une plateforme de réconciliation pour le service de transfert **WTB** (Wallet-to-Bank) et **BTW** (Bank-to-Wallet) avec **MVOLA**.

Deux sources de transactions à rapprocher (clé de jointure : `TRANSID_MVOLA`) :
1. Export CSV MVOLA (voir ci-dessous)
2. Base CBS (SQL Server) côté PAMF (voir ci-dessous)

## Source 1 : transactions MVOLA (CSV)

- Emplacement : `/input/*`
- Nom de fichier : `YYYY-MM-DD_reporting_PAMF.csv`
- Séparateur : `;`
- Colonnes (constatées dans les fichiers de `/input`) :

  `DATE_TRANS;TRANSID_MVOLA;STATE;MSISDN;PIVOT;SENS;NOM;TRANSID_PARENT;TRANS_TYPE;AMOUNT;SOLDE_PIVOT_AVANT;SOLDE_PIVOT_APRES;ORIGFTID;TYPE_OPERATION`

  | Colonne | Description |
  |---|---|
  | DATE_TRANS | Date/heure de la transaction (`dd/MM/yyyy HH:mm:ss`) |
  | TRANSID_MVOLA | Identifiant transaction MVOLA — **clé de rapprochement** avec PAMF |
  | STATE | Statut MVOLA (ex: `Completed`) |
  | MSISDN | Numéro de téléphone du client |
  | PIVOT | Compte pivot MVOLA associé |
  | SENS | Sens de l'opération (ex: `C` = crédit) |
  | NOM | Nom du client |
  | TRANSID_PARENT | Transaction parente le cas échéant (0 si aucune) |
  | TRANS_TYPE | Type de transaction (ex: `wallettobank`) |
  | AMOUNT | Montant |
  | SOLDE_PIVOT_AVANT | Solde du compte pivot avant l'opération |
  | SOLDE_PIVOT_APRES | Solde du compte pivot après l'opération |
  | ORIGFTID | Identifiant technique d'origine (UUID) |
  | TYPE_OPERATION | Type d'opération (ex: `WTB`, `BTW`) |

- Fichiers de dev déjà présents : `2026-09-07`, `2026-09-08`, `2026-09-09`.

## Source 2 : transactions PAMF (base CBS / SQL Server)

Requête de référence (mise à jour — ne filtre plus sur `Status`, cf. décision ci-dessous) :
```sql
select
  mc.rAutotransactionID, mc.postingDate, mc.Time, mc.Note,
  al.RequestID as TRANSID_MVOLA, al.responseBody,
  case when mc.Status = 3 then 1 else 0 end as is_sucess
from cbs.dbo.mcTransaction mc
join bagsPAMF_CBS_MC.dbo.apiLog al on al.apiLogID = mc.requestID
where mc.rMerchantID = 13 and mc.postingDate = ?
```
- `mcTransaction` : table des transactions du core bancaire (CBS).
- `rMerchantID = 13` : identifie le marchand MVOLA.
- `is_sucess` (1/0) : dérivé de `Status = 3` (validée/postée). **Toutes les transactions de la journée sont ramenées, y compris celles en échec** — c'est ce champ qui distingue succès/échec côté PAMF, stocké dans `TransactionPamf.is_success`.
- Jointure sur `apiLog` pour récupérer `RequestID` (aliasé `TRANSID_MVOLA`, clé de rapprochement avec le CSV) et `responseBody` (payload brut de l'appel API, utile pour l'investigation d'un écart).
- `postingDate` filtre par jour, à faire correspondre à la date du fichier CSV MVOLA du même jour.

Connexion Python (pyodbc) :
```python
import pyodbc
import platform

def getCon():
    driver = 'SQL Server' if platform.system() == 'Windows' else 'ODBC Driver 17 for SQL Server'
    connection_string = (
        f"DRIVER={{{driver}}};"
        "SERVER=172.20.24.37;"
        "DATABASE=CBS;"
        "UID=Minonja;"
        "PWD=Minonja;"
    )
    return pyodbc.connect(connection_string)
```
> ⚠️ Identifiants en clair ici à titre de référence pour le dev. En Django, les externaliser via variables d'environnement (`django-environ` / `.env`, jamais committé).

## Serveur mail (notifications)

Config SMTP de référence, reprise de `@send_par_daily_email.py` (script existant d'envoi de rapport PAR) :

```python
SMTP_SERVER = "mail.pamf.mg"
SMTP_PORT   = 25
SENDER      = "noreply@pamf.mg"
```

Envoi via `smtplib.SMTP(SMTP_SERVER, SMTP_PORT)` (pas d'auth/TLS dans le script existant — SMTP interne au réseau PAMF).

À utiliser dans le **module `user`** pour les notifications d'**activation de compte lors de l'inscription** (registration) : envoi d'un email contenant le lien/token de validation d'adresse email, cohérent avec `Authentification : Django Auth + validation par email` déjà prévu dans la stack.

> ⚠️ Mêmes règles que pour la connexion CBS : externaliser `SMTP_SERVER`/`SMTP_PORT`/`SENDER` via variables d'environnement plutôt que de les coder en dur.

## Demande fonctionnelle
Site web de gestion des écarts entre transactions MVOLA et PAMF :
- Suivi des régularisations (workflow de statut, traçabilité qui/quand)
- Consultation de la liste des transactions MVOLA
- Consultation de la liste des transactions PAMF
- Consultation des écarts détectés
- Traitement des écarts (actions de résolution, pièces jointes, commentaires)

## Stack technique

| Couche | Technologie |
|---|---|
| Backend | Django (framework web Python) |
| Frontend — interactions | HTMX (appels backend partiels) |
| Frontend — mise en page | Bootstrap + CSS personnalisé |
| Frontend — animations | JavaScript Vanilla |
| Base de données | SQLite pour dev et PostgreSQL (recommandé) pour prod |
| Authentification | Django Auth + validation par email |
| Tâches planifiées | Django-Q ou Celery + Celery Beat |
| Stockage fichiers | Django FileField (pièces jointes de régularisation) |
| Design | Inspiré Debian 13 (palette claire, typographie monospace) |

> Note : la BDD Django (SQLite/PostgreSQL) est distincte de la base CBS (SQL Server), qui est une source externe lue en lecture seule via pyodbc.

## Points à clarifier
_Aucun point ouvert pour le moment._

## Décisions prises
- **Import CSV MVOLA : dépôt manuel depuis le web.** L'utilisateur upload le fichier `YYYY-MM-DD_reporting_PAMF.csv` via un formulaire web (`FileField`), qui déclenche le parsing et l'insertion dans `TransactionMvola`. Ce n'est pas une lecture automatique d'un dossier serveur.
- **Gestion des rôles : dynamique.** Pas de rôles figés dans le code (pas de simple binaire "consultation seule / traitement"). Un administrateur doit pouvoir, depuis l'interface :
  - créer un nouveau rôle
  - ajouter ou retirer des privilèges (permissions) à un rôle existant
  - supprimer un rôle, à condition qu'il ne soit **plus assigné à aucun utilisateur**
  - Implémentation probable : modèle `Role` + `Permission` (ou usage des `Group`/`Permission` natifs de Django, gérés dynamiquement via l'admin/une UI dédiée plutôt que déclarés statiquement dans les vues).
- **Règle de détection d'un écart.** Le service étant du WTB (Wallet-to-Bank), le wallet MVOLA est débité **en premier** : le cas majoritaire d'écart est donc une transaction présente côté **MVOLA** et absente côté **PAMF** (orpheline MVOLA). L'inverse est tout de même vérifié systématiquement : transaction présente côté **PAMF** et absente côté **MVOLA** (orpheline PAMF), même si ce cas doit être plus rare.
- **Déclenchement de la réconciliation.** Processus lancé manuellement par l'utilisateur, **par date** :
  1. L'utilisateur choisit une date et lance la réconciliation.
  2. Le système vérifie que le CSV MVOLA de cette date a déjà été importé manuellement (cf. décision d'import ci-dessus).
  3. Si oui → interrogation de la base CBS (requête PAMF) pour cette même date. **Il n'existe pas d'écran d'import PAMF manuel séparé** : l'appel pyodbc/CBS est uniquement déclenché automatiquement à cette étape.
  4. Rapprochement des deux jeux de données (clé `TRANSID_MVOLA`) et **insertion en table locale** du résultat, avec un statut par transaction :
     - `ORPHELINE_MVOLA` — présente côté MVOLA, et côté PAMF soit absente, soit présente **en échec** (`is_success=False`)
     - `ORPHELINE_PAMF` — présente côté PAMF, absente côté MVOLA
     - `SUCCESS` — présente des deux côtés **et** `is_success=True` côté PAMF
  - Implémenté par `Rapprochement` (un enregistrement par date) + `ResultatRapprochement` (un enregistrement par `TRANSID_MVOLA`), app `transactions`.
- **Relance d'un rapprochement : destructive, par choix.** Relancer le rapprochement d'une date déjà traitée **supprime et recalcule entièrement** ses résultats : tous les `ResultatRapprochement` de la date sont effacés, ce qui supprime en cascade les `Ecart` associés et tout leur `EcartHistorique` (commentaires, changements de statut, tickets Aspekt enregistrés, rollbacks confirmés, pièces jointes — dont le fichier physique sous `media/` est explicitement nettoyé avant la suppression, Django ne le faisant pas lui-même). Le traitement/la régularisation déjà effectués sur une date ne survivent donc **pas** à une relance de cette date.
  - Conséquence assumée sur les notifications (Sprint 5) : comme les `Ecart` sont recréés à chaque relance, le système ne peut plus distinguer un écart déjà connu d'un écart réellement nouveau — une relance renvoie donc un email listant **tous** les écarts actuellement détectés pour cette date, pas seulement les nouveaux.
  - Matching implémenté en insertion bulk (`bulk_create`, par lots de 200) plutôt qu'une requête par transaction : essentiel pour rester rapide en synchrone avec plusieurs centaines/milliers de lignes par jour (cf. CLAUDE.md).
  - Historique de la décision : la version précédente (Sprint 2) était volontairement non destructive (résultats mis à jour en place, écarts jamais recréés) pour préserver le travail de régularisation d'une relance à l'autre. Ce choix a été inversé à la demande explicite de l'utilisateur.
- **Génération des écarts.** A la fin de chaque rapprochement, un `Ecart` (app `ecarts`) est automatiquement créé pour chaque `ResultatRapprochement` de statut `ORPHELINE_MVOLA` ou `ORPHELINE_PAMF` (statut de suivi initial `DETECTE`). Aucun `Ecart` n'est créé pour les lignes `SUCCESS`.
- **Action recommandée pour une orpheline MVOLA.** Déduite (propriété calculée `ResultatRapprochement.action_recommandee`, déléguée par `Ecart.action_recommandee`), jamais stockée en dur — toujours recalculée depuis `transaction_pamf`. Le critère est **la requête a-t-elle atteint Aspekt/CBS**, pas seulement "y a-t-il un problème" :
  - une ligne PAMF existe mais en échec (`is_success=False`) → la requête **a bien atteint** Aspekt/CBS, qui a donc la transaction en main et peut corriger son traitement → **`TICKET_ASPEKT`** : l'agent crée manuellement un ticket dans Aspekt (aucune intégration API — pas d'accès/contrat Aspekt fourni à ce jour) puis enregistre sa référence via le bouton dédié (entrée `EcartHistorique` de type `TICKET_ASPEKT`, `reference_externe` = numéro de ticket).
  - aucune ligne PAMF trouvée → la requête **n'a même pas atteint** Aspekt : il n'a rien à corriger de son côté, un ticket serait inutile → **`ROLLBACK_MVOLA`** : le wallet doit être crédité en retour côté MVOLA. Notre système n'a pas d'accès en écriture à MVOLA (sources en lecture seule) : l'écran affiche la recommandation, l'agent effectue le rollback ailleurs puis clique "Confirmer le rollback effectué" (trace une entrée `EcartHistorique` de type `ROLLBACK_CONFIRME`, avec référence/commentaire libre).
  - Ces deux actions réutilisent le mécanisme d'historique du Sprint 4 plutôt que d'introduire un nouveau modèle de suivi.
  - Validé sur données réelles : après la mise à jour de la requête CBS (suppression du filtre `Status=3`), 17 transactions du 2026-09-07 jusque-là classées `ORPHELINE_MVOLA` sans aucune ligne PAMF se sont révélées avoir en réalité une ligne PAMF en échec → recommandation correcte `TICKET_ASPEKT` (Aspekt a la transaction, peut la corriger), confirmant l'intérêt du changement de requête pour ne pas laisser ces cas sans ticket alors qu'Aspekt peut agir dessus.
- **Organisation de l'interface : sidebar par service.** La navigation principale est une sidebar listant les services de rapprochement : `MVOLA` (actif aujourd'hui), avec `Orange Money` et `Airtel Money` déjà présents en placeholder "bientôt disponible" pour anticiper leur ajout futur. L'écran d'un service est organisé en onglets : `Import <service>` et `Lancement rapprochement`. Ce dernier affiche la liste des rapprochements (un par date, avec les compteurs MVOLA / PAMF / rapprochées / orphelines) et un bouton "Détails" qui ouvre un modal Bootstrap chargé via HTMX, avec 3 sous-onglets paginés (HTMX) : transactions MVOLA, transactions PAMF, orphelines.
- **Destinataires des notifications email.** Utilisateurs actifs (`is_active`) avec `is_email_verified=True` (inscription standard via le module `user`), **ou** `is_staff=True` (comptes admin/superuser créés hors du flux d'inscription, qui ne passent jamais par la validation email). Pas encore de préférences de notification par utilisateur ni de ciblage par rôle — à revoir au Sprint 6 quand les rôles dynamiques existeront.

## Sprints de développement

### Sprint 0 — Socle projet ✅ terminé
- [x] Init dépôt git, structure projet Django (apps : `transactions`, `ecarts`, `core`, `user`)
- [x] Config settings dev (SQLite) / prod (PostgreSQL), variables d'environnement (`.env`, secrets CBS + SMTP)
- [x] Auth Django (module `user` : inscription + validation par email via envoi SMTP `mail.pamf.mg`, cf. section "Serveur mail"), design de base (palette/typo Debian 13, Bootstrap)

### Sprint 1 — Ingestion des données ✅ terminé
- [x] Formulaire web d'upload du CSV MVOLA (`YYYY-MM-DD_reporting_PAMF.csv`, dépôt manuel par l'utilisateur) → parsing et insertion dans le modèle `TransactionMvola`, historique tracé (`ImportFichierMvola`)
- [x] Validation du fichier à l'upload (nom/date, en-tête, format des colonnes, doublons intra-fichier et inter-imports)
- [x] Connexion pyodbc à la base CBS et requête PAMF → modèle `TransactionPamf` (fonction `transactions.services_pamf.importer_transactions_pamf`, historique tracé `ImportRequetePamf`). Pas d'écran dédié : appelée automatiquement au lancement du rapprochement (cf. Sprint 2 et Décisions prises)

### Sprint 2 — Moteur de rapprochement ✅ terminé (l'UI de traitement des écarts reste au Sprint 4)
- [x] Onglet "Lancement rapprochement" par date (écran MVOLA) : vérifie que le CSV MVOLA de la date a déjà été importé (sinon bloque avec message), puis déclenche automatiquement la requête CBS pour cette date
- [x] Logique de matching sur `TRANSID_MVOLA` entre `TransactionMvola` et `TransactionPamf` (`transactions.services_rapprochement.lancer_rapprochement`)
- [x] Insertion du résultat en table locale avec statut par transaction : `ORPHELINE_MVOLA`, `ORPHELINE_PAMF`, `SUCCESS` (modèles `Rapprochement` + `ResultatRapprochement`), recalculés en bulk (`bulk_create`) — une relance efface et recalcule tout, cf. Décisions prises
- [x] Modèle `Ecart` (app `ecarts`) généré automatiquement à partir des lignes `ORPHELINE_*`, avec statut de suivi (`DETECTE` / `EN_COURS` / `REGULARISE`) préservé lors d'une relance
- [x] Liste des rapprochements par date + modal "Détails" (transactions MVOLA / PAMF / orphelines, paginé via HTMX) — couvre une partie de la consultation prévue au Sprint 3
- [x] Matching en requêtes bulk (nombre de requêtes quasi constant quel que soit le volume du jour, teste jusqu'a 300 transactions) ; test de non-regression dédié (`LancerRapprochementPerformanceTests`)
- [x] Validé sur données réelles : 3 jours (2026-09-07/08/09) rapprochés via CBS réel, résultats cohérents (624/607 MVOLA/PAMF le 07/09, 17 orphelines)

### Sprint 3 — Consultation (listes) ✅ terminé
- [x] Vue liste + filtres/recherche des transactions MVOLA (date, TRANSID, MSISDN, nom, type d'opération) — onglet "Transactions MVOLA" de l'écran MVOLA
- [x] Vue liste + filtres/recherche des transactions PAMF (date, TRANSID, rAutotransactionID) — onglet "Transactions PAMF"
- [x] Vue liste des écarts, filtrage par statut / date / type — onglet "Ecarts" (app `ecarts`)
- [x] Interactions HTMX : le formulaire de filtre et la pagination rafraichissent uniquement `#table-container` (`hx-get`/`hx-target`/`hx-push-url`), sans rechargement de page ; requete HTMX detectee cote serveur (`core.htmx.is_htmx_request`) pour ne renvoyer que le fragment
- [x] Pagination factorisee (`core.pagination.paginate`, template `_pagination.html`) réutilisée par les 3 listes et déjà utilisée par le modal de détail (Sprint 2)
- Ces 3 listes sont ajoutées comme onglets supplémentaires de l'écran "Rapprochement MVOLA" (cf. Décisions prises, organisation de l'interface), plutôt que dans une section separée — coherent avec le principe "un service = un ensemble d'onglets"

### Sprint 4 — Traitement des écarts & régularisation ✅ terminé
- [x] Détail d'un écart (`ecarts:detail`, lien "Détails" depuis la liste) : transaction MVOLA vs PAMF côte à côte, `responseBody` affiché (repliable) côté PAMF
- [x] Actions de traitement : changer le statut (`DETECTE`/`EN_COURS`/`REGULARISE`), ajouter un commentaire, joindre un fichier (`FileField`, stocké sous `media/ecarts/pieces_jointes/%Y/%m/`)
- [x] Historique/suivi (modèle `EcartHistorique`, app `ecarts`) : qui (`auteur`), quand (`horodatage`), quelle action (`COMMENTAIRE` / `CHANGEMENT_STATUT` avec ancien+nouveau statut / `PIECE_JOINTE`), affiché en timeline sur l'écran de détail
  - Un changement de statut vers la même valeur ne crée pas d'entrée (pas de bruit dans l'historique)
- [x] Validé sur un écart réel (orpheline MVOLA du 2026-09-07) : commentaire, changement de statut et pièce jointe enregistrés avec le bon auteur/horodatage
- [x] Corrigé au passage (dette Sprint 1) : les tests qui uploadent un fichier (CSV MVOLA, pièce jointe) écrivaient réellement sous `media/` et polluaient l'environnement de dev au fil des exécutions. `TEST_RUNNER` (`config.test_runner.TempMediaTestRunner`) redirige `MEDIA_ROOT` vers un dossier temporaire pendant les tests.
- [x] Extension post-Sprint 5 : requête CBS mise à jour (plus de filtre `Status=3`, ajout `is_sucess`) pour distinguer une transaction PAMF réellement absente d'une transaction présente mais en échec. Deux actions de traitement supplémentaires (cf. Décisions prises - action recommandée) : "Confirmer le rollback effectué" (`ROLLBACK_CONFIRME`) et "Enregistrer le ticket Aspekt" (`TICKET_ASPEKT`), affichées conditionnellement sur l'écran de détail selon l'action recommandée.

### Sprint 5 — Automatisation & planification ✅ terminé (notifications) / non fait (tâche de fond, jugé non nécessaire pour l'instant)
- [x] La réconciliation reste déclenchée manuellement par date (cf. Décisions prises) — pas de planification automatique de la requête CBS (inchangé, aucun développement necessaire)
- [x] Notifications email (`ecarts.notifications.notifier_nouveaux_ecarts`, via le serveur mail `mail.pamf.mg`) envoyées uniquement pour les **nouveaux** écarts (`ORPHELINE_*`) créés lors du rapprochement qui vient de s'exécuter — une relance qui ne détecte rien de neuf ne renvoie pas d'email
  - Envoi différé à la validation de la transaction DB (`transaction.on_commit`), pour ne jamais notifier un rapprochement qui aurait échoué/été annulé
  - Un échec SMTP est journalisé (`logger.exception`) mais ne fait jamais échouer le rapprochement
  - Destinataires : utilisateurs actifs avec email vérifié (inscription standard), **ou** `is_staff`/superuser (comptes créés via `createsuperuser`, qui ne passent pas par l'activation email — bug réel trouvé et corrigé en testant sur les données de dev : le compte `admin` réel n'aurait sinon jamais été notifié)
- Non fait, jugé non nécessaire pour l'instant : passage en tâche de fond (Django-Q/Celery). Le moteur de rapprochement reste synchrone dans la requête HTTP — acceptable vu le nombre de requêtes quasi constant obtenu au Sprint 2 (~17-18 quel que soit le volume/jour). A reconsidérer seulement si un besoin concret apparaît (delai perçu par l'utilisateur, timeout HTTP).

### Sprint 6 — Rôles dynamiques, permissions & finitions
- Modèle `Role`/permissions dynamique : CRUD des rôles, assignation/retrait de privilèges par rôle
- Interface admin de gestion des rôles (création, édition des privilèges, suppression si non assigné)
- Assignation des rôles aux utilisateurs
- Durcissement sécurité (secrets, accès base CBS en lecture seule)
- Polish UI/UX (design Debian 13), tests, documentation

> Sprints indicatifs, à ajuster selon les réponses aux "Points à clarifier" ci-dessus.
