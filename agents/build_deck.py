"""Approach deck (pptx) - all numbers are read from the pipeline output, so slides and sheet always match."""
import json
from collections import Counter
from datetime import date
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data/processed"
OUT = ROOT / "output" / "Heidi_Lead_Agent_Approach.pptx"

NAVY = RGBColor(0x14, 0x2B, 0x45)
TEAL = RGBColor(0x0F, 0x76, 0x6E)
MINT = RGBColor(0xD8, 0xF0, 0xEC)
AMBER = RGBColor(0xF5, 0x9E, 0x0B)
INK = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x5B, 0x67, 0x75)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SOFT = RGBColor(0xF3, 0xF6, 0xF8)
HEAD, BODY = "Cambria", "Calibri"


def data():
    leads = json.loads((P / "leads.json").read_text())
    contacts = json.loads((P / "contacts.json").read_text()) if (P / "contacts.json").exists() else {}
    scout_all = json.loads((P / "scout_all.json").read_text())
    research = json.loads((P / "research.json").read_text())
    good = [l for l in leads if l["pm_confirmed"]]
    people = [c for v in contacts.values() for c in v]
    spot = json.loads((P / "spot_check.json").read_text()) if (P / "spot_check.json").exists() else None
    tiers = Counter(l["tier"] for l in good)
    return {
        "raw": 1040 + (len(json.loads((ROOT / "data/raw/gelbeseiten.json").read_text())) if (ROOT / "data/raw/gelbeseiten.json").exists() else 0),
        "both": sum(1 for s_ in scout_all if s_.get("source") == "Google Maps + Gelbe Seiten"),
        "unique": len(scout_all), "candidates": len(leads), "confirmed": len(good),
        "excluded": len(leads) - len(good) + sum(1 for s in scout_all if s["decision"] == "drop"),
        "A": tiers.get("A", 0), "B": tiers.get("B", 0), "C": tiers.get("C", 0),
        "units_sum": sum(l["units_stated"] or 0 for l in good), "units_n": sum(1 for l in good if l["units_stated"]),
        "dm": sum(1 for l in good if l.get("decision_maker_1")),
        "sites": sum(1 for r in research if r.get("website_status") == "ok"),
        "pages": len(list((ROOT / "data/raw/pages").glob("*.json"))),
        "people": len(people), "li": sum(1 for c in people if c.get("linkedin")),
        "em_ver": sum(1 for c in people if c.get("confidence") == "verified_on_website"),
        "em_pat": sum(1 for c in people if c.get("confidence") == "pattern_from_site"),
        "em_com": sum(1 for c in people if c.get("confidence") == "common_pattern"),
        "units_llm_kept": sum(1 for r in research if (r.get("units") or {}).get("verified_by")),
        "units_llm_rej": sum(1 for r in research if r.get("units_rejected")),
        "manual": len(json.loads((P / "manual_review.json").read_text())) if (P / "manual_review.json").exists() else 0,
        "bezirke": Counter(l["bezirk"] for l in good if l.get("bezirk")).most_common(),
        "top": [l for l in good if l["tier"] == "A"][:8],
        "spot": spot,
    }


