#!/usr/bin/env python
"""
Daily PAR dashboard email.
Sends yesterday's situation (J-1) mirroring the par_dashboard page.
Schedule with Windows Task Scheduler or cron.
"""

import platform
import pyodbc
import smtplib
from datetime import date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ════════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════════
SMTP_SERVER = "mail.pamf.mg"
SMTP_PORT   = 25
SENDER      = "noreply@pamf.mg"
RECIPIENTS  = ["m.razakasoa@pamf.mg","s.andriamparany@pamf.mg","d.ravalison@pamf.mg","n.ramiaramananjafy@pamf.mg"]   # ← adapter

PRODUCT     = "DFS M-KAJY (NANO)"
DB_SERVER   = "172.20.24.37"
DB_USER     = "Minonja"
DB_PWD      = "Minonja"


# ════════════════════════════════════════════════════════════
# Database
# ════════════════════════════════════════════════════════════
def _bic_conn():
    driver = 'SQL Server' if platform.system() == 'Windows' else 'ODBC Driver 17 for SQL Server'
    cs = (
        "DRIVER={{{driver}}};SERVER={ip};DATABASE={db};"
        "UID={user};PWD={pwd}"
    ).format(driver=driver, ip=DB_SERVER, db="BIC", user=DB_USER, pwd=DB_PWD)
    return pyodbc.connect(cs)


def _rows(conn, sql, params=()):
    cur  = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ════════════════════════════════════════════════════════════
# Formatting helpers
# ════════════════════════════════════════════════════════════
def _fmt(val):
    if val is None:
        return '—'
    try:
        return f"{float(val):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(val)


def _fmt_pct(val):
    if val is None:
        return '—'
    try:
        return f"{float(val):.2f}%"
    except (TypeError, ValueError):
        return str(val)


def _diff(cur, prev, inverse=False, pct_mode=False):
    # Colors match dashboard CSS vars: --success-color #198754, --danger-color #dc3545
    if cur is None or prev is None:
        return {'color': '#6c757d', 'arrow': '', 'bracket': ''}
    c, p = float(cur), float(prev)
    diff  = c - p
    if diff == 0:
        return {'color': '#6c757d', 'arrow': '', 'bracket': '(±0)'}

    up        = diff > 0
    favorable = (not up) if inverse else up
    color     = '#198754' if favorable else '#dc3545'
    arrow     = '▲' if up else '▼'

    if pct_mode:
        diff_str = f"{diff:+.2f}%"
    else:
        sign     = '+' if up else ''
        diff_str = f"{sign}{_fmt(diff)}"

    return {'color': color, 'arrow': arrow, 'bracket': f"({diff_str})"}


def _row_bg(diff):
    """Very light row tint — readable on white, avoids aggressive color bleed."""
    c = diff.get('color', '')
    if c == '#198754': return '#f0fdf4'
    if c == '#dc3545': return '#fff5f5'
    return '#ffffff'


def _delta_cell(diff):
    """Delta cell content: colored arrow + bracket."""
    if not diff.get('bracket'):
        return '<span style="color:#9e9e9e;">—</span>'
    return (
        f'<span style="font-weight:700;color:{diff["color"]};">'
        f'{diff["arrow"]} {diff["bracket"]}</span>'
    )


# ════════════════════════════════════════════════════════════
# Table row builders — clean report format, border-based
# ════════════════════════════════════════════════════════════
_TD  = 'padding:8px 14px;border:1px solid #dee2e6;font-size:13px;color:#212529;'
_TDR = _TD + 'text-align:right;font-variant-numeric:tabular-nums;'


def _section_hdr(title, colspan=3):
    """Dark navy full-width section separator row."""
    return (
        f'<tr>'
        f'<td colspan="{colspan}" style="background:#1e293b;color:#e2e8f0;'
        f'padding:9px 14px;font-size:11px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:1.2px;border:1px solid #1e293b;">'
        f'&#9632; {title}</td></tr>'
    )


def _col_hdr(d_fr, col1='Indicateur'):
    """Gray column-header row."""
    th = 'padding:7px 14px;border:1px solid #dee2e6;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#6c757d;background:#f1f5f9;'
    return (
        f'<tr>'
        f'<th style="{th}text-align:left;">{col1}</th>'
        f'<th style="{th}text-align:right;">J &mdash; {d_fr}</th>'
        f'<th style="{th}text-align:right;white-space:nowrap;">vs J&#8209;1</th>'
        f'</tr>'
    )


