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

Requête de référence :
```sql
select
  mc.rAutotransactionID, mc.postingDate, mc.Time, mc.Note,
  al.RequestID as TRANSID_MVOLA, al.responseBody
from cbs.dbo.mcTransaction mc
join bagsPAMF_CBS_MC.dbo.apiLog al on al.apiLogID = mc.requestID
where mc.rMerchantID = 13 and mc.Status = 3 and mc.postingDate = '2026-09-02'
```
- `mcTransaction` : table des transactions du core bancaire (CBS).
- `rMerchantID = 13` : identifie le marchand MVOLA.
- `Status = 3` : transaction validée/postée.
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
  3. Si oui → interrogation de la base CBS (requête PAMF) pour cette même date.
  4. Rapprochement des deux jeux de données (clé `TRANSID_MVOLA`) et **insertion en table locale** du résultat, avec un statut par transaction :
     - `ORPHELINE_MVOLA` — présente côté MVOLA, absente côté PAMF
     - `ORPHELINE_PAMF` — présente côté PAMF, absente côté MVOLA
     - `SUCCESS` — présente des deux côtés (rapprochée)

## Sprints de développement

### Sprint 0 — Socle projet
- Init dépôt git, structure projet Django (apps : `transactions`, `ecarts`, `core`, `user`)
- Config settings dev (SQLite) / prod (PostgreSQL), variables d'environnement (`.env`, secrets CBS + SMTP)
- Auth Django (module `user` : inscription + validation par email via envoi SMTP `mail.pamf.mg`, cf. section "Serveur mail"), design de base (palette/typo Debian 13, Bootstrap)

### Sprint 1 — Ingestion des données
- Formulaire web d'upload du CSV MVOLA (`YYYY-MM-DD_reporting_PAMF.csv`, dépôt manuel par l'utilisateur) → parsing et insertion dans le modèle `TransactionMvola`
- Validation du fichier à l'upload (nom/date, format des colonnes, doublons)
- Connexion pyodbc à la base CBS et requête PAMF → modèle `TransactionPamf`

### Sprint 2 — Moteur de rapprochement
- Écran/action "Lancer la réconciliation" par date : vérifie que le CSV MVOLA de la date a déjà été importé (sinon bloque avec message), puis déclenche la requête CBS pour cette date
- Logique de matching sur `TRANSID_MVOLA` entre `TransactionMvola` et `TransactionPamf`
- Insertion du résultat en table locale avec statut par transaction : `ORPHELINE_MVOLA` (présente MVOLA, absente PAMF), `ORPHELINE_PAMF` (présente PAMF, absente MVOLA), `SUCCESS` (présente des deux côtés)
- Modèle `Ecart` généré à partir des lignes `ORPHELINE_*`, avec statut de suivi (détecté / en cours / régularisé)

### Sprint 3 — Consultation (listes)
- Vue liste + filtres/recherche des transactions MVOLA
- Vue liste + filtres/recherche des transactions PAMF
- Vue liste des écarts (filtrage par statut, date, type)
- Interactions HTMX (pagination, filtres partiels sans rechargement)

### Sprint 4 — Traitement des écarts & régularisation
- Détail d'un écart (transaction MVOLA vs PAMF côte à côte, `responseBody`)
- Actions de traitement (marquer régularisé, commentaire, pièce jointe via `FileField`)
- Historique/suivi des régularisations (qui, quand, quelle action)

### Sprint 5 — Automatisation & planification
- La réconciliation reste déclenchée manuellement par date (cf. Décisions prises) — pas de planification automatique de la requête CBS
- Notifications (email, via le serveur mail `mail.pamf.mg`) en cas de nouvel écart (`ORPHELINE_*`) détecté après une réconciliation
- Django-Q/Celery Beat éventuellement pour des tâches asynchrones (ex: réconciliation longue en tâche de fond) plutôt que pour la planification

### Sprint 6 — Rôles dynamiques, permissions & finitions
- Modèle `Role`/permissions dynamique : CRUD des rôles, assignation/retrait de privilèges par rôle
- Interface admin de gestion des rôles (création, édition des privilèges, suppression si non assigné)
- Assignation des rôles aux utilisateurs
- Durcissement sécurité (secrets, accès base CBS en lecture seule)
- Polish UI/UX (design Debian 13), tests, documentation

> Sprints indicatifs, à ajuster selon les réponses aux "Points à clarifier" ci-dessus.