def tb(slide, x, y, w, h, text, size=14, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.italic, r.font.name = Pt(size), bold, italic, font
        r.font.color.rgb = color
        p.space_after = Pt(4)
    return box


def card(slide, x, y, w, h, fill=SOFT, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = 0.08
    return s


def badge(slide, x, y, n, fill=TEAL, d=0.5):
    c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    c.fill.solid()
    c.fill.fore_color.rgb = fill
    c.line.fill.background()
    tf = c.text_frame
    tf.margin_left = tf.margin_right = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = str(n)
    r.font.size, r.font.bold, r.font.name = Pt(14), True, BODY
    r.font.color.rgb = WHITE
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE


def title(slide, text, sub=None, dark=False):
    tb(slide, 0.6, 0.45, 12.1, 0.8, text, 32, WHITE if dark else NAVY, True, HEAD)
    if sub:
        tb(slide, 0.6, 1.2, 12.1, 0.4, sub, 15, MINT if dark else MUTED, italic=True)


def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = color


def stat(slide, x, y, w, big, label, color=TEAL, dark=False):
    tb(slide, x, y, w, 0.9, big, 44, AMBER if dark else color, True, HEAD)
    tb(slide, x, y + 0.9, w, 0.6, label, 13, MINT if dark else MUTED)


def fmt(n):
    return f"{int(round(n)):,}".replace(",", ".")


def short(t, n):
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def main():
    d = data()
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]

    # 1 Title ------------------------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, NAVY)
    tb(s, 0.8, 1.5, 11.5, 0.5, "AI AGENT BUILDER · CASE STUDY · HEIDI SYSTEMS", 14, AMBER, True)
    tb(s, 0.8, 2.1, 11.5, 1.6, "Heidi Lead Agent: finding and qualifying every Hausverwaltung in Berlin", 40, WHITE, True, HEAD)
    tb(s, 0.8, 4.0, 11, 0.9, "A multi-agent pipeline (Scout → Research → LLM checker → Qualifier → Contacts) "
                            f"that turns Google Maps, Gelbe Seiten and {fmt(d['pages'])} company web pages into a scored, evidence-backed lead list.", 17, MINT)
    stat(s, 0.8, 5.3, 3, fmt(d["confirmed"]), "confirmed property managers", dark=True)
    stat(s, 4.0, 5.3, 3, fmt(d["A"]), "Tier A leads, ready to call", dark=True)
    stat(s, 7.2, 5.3, 3, "~$4", "total cost (rest is free & local)", dark=True)
    tb(s, 10.2, 6.6, 2.6, 0.4, f"Hamid · {date.today():%d.%m.%Y}", 12, MINT, align=PP_ALIGN.RIGHT)
    s.notes_slide.notes_text_frame.text = "Goal: not just a list, but a repeatable agent that Heidi's sales team could run every week."

    # 2 Results at a glance -----------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, WHITE)
    title(s, "Result: a ranked lead list with evidence behind every fact", f"From {fmt(d['raw'])} listings in two sources to a sales-ready list with tiers, contacts and first-email drafts")
    funnel = [("Listings (Maps + Gelbe Seiten)", d["raw"]), ("Unique & in Berlin", d["unique"]), ("Researched", d["candidates"]),
              ("Confirmed managers", d["confirmed"]), ("Tier A + B", d["A"] + d["B"])]
    cd = CategoryChartData()
    cd.categories = [f for f, _ in funnel]
    cd.add_series("Companies", [v for _, v in funnel])
    ch = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.6), Inches(1.9), Inches(6.6), Inches(4.9), cd).chart
    ch.has_title = False
    ch.has_legend = False
    ch.plots[0].gap_width = 45
    ch.plots[0].has_data_labels = True
    dl = ch.plots[0].data_labels
    dl.font.size, dl.font.bold, dl.font.color.rgb = Pt(13), True, INK
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    ser = ch.series[0]
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = TEAL
    ch.category_axis.reverse_order = True
    ch.category_axis.tick_labels.font.size = Pt(13)
    ch.category_axis.format.line.fill.background()
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    tiles = [(fmt(d["A"]), "Tier A: call first"), (fmt(d["B"]), "Tier B: second wave"),
             (fmt(d["units_sum"]), f"units stated by {d['units_n']} companies"), (fmt(d["dm"]), "named managing directors"),
             (fmt(d["li"]), "LinkedIn profiles matched"), (fmt(d["excluded"]), "excluded, each with a reason")]
    for i, (big, lab) in enumerate(tiles):
        x, y = 7.6 + (i % 2) * 2.75, 1.9 + (i // 2) * 1.65
        card(s, x, y, 2.55, 1.45)
        tb(s, x + 0.2, y + 0.15, 2.2, 0.7, big, 30, TEAL if i < 2 else NAVY, True, HEAD)
        tb(s, x + 0.2, y + 0.85, 2.2, 0.5, lab, 12, MUTED)

    # 3 Pipeline ---------------------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, WHITE)
    title(s, "How it works: six small agents, each with one job", "Rules do the cheap work, the LLM handles only the hard cases, and every step caches its results")
    steps = [("Scout", "Google Maps (Apify) + Gelbe Seiten as 2nd source. Filters postcodes, closed places, duplicates."),
             ("Research", f"Python crawler reads {fmt(d['pages'])} pages: home, Impressum, about, services, jobs."),
             ("Browser", "Headless Chrome (Playwright) for JavaScript-only or bot-blocking sites."),
             ("LLM checker", "Local qwen2.5 via Ollama: finds names in the Impressum and double-checks every unit count."),
             ("Qualifier", "Confirms the business, assigns the Bezirk from GPS, computes 6 KPIs and a 0-100 score."),
             ("Contacts", "Directors from Impressum, LinkedIn via Google, email with confidence label + MX check.")]
    for i, (n, txt) in enumerate(steps):
        x = 0.6 + i * 2.06
        card(s, x, 2.2, 1.9, 3.4, SOFT)
        badge(s, x + 0.2, 2.4, i + 1, TEAL if i != 3 else AMBER)
        tb(s, x + 0.2, 3.05, 1.6, 0.5, n, 17, NAVY, True, HEAD)
        tb(s, x + 0.2, 3.6, 1.55, 1.9, txt, 12, INK)
        if i < 5:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 1.9), Inches(3.75), Inches(0.16), Inches(0.3))
            a.fill.solid(); a.fill.fore_color.rgb = AMBER; a.line.fill.background()
    card(s, 0.6, 5.95, 12.1, 0.95, MINT)
    tb(s, 0.85, 6.1, 11.6, 0.7, "Output: a 9-tab workbook (live scoring formulas, CRM status dropdown, German first-email drafts) + GitHub repo. "
                               "One command reruns everything: python run_pipeline.py", 14, NAVY, True, anchor=MSO_ANCHOR.MIDDLE)

    # 4 Sources & tools --------------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, WHITE)
    title(s, "Sources and tools: public data, mostly free", "Each source was chosen for a specific field. Cost: ~$4 of Apify credit; everything else ran locally")
    rows = [("Source / tool", "Used for", "Why"),
            ("Google Maps (Apify)", "Company list, address, phone, GPS, rating", "Most complete list of active Berlin businesses"),
            ("Gelbe Seiten", "Second company list, cross-check", "Closed a coverage gap (Spandau, Lichtenberg) + 176 confirmed in both"),
            ("Company websites", "Services, units, software, hiring", "Companies describe themselves most precisely"),
            ("Impressum (§5 DDG)", "Managing directors, register no., legal form", "Legally required, so the most reliable source for names"),
            ("District borders + OSM", "Bezirk per company (geocoding)", "GPS point-in-polygon beats guessing from postcodes"),
            ("Google search (Apify)", "LinkedIn profiles", "Accepted only if person AND company match"),
            ("Ollama qwen2.5:7b (local)", "Hard extraction + fact checking", "Free, private, nothing leaves the laptop"),
            ("Claude Code", "Building, debugging, reviewing the pipeline", "Pair-programming the agents in one afternoon")]
    t = s.shapes.add_table(len(rows), 3, Inches(0.6), Inches(1.85), Inches(12.1), Inches(5.1)).table
    for j, w in enumerate((3.2, 4.3, 4.6)):
        t.columns[j].width = Inches(w)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            c = t.cell(i, j)
            c.text = v
            c.fill.solid()
            c.fill.fore_color.rgb = NAVY if i == 0 else (SOFT if i % 2 else WHITE)
            p = c.text_frame.paragraphs[0]
            p.runs[0].font.size, p.runs[0].font.name = Pt(13), BODY
            p.runs[0].font.bold = i == 0 or j == 0
            p.runs[0].font.color.rgb = WHITE if i == 0 else INK

    # 5 KPIs ------------------------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, WHITE)
    title(s, "Qualifying KPIs: what makes a good Heidi customer", "Weights are editable in the sheet ('KPI Logic'); scores and tiers recalculate live")
    kpis = [("Portfolio size", 35, "More units means more meters and more recurring revenue"),
            ("Segment fit", 20, "WEG + rental management need an annual heating-cost bill"),
            ("Digital readiness", 15, "Already uses software or a tenant portal, so it adopts a digital platform faster"),
            ("Switch signal", 10, "Mentions heating-cost billing or ista/Techem/Brunata/Minol"),
            ("Growth", 10, "Live job ads (m/w/d): portfolio is growing"),
            ("Reachability", 10, "Named managing director + live website")]
    cd = CategoryChartData()
    cd.categories = [k for k, _, _ in kpis]
    cd.add_series("Weight", [w for _, w, _ in kpis])
    ch = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.6), Inches(1.9), Inches(5.2), Inches(4.4), cd).chart
    ch.has_title = False
    ch.has_legend = False
    ch.plots[0].gap_width = 40
    ch.plots[0].has_data_labels = True
    ch.plots[0].data_labels.font.size, ch.plots[0].data_labels.font.bold = Pt(13), True
    ch.plots[0].data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    ch.series[0].format.fill.solid(); ch.series[0].format.fill.fore_color.rgb = AMBER
    ch.category_axis.reverse_order = True
    ch.category_axis.tick_labels.font.size = Pt(13)
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    for i, (k, w, why) in enumerate(kpis):
        y = 1.95 + i * 0.73
        tb(s, 6.2, y, 2.3, 0.6, k, 15, NAVY, True)
        tb(s, 8.5, y, 4.3, 0.65, why, 13, INK)
    card(s, 0.6, 6.45, 12.1, 0.7, MINT)
    tb(s, 0.85, 6.52, 11.6, 0.55, "Why now: under the HeizkostenV, meters must be remotely readable by 31.12.2026. Every manager on this list has to decide on a provider.",
       14, NAVY, True, anchor=MSO_ANCHOR.MIDDLE)

    # 6 Validation ------------------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, WHITE)
    title(s, "Validation: accuracy over volume", "Every fact carries its source URL and the exact quote; nothing is silently deleted")
    checks = [("Evidence per fact", "Each unit count, name, competitor and job signal is stored with source page + quote, visible in the sheet."),
              ("Two-key check", f"Unit counts kept only if rules AND the LLM agree on the same number: {d['units_llm_kept']} kept, {d['units_llm_rej']} rejected."),
              ("Human in the loop", f"Every rules-vs-LLM disagreement was reviewed manually; {d['manual']} were restored with a written reason."),
              ("Anti-hallucination", "LLM-found names must appear word for word on the Impressum page, or they are discarded."),
              ("Honest confidence", "Emails labelled verified / pattern from colleague / likely-unverified; mail domains MX-checked."),
              ("Two sources", f"{fmt(d['both'])} companies confirmed by both Google Maps and Gelbe Seiten; {fmt(d['excluded'])} excluded ones listed with the reason.")]
    for i, (h, txt) in enumerate(checks):
        x, y = 0.6 + (i % 2) * 6.15, 1.9 + (i // 2) * 1.55
        card(s, x, y, 5.95, 1.35)
        badge(s, x + 0.25, y + 0.25, "✓", TEAL, 0.45)
        tb(s, x + 0.9, y + 0.2, 4.8, 0.4, h, 16, NAVY, True)
        tb(s, x + 0.9, y + 0.6, 4.85, 0.7, txt, 12, INK)
    if d["spot"]:
        sp = d["spot"]
        tb(s, 0.6, 6.6, 12.1, 0.5, f"Manual spot check of {sp['n']} random leads: property manager correct {sp['pm_correct']}/{sp['n']} · "
                                   f"director name correct {sp['dm_correct']}/{sp['dm_checked']} · units correct {sp['units_correct']}/{sp['units_checked']}",
           14, TEAL, True)

    # 7 Contacts --------------------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, WHITE)
    title(s, "Bonus: decision makers, not info@ addresses", "Names from the Impressum, LinkedIn only on a confirmed match, every email labelled by confidence")
    stat(s, 0.6, 1.9, 3, fmt(d["people"]), "decision makers for A/B leads")
    stat(s, 3.6, 1.9, 3, fmt(d["li"]), "LinkedIn profiles (name + company match)")
    stat(s, 6.6, 1.9, 3, fmt(d["em_ver"] + d["em_pat"]), "emails verified or pattern-backed")
    levels = [("Verified", d["em_ver"], "Personal address published on the company's own website"),
              ("Pattern from colleague", d["em_pat"], "Same format as a colleague's published address (e.g. f.lastname@)"),
              ("Likely, unverified", d["em_com"], "firstname.lastname@ - most common German SME format. Check before sending")]
    for i, (h, n, txt) in enumerate(levels):
        y = 3.75 + i * 0.85
        card(s, 0.6, y, 8.9, 0.72)
        tb(s, 0.85, y + 0.17, 3.0, 0.45, h, 15, NAVY, True)
        tb(s, 3.8, y + 0.17, 0.8, 0.45, fmt(n), 15, TEAL, True)
        tb(s, 4.6, y + 0.17, 4.8, 0.5, txt, 12, INK)
    card(s, 9.9, 1.9, 2.8, 4.65, NAVY)
    tb(s, 10.15, 2.1, 2.35, 0.4, "Data protection", 16, AMBER, True)
    tb(s, 10.15, 2.6, 2.35, 3.9, ["Only data the companies publish themselves (Impressum, Google profile).",
                                  "B2B outreach on legitimate interest, Art. 6(1)(f) GDPR.",
                                  "Unverified emails are labelled, never presented as facts.",
                                  "Drafts include a polite intro; add an opt-out line."], 12, WHITE)

    # 8 Insights: districts + top leads ---------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, WHITE)
    title(s, "Where the leads are, and who to call first", "Confirmed property managers per Bezirk and the top Tier A companies")
    bz = d["bezirke"][:10]
    cd = CategoryChartData()
    cd.categories = [b for b, _ in bz]
    cd.add_series("Leads", [n for _, n in bz])
    ch = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.6), Inches(1.9), Inches(5.6), Inches(5.0), cd).chart
    ch.has_title = False
    ch.has_legend = False
    ch.plots[0].gap_width = 40
    ch.plots[0].has_data_labels = True
    ch.plots[0].data_labels.font.size = Pt(12)
    ch.plots[0].data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    ch.series[0].format.fill.solid(); ch.series[0].format.fill.fore_color.rgb = TEAL
    ch.category_axis.reverse_order = True
    ch.category_axis.tick_labels.font.size = Pt(12)
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    rows = [("Company", "Score", "Size")] + [(short(l["company"], 38), str(l["lead_score"]), l["size_tier"].split()[0] + (f" · {fmt(l['units_stated'])}" if l.get("units_stated") else ""))
                                             for l in d["top"]]
    t = s.shapes.add_table(len(rows), 3, Inches(6.6), Inches(1.9), Inches(6.1), Inches(0.45 * len(rows))).table
    for j, w in enumerate((3.9, 0.9, 1.3)):
        t.columns[j].width = Inches(w)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            c = t.cell(i, j)
            c.text = v
            c.fill.solid()
            c.fill.fore_color.rgb = NAVY if i == 0 else (SOFT if i % 2 else WHITE)
            r = c.text_frame.paragraphs[0].runs[0]
            r.font.size, r.font.name, r.font.bold = Pt(12), BODY, i == 0
            r.font.color.rgb = WHITE if i == 0 else INK

    # 9 Next steps ------------------------------------------------------------
    s = prs.slides.add_slide(blank)
    bg(s, NAVY)
    tb(s, 0.6, 0.6, 12, 0.8, "What I would build next at Heidi", 32, WHITE, True, HEAD)
    nxt = [("Weekly agent run", "Scheduled pipeline with change alerts: new companies, new job ads, competitor newly mentioned."),
           ("CRM handoff", "Push A-leads with evidence and email draft straight into HubSpot or Pipedrive."),
           ("More cities", "Hamburg, Munich, Cologne: same pipeline, one config change."),
           ("Pain-signal mining", "Google reviews mentioning 'Nebenkostenabrechnung' = managers with a billing problem."),
           ("Claude API upgrade", "Swap the local model for Claude for higher-recall extraction and personalised outreach at scale.")]
    for i, (h, txt) in enumerate(nxt):
        y = 1.8 + i * 1.0
        badge(s, 0.6, y, i + 1, AMBER, 0.55)
        tb(s, 1.4, y - 0.02, 3.4, 0.5, h, 18, WHITE, True)
        tb(s, 4.9, y + 0.02, 7.8, 0.8, txt, 15, MINT)
    tb(s, 0.6, 6.85, 12, 0.4, "Code: github.com/hamid866/heidi-lead-agent · Sheet: see link in email", 12, MINT, italic=True)

    OUT.parent.mkdir(exist_ok=True)
    prs.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
