# interopRapprochement

## Objectif
Création d'une plateforme de réconciliation pour le service de transfert **WTB** (Wallet-to-Bank) et **BTW** (Bank-to-Wallet), initialement avec **MVOLA**, étendue à **Orange Money** (cf. section dédiée plus bas). `Airtel Money` reste anticipé en placeholder dans l'interface.

Pour chaque service, deux sources de transactions à rapprocher (clé de jointure : `TRANSID_MVOLA` / `transid_om` selon le service) :
1. Export du wallet mobile money (CSV pour MVOLA, XLS pour Orange Money — voir sections dédiées)
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

## Service Orange Money (OM)

Même pipeline que MVOLA (import fichier → requête CBS → rapprochement bulk → écarts →
notifications, cf. "Décisions prises" et Sprints ci-dessous), avec deux sources différentes.
Clé de jointure : `transid_om` (alias SQL `TRANSID_ORANGE_MONEY`, équivalent de `TRANSID_MVOLA`).

### Source 1 : transactions Orange Money (XLS)

- Emplacement : `/input/*`
- Nom de fichier : `Daily-ChannelUserTransactionReport-<compte>-YYYYMMDD.xls` (ex. :
  `Daily-ChannelUserTransactionReport-0324660679-20260907.xls`, date en fin de nom).
- Format : `.xls` binaire legacy (BIFF/OLE2, pas un `.csv`) — lu avec `xlrd` (`openpyxl` ne
  supporte que `.xlsx`). Le fichier est un relevé de rapport : ~22 lignes d'en-tête de
  métadonnées, puis un tableau avec des lignes d'en-tête de colonnes répétées à chaque section et
  des lignes de sous-total/section (`Total`, `Solde`) intercalées entre les lignes de
  transaction.
- Repérage des lignes de données : la cellule de la colonne A (`N°`) est de type numérique xlrd
  pour une vraie ligne de transaction, et vide/textuelle pour toutes les autres lignes (en-têtes,
  séparateurs, sections, totaux/soldes) — critère vérifié fiable sur fichier réel, utilisé plutôt
  que de repérer la position de l'en-tête (qui varie selon le nombre de sections).
- Colonnes (0-indexées) :

  | Colonne | Description |
  |---|---|
  | A | N° (numéro de ligne du relevé) |
  | B | Date (texte `dd/mm/yyyy`) |
  | C | Heure (texte `HH:MM:SS`) |
  | D | Référence transactionnelle OM — **clé de rapprochement** (`transid_om`), équivalent du `RequestID` côté CBS |
  | E | Service (ex. `Merchant Payment`) |
  | F | Paiement |
  | G | Statut — **seules les lignes `Succès` sont importées**, les lignes `Echec` sont comptées (`nb_hors_succes`) et ignorées |
  | H | Mode/canal (USSD / application OM) |
  | I | N° de compte technique (agent) |
  | J | Wallet (agent) |
  | K | N° Pseudo |
  | L | **MSISDN client** |
  | M | Wallet (correspondant) |
  | N | Débit |
  | O | **Crédit — montant à rapprocher** |
  | P | Commissions (MGA) |
  | Q | Sous-réseau (non utilisé) |

- Colonnes E, F, H, I, J, K, M, N, P non utilisées pour le rapprochement mais conservées pour
  l'audit (mêmes principes que MVOLA qui stocke `SOLDE_PIVOT_AVANT`/`APRES` sans s'en servir pour
  matcher).

### Source 2 : transactions PAMF pour Orange Money (base CBS / SQL Server)

