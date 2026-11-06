# Heidi Lead Agent 🏢⚡

A small multi-agent pipeline that finds and qualifies **property management companies (Hausverwaltungen) in Berlin** as leads for a metering service provider. Built for the Heidi Systems *AI Agent Builder* case study.

It runs **end-to-end for about $5** of Apify credit (Google Maps + Google search). Everything else is free: Python, Gelbe Seiten, OpenStreetMap, a **local LLM via Ollama** and DNS checks.

```
Scout + Directory ─► Research ─► Browser ─► LLM checker ─► Qualifier ─► Contacts ─► Excel / Google Sheet
(Google Maps,        (websites,  (JS sites) (Impressum     (KPIs,       (LinkedIn,
 Gelbe Seiten)        Impressum)             names, unit    score,       email +
                                             check)         Bezirk)      confidence)
```

**Live dashboard:** https://hamid866.github.io/heidi-lead-dashboard/

**Berlin run (Nov 2026):** 1,655 listings → 974 confirmed property managers in all 12 districts → 75 Tier A / 147 Tier B leads, 268 decision makers.

## Why it's built this way
| Principle | How |
|---|---|
| **Accuracy over volume** | Every fact keeps its **source URL + exact quote**. Nothing is shown without evidence. |
| **Rules first, LLM second** | Cheap, deterministic regex does most of the work. The LLM only handles the hard cases, and its output is **verified against the page text** (anti-hallucination). |
| **Two-key check for numbers** | A "units managed" figure is kept only if the rules **and** the LLM agree on the same number. |
| **Honest confidence** | Emails are labelled *verified on website*, *pattern from colleague*, or *likely pattern (unverified)*. |
| **Transparent scoring** | 6 KPIs with weights in the sheet. Change a weight and every score and tier recalculates. |
| **Nothing silently deleted** | Excluded companies are listed with the reason. |

## Agents
| File | Role |
|---|---|
| `agents/scout.py` | Downloads Google Maps results (Apify), merges the second source, keeps Berlin postcodes, removes closed places, dedupes by place ID / domain / phone, classifies keep / review / drop |
| `agents/directory.py` | Second, free source (Gelbe Seiten): closes coverage gaps of the Maps run and cross-checks companies (fuzzy name match); geocodes new addresses with OpenStreetMap |
| `agents/research.py` | Crawls home, Impressum, about, services and careers pages; extracts directors, register no., units, services, competitors (ista, Techem…), software, hiring, associations |
| `agents/browser_fetch.py` | Headless Chrome (Playwright) for JavaScript-only or bot-blocking sites |
| `agents/llm_extract.py` | Local LLM (Ollama `qwen2.5:7b`): Impressum names where rules fail + verifier for unit counts |
| `agents/qualify.py` | Confirms the company is a property manager, assigns the Bezirk (GPS + official borders), scores 0–100, tiers A/B/C |
| `agents/contacts.py` | LinkedIn match (person **and** company must appear), email with confidence label, MX check |
| `agents/build_sheet.py` | 9-tab workbook with live formulas, filters, a sales-status dropdown and German first-email drafts |

## KPIs (why they matter for a metering provider)
1. **Portfolio size (35)**: more units means more meters, which means more recurring revenue
2. **Segment fit (20)**: WEG and rental management need an annual heating-cost bill
3. **Digital readiness (15)**: already uses property software or a tenant portal, so faster adoption
4. **Switch signal (10)**: mentions heating-cost billing or a competitor
5. **Growth (10)**: currently hiring
6. **Reachability (10)**: named decision maker and a live website

## Run it
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
ollama pull qwen2.5:7b
echo "APIFY_TOKEN=..." > .env
.venv/bin/python run_pipeline.py <apify_dataset_id>
```

## Data protection
Uses only business information the companies publish themselves (Impressum duty, §5 DDG) and public Google Maps profiles, for B2B outreach on the basis of legitimate interest (Art. 6(1)(f) GDPR). Unverified email patterns are labelled as such and must be checked before use.

## Next steps (if this went to production)
- Weekly scheduled run with **change alerts**: new companies, new job ads, a competitor newly mentioned
- Same pipeline for Hamburg, Munich and other cities (one config change)
- Push A-leads straight into the CRM (HubSpot / Pipedrive) with the email draft attached
- Mine Google reviews for complaints about *Nebenkostenabrechnung* as a pain signal
