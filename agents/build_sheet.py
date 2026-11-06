"""Build the final Excel workbook (ready to import into Google Sheets).

Tabs: Read Me | Top Leads | All Leads | Contacts | KPI Logic | Districts | Data Quality | Excluded | Sources & Method
Lead Score and Tier are live formulas driven by the editable weights in 'KPI Logic'.
"""
import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data/processed"
OUT = ROOT / "output" / "Heidi_Berlin_Hausverwaltungen_Leads.xlsx"
TODAY = date.today().strftime("%d.%m.%Y")

F = "Arial"
NAVY, TEAL, LIGHT, GREY = "1F3A5F", "0F766E", "EEF4F8", "F5F5F5"
H_FONT = Font(name=F, bold=True, color="FFFFFF", size=10)
H_FILL = PatternFill("solid", fgColor=NAVY)
B_FONT = Font(name=F, size=10)
LINK = Font(name=F, size=10, color="1155CC", underline="single")
THIN = Border(bottom=Side(style="thin", color="DDDDDD"))
TIER_FILL = {"A": "C6EFCE", "B": "FFEB9C", "C": "F4CCCC"}

WEIGHTS = [  # key, label, weight, why it matters
    ("size", "Portfolio size (units managed)", 35,
     "Heidi bills per apartment/meter. More units = more devices, more recurring revenue, bigger deal."),
    ("segment", "Segment fit (WEG / rental management)", 20,
     "WEG and rental properties need an annual heating & water cost bill (HeizkostenV) - exactly Heidi's product."),
    ("switch", "Switch signal (metering / competitor mentioned)", 10,
     "Company talks about heating-cost billing or names ista/Techem/Brunata/Minol -> topic is relevant, a replacement pitch fits."),
    ("digital", "Digital readiness (software, tenant portal)", 15,
     "Companies on casavi/Immoware/portals adopt a digital metering platform faster and value API/real-time data."),
    ("growth", "Growth signal (hiring now)", 10,
     "Open jobs = growing portfolio = new buildings that need metering contracts."),
    ("reach", "Reachability (named decision maker + live website)", 10,
     "Sales can personally address the managing director; a live website shows an active business."),
]


def hdr(ws, row, headers, widths=None):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font, c.fill = H_FONT, H_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[row].height = 32
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[L(i)].width = w


def link(cell, url, text=None):
    if url:
        cell.value = text or url
        cell.hyperlink = url
        cell.font = LINK


def title(ws, text, sub=None):
    ws["A1"] = text
    ws["A1"].font = Font(name=F, bold=True, size=16, color=NAVY)
    if sub:
        ws["A2"] = sub
        ws["A2"].font = Font(name=F, italic=True, size=10, color="666666")


def yes(v):
    return "✓" if v else ""


def email_draft(l, person):
    """Deterministic, fact-based German first email. Only uses verified facts."""
    if l.get("units_stated"):
        opener = (f"laut Ihrer Website betreuen Sie rund {int(l['units_stated']):,} Einheiten".replace(",", ".")
                  + (f" - von Ihrem Büro in Berlin-{l['bezirk']} aus." if l.get("bezirk") else "."))
    else:
        opener = "ich bin auf Ihre Hausverwaltung" + (f" in Berlin-{l['bezirk']}" if l.get("bezirk") else " in Berlin") + " aufmerksam geworden."
    opener = opener[0].upper() + opener[1:]
    extra = []
    if l.get("competitor"):
        extra.append(f"Sie erwähnen {l['competitor']} auf Ihrer Website - viele Verwaltungen nutzen den Wechsel auf "
                     "fernablesbare Geräte, um Anbieter und Kosten neu zu vergleichen.")
    if l.get("software"):
        extra.append(f"Da Sie bereits digital arbeiten ({l['software']}), lassen sich unsere Verbrauchsdaten direkt in Ihre Prozesse einbinden.")
    if l.get("hiring"):
        extra.append("Sie wachsen gerade - wir nehmen Ihrem Team die Ablesung und Abrechnung komplett ab.")
    name = person.get("name") if person else None
    greet = f"Guten Tag {name}," if name else "Guten Tag,"
    return (f"Betreff: Fernablesung & Heizkostenabrechnung für {l['company'][:50]}\n\n{greet}\n\n"
            f"{opener} Nach der HeizkostenV müssen Zähler und Heizkostenverteiler bis Ende 2026 fernablesbar sein - "
            f"inklusive monatlicher Verbrauchsinformation für Ihre Bewohner.\n\n"
            + (" ".join(extra) + "\n\n" if extra else "")
            + "Heidi Systems digitalisiert den kompletten Messdienst: Geräte, Fernablesung, Abrechnung und Echtzeit-Daten "
              "für Verwalter, Eigentümer und Mieter.\n\nHätten Sie nächste Woche 15 Minuten für ein kurzes Gespräch?\n\n"
              "Viele Grüße\n[Name], Heidi Systems")