def _data_row(label, value, diff, indent=False):
    """Single data row: label | value | delta."""
    bg  = _row_bg(diff)
    pad = 'padding:7px 14px 7px 28px;' if indent else 'padding:7px 14px;'
    lc  = '#374151' if indent else '#212529'
    fw  = 'font-weight:400;' if indent else 'font-weight:600;'
    return (
        f'<tr style="background:{bg};">'
        f'<td style="{pad}border:1px solid #dee2e6;font-size:13px;{fw}color:{lc};">{label}</td>'
        f'<td style="{_TDR}">{value}</td>'
        f'<td style="{_TDR}">{_delta_cell(diff)}</td>'
        f'</tr>'
    )


def _group_hdr(label, accent_color):
    """Sub-group header row inside a section (PAR 1, PAR 15, …)."""
    return (
        f'<tr style="background:#f8fafc;">'
        f'<td colspan="3" style="padding:6px 14px;border:1px solid #dee2e6;'
        f'border-left:4px solid {accent_color};font-size:12px;font-weight:700;'
        f'color:#374151;letter-spacing:.3px;">{label}</td>'
        f'</tr>'
    )


def _period_hdr(text):
    """Period sub-header inside disb/repay section."""
    return (
        f'<tr style="background:#eff6ff;">'
        f'<td colspan="3" style="padding:7px 14px;border:1px solid #dee2e6;'
        f'font-size:12px;font-weight:600;color:#1d4ed8;">&#128197; {text}</td>'
        f'</tr>'
    )


def _spacer():
    return '<tr><td colspan="3" style="height:14px;background:#f8f9fa;border:none;"></td></tr>'


# ════════════════════════════════════════════════════════════
# Data fetching
# ════════════════════════════════════════════════════════════
def fetch_par(d_str, p_str):
    try:
        conn = _bic_conn()
        rows = _rows(conn, """
            SELECT TOP (2)
                CAST([Date] AS date) AS reportDate,
                [Name] AS Product,
                [Encours],    [Encours_nb],
                [PAR1],       [PAR_nb_1],
                ROUND(([PAR1]  * 100.0) / NULLIF([Encours], 0), 2) AS PAR1_pct,
                [PAR15],      [PAR_nb_15],
                ROUND(([PAR15] * 100.0) / NULLIF([Encours], 0), 2) AS PAR15_pct,
                [PAR30],      [PAR_nb_30],
                ROUND(([PAR30] * 100.0) / NULLIF([Encours], 0), 2) AS PAR30_pct,
                [PAR70],      [PAR_nb_70],
                ROUND(([PAR70] * 100.0) / NULLIF([Encours], 0), 2) AS PAR70_pct,
                [PAR90],      [PAR_nb_90],
                ROUND(([PAR90] * 100.0) / NULLIF([Encours], 0), 2) AS PAR90_pct,
                [WOF_Amount], [WOF_Number],
                [WOF_Amount_cum], [WOF_Number_cum]
            FROM [BIC].[dbo].[DFS_PAR]
            WHERE (CAST([Date] AS date) = ? OR CAST([Date] AS date) = ?)
              AND [Name] = 'DFS M-KAJY (NANO)'
            ORDER BY CAST([Date] AS date) DESC
        """, (d_str, p_str))
        conn.close()
        return (rows[0] if rows else {}), (rows[1] if len(rows) > 1 else {})
    except Exception as e:
        print(f"[PAR] Erreur: {e}")
        return {}, {}


