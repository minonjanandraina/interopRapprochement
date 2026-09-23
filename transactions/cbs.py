"""Connexion en lecture seule a la base CBS (SQL Server, PAMF). Cf. CLAUDE.md - Source 2."""

import platform

import pyodbc
from django.conf import settings

# Ancienne requete (join interne) : une ligne apiLog sans correspondance dans mcTransaction
# disparaissait silencieusement du resultat. Or l'existence de la ligne apiLog prouve a elle
# seule que la requete a atteint le CBS -> ces cas doivent recommander TICKET_ASPEKT et non
# ROLLBACK_MVOLA (cf. CLAUDE.md, decision du 2026-09-14). Conservee ici a titre de reference.
# REQUETE_PAMF = """
# select
#   mc.rAutotransactionID, mc.postingDate, mc.Time, mc.Note,
#   al.RequestID as TRANSID_MVOLA, al.responseBody,
#   case when mc.Status = 3 then 1 else 0 end as is_sucess
# from cbs.dbo.mcTransaction mc
# join bagsPAMF_CBS_MC.dbo.apiLog al on al.apiLogID = mc.requestID
# where mc.rMerchantID = 13 and mc.postingDate = ?
# """

# mc.Status != 3 ne prouve pas a lui seul l'echec : certaines transactions sont malgre tout
# postees sur les comptes clients (courant/epargne/pret), constate sur donnees reelles (signale
# par l'utilisateur le 2026-09-15). MouvementsCompte recense donc, pour la date interrogee, les
# rAutoTransactionID ayant reellement bouge un compte (debit wallet-pivot via
# accAccountTransaction, ou remboursement de pret via loLoanCredit) - cf. CLAUDE.md, Decisions
# prises. is_sucess passe a 1 des que Status = 3 OU que ce mouvement existe, meme si Status != 3.
#
# al.rMerchantID / al.apiServiceId peuvent eux-memes etre corrompus (constate a 0/0 sur une ligne
# apiLog reelle du 2026-09-07 dont le mcTransaction associe portait bien rMerchantID=13 et
# Status=3) : filtrer uniquement sur les colonnes d'apiLog fait alors disparaitre a tort une
# transaction pourtant bien postee cote CBS. Le filtre merchant retombe donc sur mc.rMerchantID
# quand al.rMerchantID ne correspond pas (le lien exact apiLogID/RequestID via le JOIN garantit
# que mc.rMerchantID decrit bien CETTE requete, pas une correlation fortuite), et le filtre
# apiServiceId retombe sur al.RequestURL (colonne non affectee par cette corruption) pour
# reconnaitre un appel repaymentByAlias (equivalent apiServiceId=303) meme quand apiServiceId=0.
REQUETE_PAMF = """
with MouvementsCompte as (
  select distinct rAutoTransactionID
  from cbs.dbo.accAccountTransaction
  where postingDate = ? and debitCredit = -1
    and rTransactionTypeID in (1511, 1512, 1613, 1328, 1329)
  union
  select distinct rAutoTransactionID
  from cbs.dbo.loLoanCredit
  where postingDate = ?
)
select distinct
  mc.rAutotransactionID,
  isnull(mc.postingDate, cast(al.RequestDateCreated as date)) as postingDate,
  mc.Time,
  mc.Note,
  al.RequestID as TRANSID_MVOLA,
  al.responseBody,
  max(al.apiServiceId) as apiservice,
  max(al.RequestURL) as path,
  max(al.requestBody) as body,
  case when mc.Status = 3 or mvt.rAutoTransactionID is not null then 1 else 0 end as is_sucess
from bagsPAMF_CBS_MC.dbo.apiLog al
left join cbs.dbo.mcTransaction mc on mc.requestID = al.apiLogID and mc.rMerchantID = 13
left join MouvementsCompte mvt on mvt.rAutoTransactionID = mc.rAutotransactionID
where (al.rMerchantID = 13 or mc.rMerchantID = 13)
  and (al.apiServiceId in (302, 303, 700) or al.RequestURL like '%/loanRepaymentByAlias/%')
  and cast(al.RequestDateCreated as date) = ?
group by mc.rAutotransactionID, mc.postingDate, mc.Time, mc.Note, al.RequestID, al.responseBody, mc.Status, mvt.rAutoTransactionID
"""

