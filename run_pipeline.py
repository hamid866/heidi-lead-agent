"""Heidi Lead Agent - run the whole pipeline with one command.

    python run_pipeline.py <apify_dataset_id> [...]

Steps: Scout -> Directory (2nd source) -> Scout merge -> Research -> Browser (JS sites) -> Research again -> LLM (names + unit check)
       -> Qualifier -> Contacts -> Excel workbook
Every step caches its work, so re-runs are fast and cheap.
"""
import subprocess
import sys
import time

PY = sys.executable
STEPS = [
    ("Scout: download, filter, dedupe Google Maps results", ["agents/scout.py", *sys.argv[1:]]),
    ("Directory: Gelbe Seiten as second source + geocoding", ["agents/directory.py"]),
    ("Scout: merge both sources", ["agents/scout.py", *sys.argv[1:]]),
    ("Research: crawl websites + Impressum", ["agents/research.py"]),
    ("Browser: render JavaScript / blocked sites", ["agents/browser_fetch.py"]),
    ("Research: re-read with rendered pages", ["agents/research.py"]),
    ("LLM: Impressum names + verify unit counts (local Ollama)", ["agents/llm_extract.py"]),
    ("Qualifier: confirm, district, KPIs, score", ["agents/qualify.py"]),
    ("Contacts: LinkedIn + email for A/B leads", ["agents/run_contacts.py"]),
    ("Qualifier: refresh", ["agents/qualify.py"]),
    ("Build Excel workbook", ["agents/build_sheet.py"]),
    ("Build approach deck", ["agents/build_deck.py"]),
]

if __name__ == "__main__":
    t0 = time.time()
    for i, (name, cmd) in enumerate(STEPS, 1):
        print(f"\n=== [{i}/{len(STEPS)}] {name}")
        s = time.time()
        subprocess.run([PY, *cmd], check=True)
        print(f"    done in {time.time() - s:.0f}s")
    print(f"\nPipeline finished in {(time.time() - t0) / 60:.1f} min -> output/Heidi_Berlin_Hausverwaltungen_Leads.xlsx")