def fetch_disbursements(d_str):
    try:
        conn  = _bic_conn()
        rows  = _rows(conn, """
            SELECT 'Current Month' AS t,
                   SUM(l.LoanAmountCurrent) AS amt, COUNT(*) AS nb
            FROM CBS.dbo.loLoan l
            INNER JOIN CBS.dbo.loProductCondition lpc
                ON lpc.loProductConditionID = l.loProductConditionID
            WHERE lpc.loProductID = 99
              AND MONTH(l.RealDisbursementDate) = MONTH(CONVERT(DATE,?,120))
              AND YEAR(l.RealDisbursementDate)  = YEAR(CONVERT(DATE,?,120))
              AND CAST(l.RealDisbursementDate AS DATE) <= CONVERT(DATE,?,120)
            UNION ALL
            SELECT 'Previous Month Same Date',
                   SUM(l.LoanAmountCurrent), COUNT(*)
            FROM CBS.dbo.loLoan l
            INNER JOIN CBS.dbo.loProductCondition lpc
                ON lpc.loProductConditionID = l.loProductConditionID
            WHERE lpc.loProductID = 99
              AND MONTH(l.RealDisbursementDate) = MONTH(DATEADD(MONTH,-1,CONVERT(DATE,?,120)))
              AND YEAR(l.RealDisbursementDate)  = YEAR(DATEADD(MONTH,-1,CONVERT(DATE,?,120)))
              AND CAST(l.RealDisbursementDate AS DATE) < CONVERT(DATE,?,120)
              AND DAY(CAST(l.RealDisbursementDate AS DATE)) <= DAY(CONVERT(DATE,?,120))
              AND l.Status IN (4,5,10,13)
            UNION ALL
            SELECT 'Current Day', SUM(l.LoanAmountCurrent), COUNT(*)
            FROM CBS.dbo.loLoan l
            INNER JOIN CBS.dbo.loProductCondition lpc
                ON lpc.loProductConditionID = l.loProductConditionID
            WHERE lpc.loProductID = 99
              AND CAST(l.RealDisbursementDate AS DATE) = CONVERT(DATE,?,120)
              AND l.Status IN (4,5,10,13)
            UNION ALL
            SELECT 'Previous Day', SUM(l.LoanAmountCurrent), COUNT(*)
            FROM CBS.dbo.loLoan l
            INNER JOIN CBS.dbo.loProductCondition lpc
                ON lpc.loProductConditionID = l.loProductConditionID
            WHERE lpc.loProductID = 99
              AND CAST(l.RealDisbursementDate AS DATE) = DATEADD(DAY,-1,CONVERT(DATE,?,120))
              AND l.Status IN (4,5,10,13)
        """, (d_str,)*9)
        conn.close()
        return {r['t']: r for r in rows}
    except Exception as e:
        print(f"[Disbursements] Erreur: {e}")
        return {}


def fetch_repayments(d_str):
    try:
        conn  = _bic_conn()
        rows  = _rows(conn, """
            SELECT 'Current Month' AS t,
                   SUM(lc.AmountCry) AS amt, COUNT(*) AS nb
            FROM CBS.dbo.loLoanCredit lc
            INNER JOIN CBS.dbo.loLoan l ON l.loLoanID = lc.loLoanID
            INNER JOIN CBS.dbo.loProductCondition con
                ON con.loProductConditionID = l.loProductConditionID
            WHERE con.loProductID = 99
              AND MONTH(lc.PostingDate) = MONTH(CONVERT(DATE,?,120))
              AND YEAR(lc.PostingDate)  = YEAR(CONVERT(DATE,?,120))
              AND CAST(lc.PostingDate AS DATE) < CONVERT(DATE,?,120)
            UNION ALL
            SELECT 'Previous Month Same Date',
                   SUM(lc.AmountCry), COUNT(*)
            FROM CBS.dbo.loLoanCredit lc
            INNER JOIN CBS.dbo.loLoan l ON l.loLoanID = lc.loLoanID
            INNER JOIN CBS.dbo.loProductCondition con
                ON con.loProductConditionID = l.loProductConditionID
            WHERE con.loProductID = 99
              AND MONTH(lc.PostingDate) = MONTH(DATEADD(MONTH,-1,CONVERT(DATE,?,120)))
              AND YEAR(lc.PostingDate)  = YEAR(DATEADD(MONTH,-1,CONVERT(DATE,?,120)))
              AND DAY(lc.PostingDate) <= DAY(CONVERT(DATE,?,120))
            UNION ALL
            SELECT 'Current Day', SUM(lc.AmountCry), COUNT(*)
            FROM CBS.dbo.loLoanCredit lc
            INNER JOIN CBS.dbo.loLoan l ON l.loLoanID = lc.loLoanID
            INNER JOIN CBS.dbo.loProductCondition con
                ON con.loProductConditionID = l.loProductConditionID
            WHERE con.loProductID = 99
              AND CAST(lc.PostingDate AS DATE) = CONVERT(DATE,?,120)
            UNION ALL
            SELECT 'Previous Day', SUM(lc.AmountCry), COUNT(*)
            FROM CBS.dbo.loLoanCredit lc
            INNER JOIN CBS.dbo.loLoan l ON l.loLoanID = lc.loLoanID
            INNER JOIN CBS.dbo.loProductCondition con
                ON con.loProductConditionID = l.loProductConditionID
            WHERE con.loProductID = 99
              AND CAST(lc.PostingDate AS DATE) = DATEADD(DAY,-1,CONVERT(DATE,?,120))
        """, (d_str,)*8)
        conn.close()
        return {r['t']: r for r in rows}
    except Exception as e:
        print(f"[Remboursements] Erreur: {e}")
        return {}