# apiServiceId = 303 (repaymentByAlias, remboursement sans montant precise) : le CBS scinde
# automatiquement le remboursement sur les prets actifs ayant une echeance a cette date, ce qui
# cree plusieurs mcTransaction/rAutotransactionID (un par pret, cf. responseBody.Body.LoanList)
# pour un meme RequestID/transid_om - un cas metier connu, pas une vraie ambiguite. Confirme sur
# donnees reelles (2026-09-08) : mc.AmountCRY de chaque posting correspond exactement au montant
# du pret associe dans LoanList. On agrege donc ces postings en une seule ligne (SUM(AmountCRY),
# succes seulement si tous les postings ont reussi) directement en SQL, cf. CLAUDE.md - Decisions
# prises. Les autres apiServiceId (302, 700) restent renvoyes ligne par ligne : un doublon qui y
# apparaitrait reste une vraie ambiguite, geree par le mecanisme DOUBLON_PAMF (cf.
# services_rapprochement_om.lancer_rapprochement_om) plutot que par une agregation SQL.
# Meme correctif que REQUETE_PAMF (MVOLA) ci-dessus : mc.Status != 3 n'exclut pas a lui seul un
# mouvement de compte reel, cf. le commentaire MouvementsCompte au-dessus de REQUETE_PAMF. La CTE
# est partagee par les 2 branches de l'UNION ALL (portee sur l'ensemble de l'instruction). Pour la
# branche 303 agregee, un posting individuel compte comme reussi (Status = 3 ou mouvement reel)
# avant le min() par groupe - la regle "succes ssi tous les postings ont reussi" est inchangee.
# Meme correctif rMerchantID/apiServiceId corrompus que REQUETE_PAMF (MVOLA) ci-dessus (cf. son
# commentaire), applique aux 2 branches pour le merchant (mc.rMerchantID en repli) et a la seule
# branche 303 pour le service (RequestURL like '%loanRepaymentByAlias%' en repli) - la branche
# 302/700 n'a pas besoin de ce repli (aucun cas constate) et ne doit pas le recevoir : un repli
# large sur apiServiceId y creerait un doublon avec la ligne deja captee par la branche 303.
REQUETE_PAMF_OM = """
with MouvementsCompte as (
  select distinct rAutoTransactionID
  from cbs.dbo.accAccountTransaction
  where postingDate = ? and debitCredit = -1
    and rTransactionTypeID in (1511, 1512, 1613, 1328, 1329)
  union
  select distinct rAutoTransactionID
  from cbs.dbo.loLoanCredit
  where postingDate = ?
)
select
  min(mc.rAutotransactionID) as rAutotransactionID,
  isnull(min(mc.postingDate), cast(min(al.RequestDateCreated) as date)) as postingDate,
  min(mc.Time) as Time,
  stuff((
    select '; ' + mc2.Note
    from cbs.dbo.mcTransaction mc2
    where mc2.requestID = al.apiLogID and mc2.rMerchantID = 9
    order by mc2.rAutotransactionID
    for xml path('')
  ), 1, 2, '') as Note,
  al.RequestID as TRANSID_ORANGE_MONEY,
  min(al.responseBody) as responseBody,
  al.apiServiceId as apiservice,
  max(al.RequestURL) as path,
  max(al.requestBody) as body,
  sum(mc.AmountCRY) as Amount,
  case when min(case when mc.Status = 3 or mvt.rAutoTransactionID is not null then 1 else 0 end) = 1
    then 1 else 0 end as is_sucess
from bagsPAMF_CBS_MC.dbo.apiLog al
left join cbs.dbo.mcTransaction mc on mc.requestID = al.apiLogID and mc.rMerchantID = 9
left join MouvementsCompte mvt on mvt.rAutoTransactionID = mc.rAutotransactionID
where (al.rMerchantID = 9 or mc.rMerchantID = 9)
  and (al.apiServiceId = 303 or al.RequestURL like '%/loanRepaymentByAlias/%')
  and cast(al.RequestDateCreated as date) = ?
group by al.apiLogID, al.RequestID, al.apiServiceId

union all

select
  mc.rAutotransactionID,
  isnull(mc.postingDate, cast(al.RequestDateCreated as date)) as postingDate,
  mc.Time,
  mc.Note,
  al.RequestID as TRANSID_ORANGE_MONEY,
  al.responseBody,
  al.apiServiceId as apiservice,
  al.RequestURL as path,
  al.requestBody as body,
  mc.AmountCRY as Amount,
  case when mc.Status = 3 or mvt.rAutoTransactionID is not null then 1 else 0 end as is_sucess
from bagsPAMF_CBS_MC.dbo.apiLog al
left join cbs.dbo.mcTransaction mc on mc.requestID = al.apiLogID and mc.rMerchantID = 9
left join MouvementsCompte mvt on mvt.rAutoTransactionID = mc.rAutotransactionID
where (al.rMerchantID = 9 or mc.rMerchantID = 9) and al.apiServiceId in (302, 700) and cast(al.RequestDateCreated as date) = ?
"""