Même requête que MVOLA (cf. Source 2 MVOLA ci-dessus) avec `rMerchantID = 9` (Orange Money, au
lieu de 13 pour MVOLA) et alias `TRANSID_ORANGE_MONEY` :
```sql
select
  mc.rAutotransactionID,
  isnull(mc.postingDate, cast(al.RequestDateCreated as date)) as postingDate,
  mc.Time,
  mc.Note,
  al.RequestID as TRANSID_ORANGE_MONEY,
  al.responseBody,
  case when mc.Status = 3 then 1 else 0 end as is_sucess
from bagsPAMF_CBS_MC.dbo.apiLog al
left join cbs.dbo.mcTransaction mc on mc.requestID = al.apiLogID and mc.rMerchantID = 9
where al.rMerchantID = 9 and al.apiServiceId in (302, 303, 700) and cast(al.RequestDateCreated as date) = ?
```
- Structure et sémantique identiques à MVOLA (`is_success` dérivé de `Status = 3`, `left join`
  pour ne pas perdre les lignes `apiLog` sans correspondance `mcTransaction`, cf. décision du
  2026-09-14 rappelée en Source 2 MVOLA).

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
- **Organisation de l'interface : sidebar par service.** La navigation principale est une sidebar listant les services de rapprochement : `MVOLA` et `Orange Money` (actifs), `Airtel Money` toujours en placeholder "bientôt disponible" pour anticiper son ajout futur. L'écran d'un service est organisé en onglets : `Import <service>` et `Lancement rapprochement`. Ce dernier affiche la liste des rapprochements (un par date, avec les compteurs transactions service / PAMF / rapprochées / orphelines) et un bouton "Détails" qui ouvre un modal Bootstrap chargé via HTMX, avec 3 sous-onglets paginés (HTMX) : transactions du service, transactions PAMF, orphelines.
- **Destinataires des notifications email.** Utilisateurs actifs (`is_active`) avec `is_email_verified=True` (inscription standard via le module `user`), **ou** `is_staff=True` (comptes admin/superuser créés hors du flux d'inscription, qui ne passent jamais par la validation email). Pas encore de préférences de notification par utilisateur ni de ciblage par rôle — à revoir au Sprint 6 quand les rôles dynamiques existeront.
- **Export Excel/PDF sur les tableaux, avec entête de rapport.** Chaque tableau de consultation (Transactions MVOLA, Transactions PAMF, Ecarts) et chacun des 3 sous-onglets du modal de détail d'un rapprochement (MVOLA/PAMF/orphelines) affiche desormais un bloc d'entête au-dessus du tableau (module source de l'extraction, filtres actuellement appliqués, nombre total de lignes, utilisateur et horodatage de génération) et deux boutons "Export Excel"/"Export PDF". Infrastructure commune dans `core.reports` (`build_meta`, `decrire_filtres`, `urls_export`, `export_excel`/`export_pdf`/`exporter`), réutilisée par `transactions` et `ecarts` — chaque écran définit juste ses colonnes `[(libellé, fonction d'extraction), ...]`.
  - L'export relance la même requête filtrée que l'écran (les fonctions `_filtrer_*` sont partagées entre la vue d'affichage et la vue d'export) mais **sans pagination** : toutes les lignes correspondant aux filtres sont exportées, pas seulement la page HTMX affichée.
  - Excel via `openpyxl` (fichier `.xlsx` brut, exploitable dans un tableur) ; PDF via `xhtml2pdf` (rendu HTML→PDF d'un template dédié `core/rapport_pdf.html`, mise en page A4 paysage) — choix fait pour éviter une dépendance système (WeasyPrint nécessite GTK/Cairo, absent par défaut sur les postes Windows PAMF).
  - Les URLs d'export (`.../export/<format>/`) sont ouvertes à tout utilisateur connecté (`@login_required`), au même niveau d'accès que la consultation elle-même — pas de nouveau privilège dédié à l'export.
- **Gestion des utilisateurs (écran `/compte/utilisateurs/`, privilège `gerer_utilisateurs`) : création directe, activer/désactiver, réinitialisation du mot de passe.**
  - Création (`UtilisateurCreationForm`, formulaire dédié — pas le flux d'inscription publique) : l'admin définit username/email/nom/prénom/mot de passe et les rôles directement. Le compte est créé **actif immédiatement** avec `is_email_verified=True` : contrairement à l'auto-inscription (module `user`, validation par email obligatoire), un compte créé par un admin n'a pas besoin de repasser par l'activation par email — l'admin vouche pour la personne.
  - Activer/désactiver (`is_active`) : un bouton bascule l'état ; un compte désactivé ne peut plus se connecter (vérifié par `ModelBackend` nativement, aucune logique custom nécessaire). Garde-fou : un administrateur ne peut pas désactiver son propre compte (évite un auto-verrouillage), le bouton est simplement masqué sur sa propre ligne et la vue re-vérifie côté serveur.
  - Changement de mot de passe : réinitialisation **côté admin uniquement** (`DefinirMotDePasseForm`, basé sur `django.contrib.auth.forms.SetPasswordForm` — ne demande pas l'ancien mot de passe). Pas de page "changer mon propre mot de passe" en self-service pour l'instant (décision explicite, à revoir si le besoin apparaît).
- **Ajout du service Orange Money (OM) : duplication plutôt que généralisation.** Même pipeline que MVOLA (import → requête CBS → rapprochement bulk → écarts → notifications), implémenté par des modèles/vues/URLs parallèles suffixés `OM`/`om` (`TransactionOM`, `TransactionPamfOM`, `RapprochementOM`, `ResultatRapprochementOM`, `EcartOM`, `EcartHistoriqueOM`, app `ecarts.services_om`) plutôt qu'une généralisation de `Rapprochement`/`ResultatRapprochement`/`Ecart` avec un champ `service`. Cohérent avec le code existant qui ne généralisait déjà rien entre les deux sources d'une même réconciliation (`TransactionMvola`/`TransactionPamf` sont deux modèles concrets distincts) ; évite aussi de toucher au code MVOLA déjà validé sur données réelles. Les briques déjà génériques sont réutilisées telles quelles : `core.reports`/`core.pagination`/`core.htmx`, la vérification "journée CBS terminée" (`JourneeCbsNonTerminee`, `fetch_derniere_activite`, indépendante du marchand), et les formulaires d'action sur un écart (`CommentaireForm`, `ChangerStatutForm`, `PieceJointeForm`, `TicketAspektForm`, `RollbackConfirmeForm`).
  - Nouveau privilège dédié `importer_fichier_om` (catalogue `user.privileges`, distinct de `importer_csv_mvola`) : format source différent (XLS vs CSV), donc geste d'import distinct à autoriser séparément. `lancer_rapprochement` et `traiter_ecarts` restent partagés entre MVOLA et OM (déjà nommés génériquement, pas de suffixe service).
  - Import OM : le fichier `.xls` (legacy BIFF/OLE2, lu via `xlrd` — `openpyxl` ne supporte que `.xlsx`) est un relevé de rapport avec des lignes d'en-tête/section/sous-total intercalées ; le parseur (`transactions.xls_om`) isole les vraies lignes de transaction par le type de cellule (numérique) de la colonne N°, et ne conserve que les lignes `Statut = Succès` (comptage séparé `nb_hors_succes` pour les lignes `Echec`, pas une erreur).
  - Validé sur données réelles (`input/Daily-ChannelUserTransactionReport-0324660679-20260907.xls`) : 190 lignes de transaction détectées (31 `Echec` + 159 `Succès`), 159 lignes importées.
- **Paiement scindé sur plusieurs prêts côté CBS : plusieurs postings pour un même transid, résolution manuelle (pas d'agrégation automatique).** Incident réel du 08/09/2026 côté Orange Money (`IntegrityError` sur `TransactionPamfOM.transid_om`, alors unique) : un paiement marchand peut être posté par le CBS sur **plusieurs `mcTransaction`** (un `rAutotransactionID` par prêt réglé, visible dans `responseBody.Body.LoanList`) tout en partageant le même `RequestID`/transid. L'utilisateur a confirmé (requête CBS testée en `SELECT DISTINCT`) que le même phénomène existe côté **MVOLA** — ce ne sont pas des doublons exacts éliminables par `DISTINCT`, mais de vraies lignes différentes. `TransactionPamf(OM).transid_mvola/transid_om` ne sont donc plus uniques (contrainte déplacée sur le couple `(transid, rAutotransactionID)` pour les deux services), et le dédoublonnage à l'import (`services_pamf(_om).importer_transactions_pamf(_om)`) se fait sur cette même paire.
  - **Décision (remplace une première version auto-agrégée du 2026-09-15, explicitement rollback à la demande de l'utilisateur) : aucune résolution automatique.** Dès qu'un transid a plus d'une ligne `TransactionPamf(OM)` pour la date rapprochée, le moteur (`lancer_rapprochement`/`lancer_rapprochement_om`) crée un `ResultatRapprochement(OM)` de statut `DOUBLON_PAMF` (`transaction_pamf` laissé `NULL`), génère un `Ecart(OM)` de type `DOUBLON_PAMF` avec action recommandée `CHOISIR_POSTING` — cela prime sur toute autre règle (y compris l'exclusion "absente + échec"). Sur l'écran de détail de l'écart, l'agent voit tous les postings candidats (rAutotransactionID, heure, note, statut CBS) et choisit celui à retenir ; le choix est tracé en `EcartHistorique(OM)` (action `RESOLUTION_DOUBLON`, `reference_externe` = rAutotransactionID choisi), sans recalcul automatique du statut ensuite — `DOUBLON_PAMF` reste un marqueur historique de l'ambiguïté initiale, et l'écart se traite/se clôture normalement (DETECTE/EN_COURS/REGULARISE) comme n'importe quel autre écart.
  - `Rapprochement(OM).nb_pamf` compte des transids distincts (transactions métier), pas des lignes `TransactionPamf(OM)` brutes — cohérent avec `nb_mvola`/`nb_om`. Un nouveau compteur `nb_doublons_pamf` est affiché à côté des compteurs existants (historique des rapprochements, modal de détail).
  - Revalidé sur données réelles (Orange Money, 2026-09-08, 2 paiements scindés, tous postings réussis) : classés `DOUBLON_PAMF`/`CHOISIR_POSTING` au lieu d'être auto-résolus en `SUCCESS`.
- **Cause racine identifiée des postings scindés Orange Money : `repaymentByAlias` (`apiServiceId=303`, remboursement sans montant précisé) → CBS scinde automatiquement sur les prêts actifs échus à cette date.** Le `DOUBLON_PAMF` ci-dessus reste le filet de sécurité général (`apiServiceId` 302/700, ou tout autre cas imprévu), mais ce cas précis est **connu et non ambigu** : `mc.AmountCRY` de chaque posting correspond exactement au montant du prêt associé dans `responseBody.Body.LoanList` (vérifié sur 2026-09-08 : 31785.61+40414.39=72200.00 et 259784.45+215.55=260000.00). `REQUETE_PAMF_OM` (`transactions/cbs.py`) est donc un `UNION ALL` de 2 branches : `apiServiceId=303` est agrégé en SQL par `RequestID` (`SUM(mc.AmountCRY)`, `Note` = concaténation des `Note` par prêt via `FOR XML PATH` — `STRING_AGG` indisponible, CBS tourne en SQL Server 2016 —, succès seulement si **tous** les postings du groupe ont réussi, `rAutotransactionID` = le plus petit des postings du groupe comme référence), `apiServiceId` 302/700 restent renvoyés ligne par ligne (comportement inchangé, doublon éventuel toujours géré par `DOUBLON_PAMF`). `fetch_transactions_pamf_om` passe désormais la date deux fois (une par branche de l'`UNION ALL`).
  - Nouveau champ `TransactionPamfOM.montant` (le montant CBS, `AmountCRY` sommé pour un remboursement scindé), affiché dans l'écran de détail d'écart, la liste "Transactions PAMF" et son export. Pas encore utilisé dans la logique de rapprochement (le matching reste basé sur la seule présence/absence du transid), simple donnée d'audit pour l'instant.
  - MVOLA (`rMerchantID=13`) utilise vraisemblablement le même `apiServiceId=303`, mais aucun cas réel de scission n'a été constaté sur les dates vérifiées (2026-09-11) : `REQUETE_PAMF` (MVOLA) n'a **pas** été modifiée pour l'instant — à revoir si un incident similaire y est constaté.
  - Revalidé sur données réelles (Orange Money, 2026-09-08, après réimport avec la requête agrégée) : les 2 paiements scindés sont désormais classés `SUCCESS` directement (`nb_doublons_pamf` repassé à 0, `nb_success` 121→123).
- **`mc.Status != 3` ne suffit pas à conclure à un échec côté PAMF : certaines transactions sont malgré tout postées sur les comptes clients.** Signalé par l'utilisateur le 2026-09-15 avec une requête de vérification (`cbs.dbo.accAccountTransaction` filtrée sur `debitCredit = -1` et `rTransactionTypeID in (1511, 1512, 1613, 1328, 1329)`, `UNION` avec `cbs.dbo.loLoanCredit`, par `postingDate`) qui liste, tous marchands confondus, les `rAutoTransactionID` ayant réellement mouvementé un compte (courant/épargne/prêt) ce jour-là — y compris des transferts compte-à-compte, dépôts en agence, etc., sans lien avec MVOLA/OM : cette requête sert uniquement de filtre de correspondance sur `rAutoTransactionID`, jamais de source de vérité seule.
  - **`REQUETE_PAMF`/`REQUETE_PAMF_OM` (`transactions/cbs.py`) intègrent désormais cette vérification via une CTE `MouvementsCompte`** (mêmes deux tables/conditions que la requête de l'utilisateur, filtrée sur la date interrogée) jointe sur `rAutoTransactionID` : `is_sucess` passe à 1 dès que `mc.Status = 3` **ou** que la ligne apparaît dans `MouvementsCompte`, même si `Status != 3`. Pour la branche agrégée `apiServiceId=303` (OM), ce critère élargi s'applique posting par posting *avant* le `min()` par groupe — la règle "succès seulement si tous les postings du remboursement scindé ont réussi" reste inchangée, seule la définition du succès d'un posting individuel est élargie.
  - Conséquence sur `ResultatRapprochement(OM).action_recommandee` : une transaction jusque-là classée `ORPHELINE_MVOLA`/`ORPHELINE_OM` avec recommandation `TICKET_ASPEKT` (PAMF présente mais `is_success=False`) peut désormais ressortir directement `SUCCESS` (rapprochée) si le mouvement de compte est trouvé — corrige un faux écart, pas seulement une recommandation.
  - `fetch_transactions_pamf` passe désormais la date 3 fois (2× pour la CTE, 1× pour le `where` principal) ; `fetch_transactions_pamf_om` la passe 4 fois (2× pour la CTE partagée par les 2 branches de l'`UNION ALL`, puis 1× par branche).
  - Non encore revalidé sur données réelles à ce stade (pas d'accès CBS depuis cet environnement) — à confirmer par l'utilisateur sur une date connue pour avoir des orphelines `Status != 3` mais un mouvement de compte réel.
- **`apiLog.rMerchantID`/`apiLog.apiServiceId` peuvent eux-mêmes être corrompus (constaté à `0`/`0` sur une ligne réelle du 2026-09-07, `RequestURL` = `/api/loanRepaymentByAlias/...`), alors que le `mcTransaction` associé porte bien le vrai `rMerchantID` (9) et a été posté (`Status=3`).** Comme `REQUETE_PAMF`/`REQUETE_PAMF_OM` filtrent sur les colonnes d'`apiLog`, une telle ligne disparaissait entièrement du résultat malgré une transaction réellement postée côté CBS — l'utilisateur a d'abord tenté `(al.rMerchantID = 9 or mc.rMerchantID = 9)` seul, insuffisant car `al.apiServiceId = 0` échouait toujours le filtre `apiServiceId in (302, 303, 700)`/`= 303`.
  - **Filtre marchand** : repli sur `mc.rMerchantID` quand `al.rMerchantID` ne correspond pas (`al.rMerchantID = 13/9 or mc.rMerchantID = 13/9`) — fiable car le `LEFT JOIN` relie `mc` à **cette** ligne `apiLog` précise via `mc.requestID = al.apiLogID`, pas une corrélation approximative.
  - **Filtre service** : repli sur `al.RequestURL like '%/loanRepaymentByAlias/%'` (colonne non affectée par cette corruption) pour reconnaître un appel équivalent à `apiServiceId=303`, en plus du test exact sur `apiServiceId`. Appliqué à `REQUETE_PAMF` (MVOLA, filtre unique) et à la seule branche `303` agrégée de `REQUETE_PAMF_OM` — **pas** à la branche `302/700`, qui n'a pas ce problème constaté et où un repli large créerait un doublon avec la ligne déjà captée par la branche `303`.
  - Portée volontairement limitée à ce cas précis (repaymentByAlias) faute de connaître le pattern d'URL des autres `apiServiceId` (302, 700) : une corruption `0/0` sur un appel qui ne serait pas un repaiement reste un angle mort non couvert, à revoir si constaté.
- **Conteneur de page uniformément élargi (`app-shell`, `static/css/debian13.css`, `max-width: 1140px` -> `1900px`) sur tout le site** (demande explicite du 2026-09-15, après une première version scopée uniquement aux 2 listes d'écarts via une classe modificatrice `app-shell-wide` optionnelle, abandonnée pour garder un rendu cohérent partout). Les pages de formulaire (login, register, rôles, etc.) ne sont pas affectées visuellement : elles s'auto-contraignent déjà avec des colonnes Bootstrap (`col-md-5`/`col-md-6`) à l'intérieur du conteneur, qui n'en devient que plus centré.
  - Piège de déploiement identifié à cette occasion : en prod (`DEBUG=False`), WhiteNoise sert les statiques depuis `STATIC_ROOT` (`staticfiles/`, `CompressedManifestStaticFilesStorage`) et non depuis `static/` (`STATICFILES_DIRS`) — modifier `static/css/debian13.css` seul ne change rien tant que `python manage.py collectstatic --noinput` n'a pas régénéré le fichier haché et `staticfiles/staticfiles.json`. A faire systématiquement après tout changement de statique, suivi d'un redémarrage du process app.
- **MaJ en masse sur les listes d'écarts MVOLA/OM (`/ecarts/mvola/ecarts/`, `/ecarts/om/ecarts/`) : sélection multi-lignes (case à cocher + tout sélectionner) + application groupée de 3 actions, demande explicite du 2026-09-15.** Actions retenues (les 2 autres possibles - pièce jointe, confirmation de rollback - explicitement exclues par l'utilisateur, trop spécifiques à une transaction pour avoir un sens en masse) :
  - Changer le statut (même nouveau statut pour tous les écarts cochés)
  - Ajouter un commentaire (même texte sur chaque écart coché)
  - Enregistrer un ticket Aspekt (même référence sur chaque écart coché - couvre le cas d'un seul ticket Aspekt ouvert pour plusieurs transactions)
  - Implémenté par `BulkActionForm` (un seul formulaire partagé MVOLA/OM, `ecarts/forms.py` - les choix de statut sont des chaînes identiques des deux côtés, pas de raison de dupliquer) et deux vues `mvola_bulk_action`/`om_bulk_action` (`ecarts/views.py`, `@privilege_required(traiter_ecarts)`, même privilège que les actions unitaires) qui bouclent sur les `Ecart(OM)` dont le `pk` est coché et réutilisent telles quelles les fonctions `services(_om).changer_statut/ajouter_commentaire/enregistrer_ticket_aspekt` (une entrée `EcartHistorique(OM)` par écart traité, mêmes règles qu'en unitaire - ex. changement de statut vers la valeur déjà en place toujours sans bruit d'historique).
  - Portée volontairement limitée à la page HTMX actuellement affichée (pas de sélection "toutes les pages"/persistée entre pages) : le bouton "tout sélectionner" ne coche que les lignes visibles.
  - Les cases à cocher et la barre d'action sont **dans** le même `<form>` que le tableau (`ecarts/templates/ecarts/partials/liste_table.html`/`liste_om_table.html`), qui poste sur l'URL dédiée puis redirige vers la liste en réappliquant les filtres/pagination courants (champ caché `_querystring`, repris du contexte `querystring` déjà utilisé par la pagination HTMX) plutôt que de perdre le contexte de filtrage.
  - Comme le reste des actions de traitement d'écart dans ce projet, la barre d'action en masse s'affiche sans vérifier `has_privilege` côté template (cohérent avec `detail.html`/`om_detail.html`) : l'application du privilège `traiter_ecarts` reste uniquement côté serveur (403 si absent).
  - **Garde-fou UX ajouté le 2026-09-15 : la sélection multiple et la barre d'action en masse ne s'affichent que si les filtres Statut ET Action recommandée sont *tous les deux* renseignés** (`filtre_applique`, calculé dans `_filtrer_ecarts(_om)` par `bool(data['statut']) and bool(data['action_recommandee'])` une fois le formulaire validé, propagé au contexte des deux vues `mvola_liste`/`om_liste`) — intention explicite de l'utilisateur : forcer à cibler précisément un lot homogène (même statut, même action à mener) avant d'autoriser une action de masse, pas juste "un filtre quelconque" (première version, resserrée sur demande explicite le jour même). Sans ces deux filtres, le tableau s'affiche normalement (sans colonne case à cocher) avec un message invitant à les renseigner. C'est une nudge d'interface uniquement, pas un contrôle de sécurité : `mvola_bulk_action`/`om_bulk_action` continuent d'accepter n'importe quelle liste de `pk` côté serveur (seul le privilège `traiter_ecarts` est verifié), que ces filtres aient été appliqués ou non côté écran.

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

### Sprint 6 — Rôles dynamiques, permissions & finitions (en cours)
- [x] Modèle `Role`/`Permission` dynamique (app `user`) : `Role` custom (pas les `Group`/`Permission` natifs de Django, choix explicite de l'utilisateur) avec M2M `permissions`, et M2M `User.roles`. `Permission` est un catalogue **fixe** de privilèges (`user.privileges.PRIVILEGE_CHOICES`), seedé par des migrations de données (`user.0003_seed_privileges`, complété au Sprint 7 par `0005_seed_importer_fichier_om`) — pas une liste ouverte à la création par l'utilisateur, seule leur répartition entre rôles est dynamique : `importer_csv_mvola`, `importer_fichier_om`, `lancer_rapprochement`, `traiter_ecarts`, `gerer_roles`, `gerer_utilisateurs`
- [x] `User.has_privilege(code)` : `True` sans condition pour un superuser, sinon vérifie les `Role` assignés. Vues gatées via le décorateur `user.decorators.privilege_required(code)` (403 si connecté mais sans le privilège, redirection login si anonyme) plutôt que le simple `@login_required` : `mvola_import`/`mvola_rapprochement` (transactions), et les 5 vues d'action de `ecarts` (commentaire, changement de statut, pièce jointe, ticket Aspekt, rollback confirmé). Les vues de **consultation** (listes MVOLA/PAMF/écarts, détail d'un écart, modal de détail d'un rapprochement) restent en `@login_required` simple, ouvertes à tout utilisateur connecté
- [x] Interface dédiée (app `user`, pas seulement l'admin Django) : `/compte/roles/` (liste + création + édition des privilèges via checkboxes + suppression), `/compte/utilisateurs/` (liste + assignation des rôles par utilisateur). Suppression d'un rôle bloquée (message d'erreur, pas d'exception) tant qu'il est assigné à au moins un utilisateur, cf. décision initiale. Egalement enregistrées dans l'admin Django (`Role`/`Permission`, `User.roles` en `filter_horizontal`) pour un accès de secours
- [x] Sidebar : nouvelle section "Administration" (sous les services), avec les liens "Rôles"/"Utilisateurs" affichés uniquement si l'utilisateur connecté a respectivement `gerer_roles`/`gerer_utilisateurs` (`User.peut_gerer_roles`/`peut_gerer_utilisateurs`, utilisés côté template car `has_privilege` prend un argument)
- [x] Migration de données `0003_seed_privileges` : crée aussi un rôle `Administrateur` (les 5 privilèges) et l'assigne à tous les superusers existants au moment de la migration — évite qu'un superuser existant (ex. compte `admin` réel utilisé en dev) se retrouve verrouillé hors des fonctionnalités qu'il utilisait déjà avant l'introduction des privilèges
- [x] Durcissement sécurité : déjà en place depuis le Sprint 0/1 (secrets via `.env`, jamais committé) — vérifié à nouveau ici. Accès CBS confirmé lecture seule : `transactions/cbs.py` n'exécute qu'un unique `SELECT` (`fetch_transactions_pamf`), aucune écriture n'existe dans le code vers la base CBS
- [ ] Polish UI/UX (design Debian 13) au-delà des nouveaux écrans roles/utilisateurs, documentation utilisateur

### Sprint 7 — Service Orange Money (OM) ✅ terminé
- [x] Reproduction complète du pipeline MVOLA pour Orange Money (import fichier `.xls` → requête CBS `rMerchantID=9` → rapprochement bulk sur `transid_om` → écarts → notifications → exports), par duplication de modèles/vues/URLs/templates plutôt que généralisation (cf. "Décisions prises")
- [x] Parseur XLS dédié (`transactions.xls_om`) : filtre `Statut = Succès`, ignore les lignes de section/sous-total/en-tête répétées du relevé (repérage par type de cellule, pas par position), validé sur le fichier réel `input/Daily-ChannelUserTransactionReport-0324660679-20260907.xls` (159 lignes `Succès` importées sur 190 lignes de transaction)
- [x] Nouveau privilège `importer_fichier_om` (distinct de `importer_csv_mvola`), `lancer_rapprochement`/`traiter_ecarts` réutilisés tels quels (déjà génériques)
- [x] Sidebar : `Orange Money` passe de placeholder à service actif ; `Airtel Money` reste en placeholder
- [x] Tests dédiés (`transactions.tests_om`, `ecarts.tests_om`) couvrant le parsing XLS sur données réelles, le moteur de rapprochement OM (3 statuts, cas exclu, action recommandée, relance destructive), les actions de traitement d'écart OM, le gating des privilèges, et un filet de sécurité "smoke test" sur tous les écrans/exports OM

> Sprints indicatifs, à ajuster selon les réponses aux "Points à clarifier" ci-dessus.