# ════════════════════════════════════════════════════════════
# Build HTML email body — clean bordered report format
# ════════════════════════════════════════════════════════════
def build_html(selected_date, previous_date):
    d_str = selected_date.strftime('%Y-%m-%d')
    p_str = previous_date.strftime('%Y-%m-%d')
    d_fr  = selected_date.strftime('%d/%m/%Y')
    p_fr  = previous_date.strftime('%d/%m/%Y')

    cur, prv   = fetch_par(d_str, p_str)
    disb_data  = fetch_disbursements(d_str)
    repay_data = fetch_repayments(d_str)

    def g(f): return cur.get(f)
    def p(f): return prv.get(f)

    # ── Build one master report table ──────────────────────
    rows = []

    # ── ENCOURS ────────────────────────────────────────────
    rows.append(_section_hdr('Encours'))
    rows.append(_col_hdr(d_fr))
    rows.append(_data_row('Montant', _fmt(g('Encours')),
                          _diff(g('Encours'),    p('Encours'),    inverse=False)))
    rows.append(_data_row('Nombre de pr&ecirc;ts', _fmt(g('Encours_nb')),
                          _diff(g('Encours_nb'), p('Encours_nb'), inverse=False)))
    rows.append(_spacer())

    # ── PAR ────────────────────────────────────────────────
    rows.append(_section_hdr('Portfolio At Risk (PAR)'))
    rows.append(_col_hdr(d_fr))
    for label, amt_f, nb_f, pct_f in [
        ('PAR 1',  'PAR1',  'PAR_nb_1',  'PAR1_pct'),
        ('PAR 15', 'PAR15', 'PAR_nb_15', 'PAR15_pct'),
        ('PAR 30', 'PAR30', 'PAR_nb_30', 'PAR30_pct'),
        ('PAR 70', 'PAR70', 'PAR_nb_70', 'PAR70_pct'),
        ('PAR 90', 'PAR90', 'PAR_nb_90', 'PAR90_pct'),
    ]:
        pct_d = _diff(g(pct_f), p(pct_f), inverse=True, pct_mode=True)
        amt_d = _diff(g(amt_f), p(amt_f), inverse=True)
        nb_d  = _diff(g(nb_f),  p(nb_f),  inverse=True)
        accent = pct_d.get('color', '#9e9e9e')
        rows.append(_group_hdr(label, accent))
        rows.append(_data_row('% (mnt)', _fmt_pct(g(pct_f)), pct_d, indent=True))
        rows.append(_data_row('Montant',   _fmt(g(amt_f)),     amt_d, indent=True))
        rows.append(_data_row('Nombre',    _fmt(g(nb_f)),      nb_d,  indent=True))
    rows.append(_spacer())

    # ── WOF ────────────────────────────────────────────────
    rows.append(_section_hdr('Write-Off (WOF)'))
    rows.append(_col_hdr(d_fr))
    for label, field in [
        ('Montant',        'WOF_Amount'),
        ('Nombre',         'WOF_Number'),
        ('Montant cumul&eacute;', 'WOF_Amount_cum'),
        ('Nombre cumul&eacute;',  'WOF_Number_cum'),
    ]:
        rows.append(_data_row(label, _fmt(g(field)),
                              _diff(g(field), p(field), inverse=True)))
    rows.append(_spacer())

    # ── DÉCAISSEMENTS & REMBOURSEMENTS ─────────────────────
    rows.append(_section_hdr('D&eacute;caissements &amp; Remboursements'))
    rows.append(_col_hdr(d_fr, col1='Indicateur'))

    for period_lbl, dk_cur, dk_prv, rk_cur, rk_prv in [
        (f'Mois en cours &mdash; vs m&ecirc;me p&eacute;riode mois pr&eacute;c&eacute;dent',
         'Current Month', 'Previous Month Same Date',
         'Current Month', 'Previous Month Same Date'),
        (f'Journ&eacute;e {d_fr} &mdash; vs hier {p_fr}',
         'Current Day', 'Previous Day',
         'Current Day', 'Previous Day'),
    ]:
        dc = disb_data.get(dk_cur,  {})
        dp = disb_data.get(dk_prv,  {})
        rc = repay_data.get(rk_cur, {})
        rp = repay_data.get(rk_prv, {})
        rows.append(_period_hdr(period_lbl))
        rows.append(_data_row('D&eacute;caissements &mdash; Montant',
                              _fmt(dc.get('amt')),
                              _diff(dc.get('amt'), dp.get('amt'), inverse=False)))
        rows.append(_data_row('D&eacute;caissements &mdash; Nombre de pr&ecirc;ts',
                              _fmt(dc.get('nb')),
                              _diff(dc.get('nb'),  dp.get('nb'),  inverse=False)))
        rows.append(_data_row('Remboursements &mdash; Montant',
                              _fmt(rc.get('amt')),
                              _diff(rc.get('amt'), rp.get('amt'), inverse=False)))
        rows.append(_data_row('Remboursements &mdash; Nombre',
                              _fmt(rc.get('nb')),
                              _diff(rc.get('nb'),  rp.get('nb'),  inverse=False)))

    table_body = '\n'.join(rows)

    # ── Assemble full email ─────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Rapport PAR &mdash; {PRODUCT}</title>  <a href="http://192.168.123.97:8776/par-dashboard/" style="color:#0d6efd;text-decoration:underline;"> voir le Dashboard</a>