REQUETE_DERNIERE_ACTIVITE = """
select top 1 RequestDateCreated
from bagsPAMF_CBS_MC.dbo.apiLog
order by apiLogID desc
"""


def get_connection():
    driver = 'SQL Server' if platform.system() == 'Windows' else 'ODBC Driver 17 for SQL Server'
    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={settings.CBS_DB_SERVER};"
        f"DATABASE={settings.CBS_DB_NAME};"
        f"UID={settings.CBS_DB_UID};"
        f"PWD={settings.CBS_DB_PWD};"
    )
    return pyodbc.connect(connection_string)


def fetch_transactions_pamf(date_requete):
    """Execute la requete de reference pour une date donnee. Retourne une liste de dicts.

    REQUETE_PAMF attend le parametre de date 3 fois : 2 fois pour la CTE MouvementsCompte
    (accAccountTransaction, puis loLoanCredit) et une fois pour le where principal.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        # Le driver ODBC 'SQL Server' (legacy, utilise sur les postes Windows) ne sait pas
        # binder un objet date via SQLBindParameter : on passe une chaine ISO, castee
        # implicitement par SQL Server.
        date_iso = date_requete.isoformat()
        cursor.execute(REQUETE_PAMF, date_iso, date_iso, date_iso)
        colonnes = [c[0] for c in cursor.description]
        return [dict(zip(colonnes, row)) for row in cursor.fetchall()]


def fetch_transactions_pamf_om(date_requete):
    """Execute la requete CBS Orange Money (rMerchantID=9) pour une date donnee. Retourne une
    liste de dicts.

    REQUETE_PAMF_OM attend le parametre de date 4 fois : 2 fois pour la CTE MouvementsCompte
    (partagee par les 2 branches de l'UNION ALL), puis une fois par branche (agregation
    apiServiceId=303, puis 302/700 tels quels).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        date_iso = date_requete.isoformat()
        cursor.execute(REQUETE_PAMF_OM, date_iso, date_iso, date_iso, date_iso)
        colonnes = [c[0] for c in cursor.description]
        return [dict(zip(colonnes, row)) for row in cursor.fetchall()]


def fetch_derniere_activite():
    """Horodatage (naif, heure serveur CBS) de la derniere ligne loggee dans apiLog, tous
    marchands/dates confondus. Retourne None si la table est vide."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(REQUETE_DERNIERE_ACTIVITE)
        row = cursor.fetchone()
        return row[0] if row else None
