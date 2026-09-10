"""Connexion en lecture seule a la base CBS (SQL Server, PAMF). Cf. CLAUDE.md - Source 2."""

import platform

import pyodbc
from django.conf import settings

REQUETE_PAMF = """
select
  mc.rAutotransactionID, mc.postingDate, mc.Time, mc.Note,
  al.RequestID as TRANSID_MVOLA, al.responseBody,
  case when mc.Status = 3 then 1 else 0 end as is_sucess
from cbs.dbo.mcTransaction mc
join bagsPAMF_CBS_MC.dbo.apiLog al on al.apiLogID = mc.requestID
where mc.rMerchantID = 13 and mc.postingDate = ?
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
    """Execute la requete de reference pour une date donnee. Retourne une liste de dicts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Le driver ODBC 'SQL Server' (legacy, utilise sur les postes Windows) ne sait pas
        # binder un objet date via SQLBindParameter : on passe une chaine ISO, castee
        # implicitement par SQL Server.
        cursor.execute(REQUETE_PAMF, date_requete.isoformat())
        colonnes = [c[0] for c in cursor.description]
        return [dict(zip(colonnes, row)) for row in cursor.fetchall()]