</head>
<body style="margin:0;padding:20px 12px;background:#e2e8f0;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:680px;margin:0 auto;">

  <!-- ═══ HEADER ═══ -->
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#1a1f2e;border-radius:10px 10px 0 0;">
    <tr>
      <td style="padding:16px 20px;">

        <div style="margin-top:4px;font-size:11px;color:#64748b;">
          Rapport PAR Journalier &mdash; {PRODUCT}
        </div>
      </td>
      <td align="right" style="padding:16px 20px;vertical-align:middle;">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px;">P&eacute;riode analys&eacute;e</div>
        <span style="background:#0d6efd;color:#fff;border-radius:4px;
                     padding:3px 10px;font-size:12px;font-weight:600;">J {d_fr}</span>
        <span style="color:#94a3b8;margin:0 4px;">vs</span>
        <span style="background:#475569;color:#fff;border-radius:4px;
                     padding:3px 10px;font-size:12px;">J&#8209;1 {p_fr}</span>
      </td>
    </tr>
  </table>

  <!-- ═══ LEGEND BAR ═══ -->
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#f8fafc;border:1px solid #dee2e6;border-top:none;">
    <tr>
      <td style="padding:8px 20px;font-size:12px;color:#6c757d;">
        <span style="background:#f0fdf4;color:#15803d;border:1px solid #86efac;
                     border-radius:3px;padding:2px 8px;font-weight:600;margin-right:8px;">
          &#9650; Favorable
        </span>
        <span style="background:#fff5f5;color:#b91c1c;border:1px solid #fca5a5;
                     border-radius:3px;padding:2px 8px;font-weight:600;margin-right:16px;">
          &#9660; D&eacute;favorable
        </span>
        <span style="color:#9e9e9e;font-size:11px;">
          Encours&nbsp;: hausse = favorable &nbsp;|&nbsp;
          PAR &amp; WOF&nbsp;: baisse = favorable
        </span>
      </td>
    </tr>
  </table>

  <!-- ═══ REPORT TABLE ═══ -->
  <table width="100%" cellpadding="0" cellspacing="0"
         style="border-collapse:collapse;background:#ffffff;
                border:1px solid #dee2e6;border-top:none;">
    {table_body}
  </table>

  <!-- ═══ FOOTER ═══ -->
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#f1f5f9;border:1px solid #dee2e6;border-top:none;
                border-radius:0 0 10px 10px;">
    <tr>
      <td style="padding:10px 20px;font-size:11px;color:#94a3b8;">
        Rapport automatique g&eacute;n&eacute;r&eacute; le {date.today().strftime('%d/%m/%Y')}.
        Donn&eacute;es au {d_fr}. PAR&nbsp;% = Montant&nbsp;/ Encours.
      </td>
    </tr>
  </table>

</div>
</body>
</html>"""
    return html


# ════════════════════════════════════════════════════════════
# Email sender
# ════════════════════════════════════════════════════════════
def send_email(subject, recipients, html_body):
    msg            = MIMEMultipart()
    msg['From']    = SENDER
    msg['To']      = ", ".join(recipients)
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.ehlo()
            s.sendmail(SENDER, recipients, msg.as_string())
            print("Email envoyé avec succès.")
    except Exception as e:
        print(f"Erreur envoi mail: {e}")


# ════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════
if __name__ == '__main__':
    selected_date = date.today() - timedelta(days=1)   # J-1
    previous_date = selected_date - timedelta(days=1)  # J-2

    print(f"Génération du rapport pour {selected_date} vs {previous_date}...")

    html    = build_html(selected_date, previous_date)
    subject = (
        f"{selected_date.strftime('%d/%m/%Y')}"
        f"-Situation PAR {PRODUCT}  "
        
    )
    send_email(subject, RECIPIENTS, html)