def main():
    leads = json.loads((P / "leads.json").read_text())
    contacts = json.loads((P / "contacts.json").read_text()) if (P / "contacts.json").exists() else {}
    good = [l for l in leads if l["pm_confirmed"]]
    excl = [l for l in leads if not l["pm_confirmed"]]
    scout_all = json.loads((P / "scout_all.json").read_text())
    dropped = [s for s in scout_all if s["decision"] == "drop"]

    wb = Workbook()
    ws_readme = wb.active
    ws_readme.title = "Read Me"
    ws_top = wb.create_sheet("Top Leads")
    ws = wb.create_sheet("All Leads")
    ws_c = wb.create_sheet("Contacts")
    ws_k = wb.create_sheet("KPI Logic")
    ws_d = wb.create_sheet("Districts")
    ws_q = wb.create_sheet("Data Quality")
    ws_x = wb.create_sheet("Excluded")
    ws_s = wb.create_sheet("Sources & Method")

    # ------------------------------------------------------------------ KPI Logic
    title(ws_k, "KPI Logic & Lead Scoring", "Edit the yellow weights - every Lead Score and Tier in 'All Leads' recalculates automatically.")
    hdr(ws_k, 4, ["#", "KPI", "Weight (points)", "Why it matters for Heidi", "How it is measured"], [5, 44, 16, 80, 70])
    how = {
        "size": "Units stated on the company website (verified by rules + local LLM). If not stated: estimate from building count x15, "
                "or proxy from Google review volume, legal form and number of managing directors (estimates get 80% of points).",
        "segment": "Website mentions WEG-Verwaltung (+50%) and/or Mietverwaltung (+50%). Housing companies/co-ops = 100%.",
        "switch": "Competitor named on website (ista, Techem, Brunata-Metrona, Minol, KALO, Noventic) = 100%; heating-cost billing mentioned = 60%.",
        "digital": "Named property software on website (casavi, Immoware24, Facilioo, Aareon...) = 67%; tenant/owner portal or app = 33%.",
        "growth": "Careers page with a real job ad, i.e. gender tag like (m/w/d) = 100%.",
        "reach": "Managing director named in Impressum = 60%, website reachable = 40%.",
    }
    for i, (k, lab, w, why) in enumerate(WEIGHTS, 1):
        r = 4 + i
        ws_k.cell(r, 1, i)
        ws_k.cell(r, 2, lab).font = Font(name=F, bold=True, size=10)
        c = ws_k.cell(r, 3, w)
        c.fill = PatternFill("solid", fgColor="FFFF00")
        c.font = Font(name=F, color="0000FF", bold=True, size=10)
        ws_k.cell(r, 4, why)
        ws_k.cell(r, 5, how[k])
    ws_k.cell(11, 2, "Total (should be 100)").font = Font(name=F, bold=True)
    ws_k["C11"] = "=SUM(C5:C10)"
    ws_k["C11"].font = Font(name=F, bold=True)
    ws_k.cell(13, 2, "Tier A if score >=").font = Font(name=F, bold=True)
    ws_k.cell(14, 2, "Tier B if score >=").font = Font(name=F, bold=True)
    for r, v in ((13, 60), (14, 40)):
        c = ws_k.cell(r, 3, v)
        c.fill = PatternFill("solid", fgColor="FFFF00")
        c.font = Font(name=F, color="0000FF", bold=True)
    ws_k.cell(15, 2, "Tier C = everything below Tier B")
    ws_k.cell(17, 2, "Hard filter").font = Font(name=F, bold=True)
    ws_k.cell(17, 4, "A company is only scored if it is confirmed as a property manager (website wording or Google category). "
                      "Unconfirmed companies are listed in the 'Excluded' tab with the reason.")
    for row in ws_k.iter_rows(min_row=5, max_row=17):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if not c.font.bold and c.font.color is None:
                c.font = B_FONT

    # ------------------------------------------------------------------ All Leads
    cols = [
        ("Lead ID", 8), ("Company", 34), ("Tier", 6), ("Lead Score", 8), ("Why this score", 34), ("Type", 14),
        ("Bezirk", 18), ("Address", 34), ("PLZ", 7), ("Website", 28), ("Phone", 16), ("General email", 26),
        ("Decision maker 1", 22), ("Role 1", 18), ("Decision maker 2", 22), ("Role 2", 18),
        ("Size tier", 13), ("Units managed (stated)", 11), ("Size basis", 30),
        ("WEG", 6), ("Miet", 6), ("SE", 6), ("Gewerbe", 8),
        ("Metering provider mentioned", 18), ("Software / portal", 20), ("Hiring now", 8), ("Associations", 12),
        ("Google rating", 8), ("Google reviews", 8), ("Legal form", 12), ("Commercial register", 24), ("Founded", 8),
        ("Evidence: units quote", 50), ("Units check", 26), ("Evidence: source page", 28), ("Impressum", 28), ("Listing (Maps / Gelbe Seiten)", 14), ("Found in", 20),
        ("Confirmed property manager because", 32), ("Also listed as (same company)", 28), ("Sales status", 14), ("Sales owner", 12), ("Notes", 24),
        ("f_size", 7), ("f_segment", 7), ("f_switch", 7), ("f_digital", 7), ("f_growth", 7), ("f_reach", 7),
    ]
    idx = {n: i + 1 for i, (n, _) in enumerate(cols)}
    hdr(ws, 1, [c for c, _ in cols], [w for _, w in cols])
    f0 = idx["f_size"]
    for j, (k, *_ ) in enumerate(WEIGHTS):
        ws.cell(1, f0 + j).comment = Comment(f"0-1 factor for '{k}'. Score = sum(factor x weight in KPI Logic).", "Heidi Lead Agent")
        ws.cell(1, f0 + j).fill = PatternFill("solid", fgColor="7F8C8D")
    n = len(good)
    for i, l in enumerate(good, 2):
        lid = f"HV-{i - 1:04d}"
        l["lead_id"] = lid
        vals = {
            "Lead ID": lid, "Company": l["company"], "Type": l["type"], "Bezirk": l.get("bezirk"),
            "Address": l["address"], "PLZ": l.get("postal_code"), "Phone": l.get("phone"),
            "General email": l.get("general_email"),
            "Decision maker 1": l.get("decision_maker_1"), "Role 1": l.get("role_1"),
            "Decision maker 2": l.get("decision_maker_2"), "Role 2": l.get("role_2"),
            "Size tier": l["size_tier"], "Units managed (stated)": l.get("units_stated"), "Size basis": l["size_basis"],
            "WEG": yes(l["svc_weg"]), "Miet": yes(l["svc_miet"]), "SE": yes(l["svc_se"]), "Gewerbe": yes(l["svc_gewerbe"]),
            "Metering provider mentioned": l.get("competitor") or None, "Software / portal": l.get("software") or None,
            "Hiring now": "Yes" if l["hiring"] else None, "Associations": l.get("associations") or None,
            "Google rating": l.get("google_rating"), "Google reviews": l.get("google_reviews"),
            "Legal form": l.get("legal_form"), "Commercial register": l.get("register"), "Founded": l.get("founded"),
            "Evidence: units quote": ("…" + l["units_evidence"] + "…") if l.get("units_evidence") and l.get("units_stated") else None,
            "Units check": l.get("units_check") if l.get("units_stated") else None,
            "Also listed as (same company)": l.get("also_listed_as"),
            "Confirmed property manager because": l["confirmation"], "Sales status": "New",
            "Why this score": l["score_breakdown"],
        }
        for k, v in vals.items():
            c = ws.cell(i, idx[k], v)
            c.font = B_FONT
        link(ws.cell(i, idx["Website"]), l.get("website"))
        if l.get("units_stated"):
            link(ws.cell(i, idx["Evidence: source page"]), l.get("units_source"))
        link(ws.cell(i, idx["Impressum"]), l.get("impressum_url"))
        link(ws.cell(i, idx["Listing (Maps / Gelbe Seiten)"]), l.get("google_maps_url"), "Open listing")
        ws.cell(i, idx["Found in"], l.get("source")).font = B_FONT
        for j, (k, *_ ) in enumerate(WEIGHTS):
            ws.cell(i, f0 + j, l[f"f_{k}"]).font = Font(name=F, size=9, color="7F8C8D")
        fl = [f"{L(f0 + j)}{i}*'KPI Logic'!$C${5 + j}" for j in range(6)]
        ws.cell(i, idx["Lead Score"], f"=ROUND({'+'.join(fl)},0)").font = Font(name=F, bold=True, size=10)
        sc = f"{L(idx['Lead Score'])}{i}"
        ws.cell(i, idx["Tier"], f"=IF({sc}>='KPI Logic'!$C$13,\"A\",IF({sc}>='KPI Logic'!$C$14,\"B\",\"C\"))").font = Font(name=F, bold=True, size=10)
        ws.cell(i, idx["Units managed (stated)"]).number_format = "#,##0"
    last = n + 1
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{L(len(cols))}{last}"
    tier_rng = f"{L(idx['Tier'])}2:{L(idx['Tier'])}{last}"
    for t, col in TIER_FILL.items():
        ws.conditional_formatting.add(tier_rng, CellIsRule(operator="equal", formula=[f'"{t}"'], fill=PatternFill("solid", fgColor=col)))
    dv = DataValidation(type="list", formula1='"New,Contacted,Meeting booked,Offer sent,Won,Lost,Not relevant"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{L(idx['Sales status'])}2:{L(idx['Sales status'])}{last}")
    for r in range(2, last + 1):
        ws.cell(r, idx["Why this score"]).alignment = Alignment(wrap_text=False)
    # column refs used by other tabs
    AL = lambda name: f"'All Leads'!${L(idx[name])}$2:${L(idx[name])}${last}"  # noqa: E731

    # ------------------------------------------------------------------ Contacts
    ccols = [("Lead ID", 8), ("Company", 32), ("Tier (at export)", 8), ("Name", 22), ("Role", 20), ("Email", 30),
             ("Email confidence", 18), ("How the email was found", 44), ("LinkedIn", 40), ("LinkedIn headline", 40),
             ("Source (Impressum)", 32)]
    hdr(ws_c, 1, [c for c, _ in ccols], [w for _, w in ccols])
    r = 2
    conf_label = {"verified_on_website": "✅ Verified (published)", "pattern_from_site": "🟡 Pattern from colleague",
                  "common_pattern": "🟠 Likely pattern (unverified)", "no_mail_server": "❌ No mail server"}
    for l in good:
        for p in contacts.get(l["placeId"], []):
            ws_c.cell(r, 1, l["lead_id"]); ws_c.cell(r, 2, l["company"]); ws_c.cell(r, 3, l["tier"])
            ws_c.cell(r, 4, p["name"]); ws_c.cell(r, 5, p["role"]); ws_c.cell(r, 6, p.get("email"))
            ws_c.cell(r, 7, conf_label.get(p.get("confidence"), p.get("confidence"))); ws_c.cell(r, 8, p.get("how"))
            li = p.get("linkedin") or {}
            link(ws_c.cell(r, 9), li.get("url"))
            ws_c.cell(r, 10, li.get("headline"))
            link(ws_c.cell(r, 11), p.get("source"))
            for cc in range(1, 12):
                if ws_c.cell(r, cc).font != LINK:
                    ws_c.cell(r, cc).font = B_FONT
            r += 1
    ws_c.freeze_panes = "C2"
    ws_c.auto_filter.ref = f"A1:K{max(r - 1, 2)}"
    c_last = r - 1

    # ------------------------------------------------------------------ Top Leads (snapshot)
    top = [l for l in good if l["tier"] == "A"]
    title(ws_top, f"Top Leads - Tier A ({len(top)} companies)",
          f"Snapshot sorted by score on {TODAY}. Each row: who to call, why they fit, and a ready first email (German).")
    tcols = [("Rank", 6), ("Lead ID", 8), ("Company", 32), ("Score", 7), ("Bezirk", 16), ("Size", 13), ("Units", 9),
             ("Services", 16), ("Signals", 34), ("Best contact", 22), ("Role", 18), ("Email", 30), ("Email confidence", 18),
             ("LinkedIn", 30), ("Phone", 16), ("Website", 26), ("Draft first email (German)", 90)]
    hdr(ws_top, 4, [c for c, _ in tcols], [w for _, w in tcols])
    for i, l in enumerate(top, 1):
        r = 4 + i
        ps = contacts.get(l["placeId"], [])
        best = next((p for p in ps if p.get("confidence") == "verified_on_website"), ps[0] if ps else None)
        sig = [s for s in [f"uses {l['competitor']}" if l.get("competitor") else None,
                           f"software: {l['software']}" if l.get("software") else None,
                           "hiring" if l.get("hiring") else None,
                           l.get("associations") and f"member: {l['associations']}"] if s]
        svc = ", ".join(s for s, f in (("WEG", l["svc_weg"]), ("Miet", l["svc_miet"]), ("SE", l["svc_se"])) if f)
        vals = [i, l["lead_id"], l["company"], l["lead_score"], l.get("bezirk"), l["size_tier"], l.get("units_stated"),
                svc, "; ".join(sig), best and best["name"], best and best["role"], best and best.get("email"),
                best and conf_label.get(best.get("confidence")), None, l.get("phone"), None, email_draft(l, best)]
        for j, v in enumerate(vals, 1):
            c = ws_top.cell(r, j, v)
            c.font = B_FONT
            c.alignment = Alignment(wrap_text=j in (9, 17), vertical="top")
        link(ws_top.cell(r, 14), best and (best.get("linkedin") or {}).get("url"))
        link(ws_top.cell(r, 16), l.get("website"))
        ws_top.cell(r, 7).number_format = "#,##0"
        ws_top.row_dimensions[r].height = 150
    ws_top.freeze_panes = "D5"

    # ------------------------------------------------------------------ Districts
    title(ws_d, "Leads by Berlin district (Bezirk)", "Live formulas on 'All Leads'. District assigned from GPS coordinates + official district borders.")
    hdr(ws_d, 4, ["Bezirk", "Leads", "Tier A", "Tier B", "Tier C", "Units stated (sum)", "Avg Google rating", "Share of all leads"],
        [26, 10, 10, 10, 10, 18, 16, 16])
    bez = sorted({l["bezirk"] for l in good if l.get("bezirk")})
    for i, b in enumerate(bez + ["(outside borders / unknown)"], 5):
        ws_d.cell(i, 1, b).font = Font(name=F, bold=True, size=10)
        crit = f'A{i}' if b in bez else '""'
        ws_d.cell(i, 2, f"=COUNTIFS({AL('Bezirk')},{crit})")
        for j, t in enumerate("ABC", 3):
            ws_d.cell(i, j, f'=COUNTIFS({AL("Bezirk")},{crit},{AL("Tier")},"{t}")')
        ws_d.cell(i, 6, f"=SUMIFS({AL('Units managed (stated)')},{AL('Bezirk')},{crit})").number_format = "#,##0"
        ws_d.cell(i, 7, f"=IFERROR(AVERAGEIFS({AL('Google rating')},{AL('Bezirk')},{crit}),\"-\")").number_format = "0.0"
        ws_d.cell(i, 8, f"=IFERROR(B{i}/SUM($B$5:$B${5 + len(bez)}),0)").number_format = "0.0%"
    tr = 6 + len(bez)
    ws_d.cell(tr, 1, "Total").font = Font(name=F, bold=True)
    for j in range(2, 7):
        ws_d.cell(tr, j, f"=SUM({L(j)}5:{L(j)}{tr - 1})").font = Font(name=F, bold=True)
    ws_d.cell(tr, 6).number_format = "#,##0"

    # ------------------------------------------------------------------ Data Quality
    title(ws_q, "Data quality & validation", "Fill rates are live formulas. Every key fact keeps its source page and quote in 'All Leads'.")
    hdr(ws_q, 4, ["Field", "Filled", "Of leads", "Fill rate", "How it was validated"], [34, 10, 10, 10, 100])
    checks = [
        ("Website", "Website", "HTTP check; dead/unreachable sites retried with a real headless browser (Playwright)."),
        ("Phone", "Phone", "From Google Maps business profile."),
        ("Bezirk", "Bezirk", "Point-in-polygon on official Berlin district borders using Google Maps GPS coordinates."),
        ("Decision maker", "Decision maker 1", "Extracted from the legally required Impressum (§5 DDG). Rules first; local LLM only as fallback and every LLM name must appear word-for-word on the page."),
        ("Units managed (stated)", "Units managed (stated)", "Regex with context rules, then a second check by local LLM: kept only if both agree on the same number (rejects 'ab 50 Einheiten', client portfolios, listings)."),
        ("Commercial register", "Commercial register", "HRB/HRA number + court parsed from Impressum."),
        ("Google rating", "Google rating", "From Google Maps."),
        ("Software / portal", "Software / portal", "Keyword match on company website; quote stored."),
        ("Metering provider mentioned", "Metering provider mentioned", "Keyword match (ista, Techem, Brunata, Minol, KALO, Noventic); quote stored."),
    ]
    for i, (lab, col, how_) in enumerate(checks, 5):
        ws_q.cell(i, 1, lab).font = Font(name=F, bold=True, size=10)
        ws_q.cell(i, 2, f"=SUMPRODUCT(--(LEN({AL(col)})>0))")
        ws_q.cell(i, 3, f"=COUNTA({AL('Company')})")
        ws_q.cell(i, 4, f"=IFERROR(B{i}/C{i},0)").number_format = "0%"
        ws_q.cell(i, 5, how_).alignment = Alignment(wrap_text=True)
    r = 6 + len(checks)
    ws_q.cell(r, 1, "Contacts (A/B leads)").font = Font(name=F, bold=True, size=11, color=NAVY)
    for k, (lab, key) in enumerate([("Emails verified (published on website)", "✅ Verified (published)"),
                                     ("Emails from colleague pattern", "🟡 Pattern from colleague"),
                                     ("Emails likely pattern (unverified)", "🟠 Likely pattern (unverified)")], 1):
        ws_q.cell(r + k, 1, lab)
        ws_q.cell(r + k, 2, f"=COUNTIF('Contacts'!$G$2:$G${max(c_last, 2)},\"{key}\")")
    ws_q.cell(r + 4, 1, "LinkedIn profiles matched (name + company)")
    ws_q.cell(r + 4, 2, f"=COUNTA('Contacts'!$I$2:$I${max(c_last, 2)})")
    ws_q.cell(r + 6, 1, "Manual spot check").font = Font(name=F, bold=True, size=11, color=NAVY)
    sc_p = P / "spot_check.json"
    if sc_p.exists():
        sc = json.loads(sc_p.read_text())
        ws_q.cell(r + 7, 1, "Sample size"); ws_q.cell(r + 7, 2, sc["n"])
        ws_q.cell(r + 8, 1, "Company is a property manager - correct"); ws_q.cell(r + 8, 2, sc["pm_correct"])
        ws_q.cell(r + 9, 1, "Decision maker name - correct"); ws_q.cell(r + 9, 2, sc["dm_correct"]); ws_q.cell(r + 9, 3, sc["dm_checked"])
        ws_q.cell(r + 10, 1, "Units figure - correct"); ws_q.cell(r + 10, 2, sc["units_correct"]); ws_q.cell(r + 10, 3, sc["units_checked"])
        ws_q.cell(r + 11, 1, "Notes"); ws_q.cell(r + 11, 5, sc.get("notes", ""))
    for row in ws_q.iter_rows(min_row=5):
        for c in row:
            if c.font.name != F:
                c.font = B_FONT

    # ------------------------------------------------------------------ Excluded
    title(ws_x, "Excluded companies (transparency)", "Found in the search but NOT counted as leads - with the reason. Nothing is silently deleted.")
    hdr(ws_x, 4, ["Company", "Google category", "Reason", "Website", "Address"], [40, 30, 55, 34, 40])
    r = 5
    for l in excl:
        ws_x.cell(r, 1, l["company"]); ws_x.cell(r, 2, l["google_category"]); ws_x.cell(r, 3, l["confirmation"])
        link(ws_x.cell(r, 4), l.get("website")); ws_x.cell(r, 5, l["address"]); r += 1
    for s in dropped:
        ws_x.cell(r, 1, s["title"]); ws_x.cell(r, 2, s.get("categoryName")); ws_x.cell(r, 3, s["decision_reason"])
        link(ws_x.cell(r, 4), s.get("website") if isinstance(s.get("website"), str) else None); ws_x.cell(r, 5, s.get("address")); r += 1
    ws_x.auto_filter.ref = f"A4:E{r - 1}"

    # ------------------------------------------------------------------ Sources & Method
    title(ws_s, "Sources, tools & pipeline")
    rows = [
        ("1. Scout agent", "Google Maps via Apify (compass/crawler-google-places): 'Hausverwaltung', 'Immobilienverwaltung', 'WEG Verwaltung' across Berlin. 1,040 places -> Berlin postcodes 10115-14199, closed places removed, de-duplicated by place ID, website domain and phone."),
        ("1b. Directory agent", "Gelbe Seiten (all Berlin, 3 search terms) as a second, free source: closes coverage gaps of the Maps run (e.g. Spandau, Lichtenberg) and cross-checks companies. New addresses geocoded with OpenStreetMap Nominatim."),
        ("2. Research agent", "Python crawler reads homepage, Impressum, about, services, careers pages of every company website (~4,000 pages). Rule-based extraction; every fact stored with source URL + exact quote."),
        ("3. Browser agent", "Headless Chrome (Playwright) for JavaScript-only or bot-blocking websites."),
        ("4. LLM agent (local, free)", "Ollama + qwen2.5:7b on a laptop, used only where rules fail: reads Impressum names (must appear verbatim) and double-checks every 'units managed' quote."),
        ("5. Qualifier agent", "Confirms property-management business, assigns Bezirk from GPS + official borders, computes 6 KPIs and a 0-100 score (weights editable in 'KPI Logic')."),
        ("6. Contact agent", "Decision makers from Impressum; LinkedIn via web search, accepted only if result shows person AND company; email with confidence label; MX check of the mail domain."),
        ("Data protection", "Only business data published by the companies themselves (Impressum duty, §5 DDG) and public Google Maps profiles. Personal emails marked by confidence; unverified patterns must be checked before outreach. Legitimate interest B2B (Art. 6(1)(f) GDPR); include opt-out in outreach."),
        ("Cost", "Apify ~4 USD (free monthly credit). Everything else free: Python, local LLM, DuckDuckGo search, DNS checks."),
        ("Data as of", TODAY),
        ("Code", "GitHub repo: heidi-lead-agent (re-run anytime: python run_pipeline.py)"),
    ]
    ws_s.column_dimensions["A"].width = 26
    ws_s.column_dimensions["B"].width = 130
    for i, (a, b) in enumerate(rows, 3):
        ws_s.cell(i, 1, a).font = Font(name=F, bold=True, size=10)
        ws_s.cell(i, 2, b).font = B_FONT
        ws_s.cell(i, 2).alignment = Alignment(wrap_text=True, vertical="top")

    # ------------------------------------------------------------------ Read Me
    title(ws_readme, "Berlin Hausverwaltungen - Lead List for Heidi Systems", f"Prepared by Hamid for the AI Agent Builder case study · data as of {TODAY}")
    ws_readme.column_dimensions["A"].width = 38
    ws_readme.column_dimensions["B"].width = 16
    ws_readme.column_dimensions["C"].width = 90
    stats = [
        ("Confirmed property managers / housing companies", f"=COUNTA({AL('Company')})"),
        ("Tier A leads", f'=COUNTIF({AL("Tier")},"A")'),
        ("Tier B leads", f'=COUNTIF({AL("Tier")},"B")'),
        ("Tier C leads", f'=COUNTIF({AL("Tier")},"C")'),
        ("Units under management (stated, sum)", f"=SUM({AL('Units managed (stated)')})"),
        ("Companies with named decision maker", f"=SUMPRODUCT(--(LEN({AL('Decision maker 1')})>0))"),
        ("Contacts with personal email / LinkedIn", f"=COUNTA('Contacts'!$D$2:$D${max(c_last, 2)})"),
        ("Excluded (with reason)", f"=COUNTA('Excluded'!$A$5:$A${max(r - 1, 5)})"),
    ]
    ws_readme["A4"] = "Key numbers"
    ws_readme["A4"].font = Font(name=F, bold=True, size=12, color=NAVY)
    for i, (a, f) in enumerate(stats, 5):
        ws_readme.cell(i, 1, a).font = B_FONT
        c = ws_readme.cell(i, 2, f)
        c.font = Font(name=F, bold=True, size=11, color=TEAL)
        c.number_format = "#,##0"
    g = 5 + len(stats) + 1
    ws_readme.cell(g, 1, "How to use this sheet").font = Font(name=F, bold=True, size=12, color=NAVY)
    guide = [
        ("Top Leads", "Start here: Tier A companies with best contact, signals and a ready German first email."),
        ("All Leads", "Every confirmed company with all KPIs, evidence quotes and links. Filter by Tier, Bezirk, size. 'Sales status' is a dropdown - use it as a mini CRM."),
        ("Contacts", "Decision makers with email confidence (✅ verified / 🟡 pattern from colleague / 🟠 likely, unverified) and matched LinkedIn profiles."),
        ("KPI Logic", "Why each KPI matters and its weight. Change the yellow cells -> scores and tiers update everywhere."),
        ("Districts", "Where the leads and units are in Berlin."),
        ("Data Quality", "Fill rates, validation method per field and manual spot-check results."),
        ("Excluded", "Companies found but excluded, with reasons (no silent deletions)."),
        ("Sources & Method", "Pipeline, tools, cost and data-protection notes."),
    ]
    for i, (a, b) in enumerate(guide, g + 1):
        ws_readme.cell(i, 1, a).font = Font(name=F, bold=True, size=10)
        ws_readme.cell(i, 3, b).font = B_FONT
    h = g + len(guide) + 2
    ws_readme.cell(h, 1, "Why now").font = Font(name=F, bold=True, size=12, color=NAVY)
    ws_readme.cell(h + 1, 1, "HeizkostenV: meters and heat cost allocators must be remotely readable by 31.12.2026, with monthly "
                             "consumption info for residents. Every Berlin property manager has to act now - the strongest reason to call this list today.").font = B_FONT
    ws_readme.cell(h + 1, 1).alignment = Alignment(wrap_text=True)
    ws_readme.merge_cells(start_row=h + 1, start_column=1, end_row=h + 1, end_column=3)
    ws_readme.row_dimensions[h + 1].height = 32
    ws_readme.cell(h + 3, 1, "Legend").font = Font(name=F, bold=True, size=12, color=NAVY)
    for i, (t, col, txt) in enumerate([("A", TIER_FILL["A"], "Best fit - contact first"), ("B", TIER_FILL["B"], "Good fit - second wave"),
                                       ("C", TIER_FILL["C"], "Low priority / small")], h + 4):
        c = ws_readme.cell(i, 1, f"Tier {t}")
        c.fill = PatternFill("solid", fgColor=col)
        c.font = Font(name=F, bold=True)
        ws_readme.cell(i, 3, txt).font = B_FONT

    for wsx in (ws_top, ws_c, ws_x):
        for row in wsx.iter_rows(min_row=2):
            for c in row:
                if c.font.name != F:
                    c.font = B_FONT
    for wsx in wb.worksheets:
        wsx.sheet_view.showGridLines = wsx.title in ("All Leads", "Contacts", "Excluded")
    ws_readme.sheet_properties.tabColor = NAVY
    ws_top.sheet_properties.tabColor = "2E7D32"
    ws.sheet_properties.tabColor = TEAL
    OUT.parent.mkdir(exist_ok=True)
    wb.save(OUT)
    print(f"saved {OUT} | leads {n} | top {len(top)} | contacts rows {c_last - 1} | excluded {r - 5}")


if __name__ == "__main__":
    main()
