"""
main.py — daily job hunt orchestrator.

Run locally:  python main.py
Run on CI:    triggered by GitHub Actions (.github/workflows/daily.yml)
"""

import json
import os
import sys
from pathlib import Path

from config import MAX_RESULTS, MIN_SCORE
from notifier import add_to_notion, send_email
from scrapers import scrape_all
from scorer import score_jobs

# German words anywhere in the title = German-language role
_GERMAN_TITLE_KEYWORDS = {
    "künstliche", "intelligenz", "entwicklung", "algorithmen",
    "wissenschaft", "kenntnisse", "wissenschaftler", "analytiker",
    "datenanalyse", "maschinelles", "verarbeitung", "forschung",
    "ausbildung", "gestützte", "gestützt", "bereich", "weiterentwicklung",
    "automatisierung", "digitalisierung", "daten", "geschlechter",
    "abschlussarbeit", "projektionsoptiken", "datenerfassung",
    "berichterstattung", "lieferkette", "alle", "statistiken",
}

# If the title contains any of these → almost certainly German-language
_GERMAN_TITLE_FRAGMENTS = (
    "ki-", "-ki", "ki ", " ki ", "künstlich", "entwickl", "daten",
    "gestütz", "automatisier", "digitalisi", "bereich", "geschlecht",
    "abschluss", "statistik",
)

def _no_experience_overload(j: dict) -> bool:
    """Drop jobs that require 3+ years of experience anywhere in the description."""
    import re
    desc_lower = (j.get("description") or "").lower()

    patterns = [
        r"\b([3-9]|\d{2})\+?\s*years?\s*(of\s*)?(professional\s*)?(work\s*)?experience",
        r"\bminimum\s*(of\s*)?([3-9]|\d{2})\s*years?",
        r"\bat\s+least\s+([3-9]|\d{2})\s*years?",
        r"\b([3-9]|\d{2})\s*[-–]\s*\d+\s*years?\s*(of\s*)?experience",
        r"\b([3-9]|\d{2})\+\s*years?",   # catches "5+ years Python"
        r"\bexperience\s*:?\s*([3-9]|\d{2})\+?\s*years?",
    ]
    for pattern in patterns:
        if re.search(pattern, desc_lower):
            return False

    return True


def _not_fulltime_senior(j: dict) -> bool:
    """Drop jobs with senior/lead titles — junior and entry level full-time is fine."""
    title_lower = j["title"].lower()

    senior_titles = ("senior ", "lead ", "head of", "principal ", "staff engineer",
                     "director", "vp ", "vice president", "manager ")
    if any(t in title_lower for t in senior_titles):
        return False

    return True


def _no_masters_required(j: dict) -> bool:
    """Drop jobs that strictly require a Master's degree with no Bachelor's alternative."""
    desc_lower = (j.get("description") or "").lower()
    title_lower = j["title"].lower()

    # Signals that Master's is strictly required
    masters_required = (
        "master's degree required", "master degree required",
        "masters degree required", "msc required", "m.sc. required",
        "must have a master", "requires a master",
        "master's degree is required", "masterabschluss erforderlich",
        "abgeschlossenes masterstudium",
    )
    # Signals that Bachelor's is also fine
    bachelors_ok = (
        "bachelor", "b.sc", "bsc", "undergraduate",
        "or equivalent", "or related degree",
    )

    for signal in masters_required:
        if signal in desc_lower:
            # Only drop if no bachelor alternative mentioned
            if not any(b in desc_lower for b in bachelors_ok):
                return False

    return True


def _is_english_friendly(j: dict) -> bool:
    """Drop jobs that are clearly German-language unless description confirms English."""
    title_lower = j["title"].lower()
    desc_lower = (j.get("description") or "").lower()

    # Explicit English signal in description → always keep
    english_signals = (
        "english", "working language is english", "language: english",
        "english-speaking", "team language", "our language is english",
    )
    if any(s in desc_lower for s in english_signals):
        return True

    # German word in title → drop
    title_words = set(title_lower.split())
    if title_words & _GERMAN_TITLE_KEYWORDS:
        return False
    if any(frag in title_lower for frag in _GERMAN_TITLE_FRAGMENTS):
        return False

    # Title has "(m/w/d)" or "(w/m/d)" and NO english signal in description → likely German role
    if ("(m/w/d)" in title_lower or "(w/m/d)" in title_lower or "(d/m/w)" in title_lower):
        if "english" not in desc_lower:
            return False

    return True

SEEN_FILE = Path("seen_jobs.json")


def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen: set[str]) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))


def main() -> None:
    print("=" * 60)
    print("  Daily Job Hunter — starting run")
    print("=" * 60)

    seen = load_seen()
    print(f"Previously seen jobs: {len(seen)}")

    # ── Scrape ────────────────────────────────────────────────────────────────
    all_jobs = scrape_all()

    new_jobs = [j for j in all_jobs if j["id"] not in seen]
    print(f"New (unseen) jobs: {len(new_jobs)}")

    # Drop jobs that are clearly German-language with no English mention
    new_jobs = [j for j in new_jobs if _is_english_friendly(j)]
    print(f"After English filter: {len(new_jobs)}")

    # Drop jobs requiring 3+ years experience
    new_jobs = [j for j in new_jobs if _no_experience_overload(j)]
    print(f"After experience filter: {len(new_jobs)}")

    # Drop senior/lead roles
    new_jobs = [j for j in new_jobs if _not_fulltime_senior(j)]
    print(f"After senior filter: {len(new_jobs)}")

    # Drop jobs that strictly require a Master's degree
    new_jobs = [j for j in new_jobs if _no_masters_required(j)]
    print(f"After Master's filter: {len(new_jobs)}")

    if not new_jobs:
        print("Nothing new today. Exiting.")
        # Still save in case seen_jobs.json was empty
        seen.update(j["id"] for j in all_jobs)
        save_seen(seen)
        sys.exit(0)

    # ── Score ─────────────────────────────────────────────────────────────────
    scored = score_jobs(new_jobs)

    good = [j for j in scored if j["score"] >= MIN_SCORE]
    good.sort(key=lambda x: x["score"], reverse=True)
    top = good[:MAX_RESULTS]

    print(f"\nJobs scoring >= {MIN_SCORE}: {len(good)}")
    print(f"Sending top {len(top)} to notifications\n")

    for j in top[:10]:  # print preview in CI logs
        print(f"  [{j['score']:3d}] {j['title']} @ {j['company']} ({j['source']})")

    # ── Notify ────────────────────────────────────────────────────────────────
    if top:
        send_email(top)
        add_to_notion(top)
    else:
        print("No jobs above threshold — no notifications sent.")

    # ── Update seen ───────────────────────────────────────────────────────────
    seen.update(j["id"] for j in new_jobs)
    save_seen(seen)

    print("\nDone. seen_jobs.json updated.")


if __name__ == "__main__":
    main()
