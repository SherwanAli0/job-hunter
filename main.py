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

# ── Location filter — Germany on-site OR remote that covers Germany ──────────
# Sherwan lives in Bochum (NRW) and pays German taxes. He needs jobs he can
# actually do FROM Germany — F2F/hybrid in Germany, OR a remote role that
# explicitly allows Germany-based hires. A Poland F2F job is useless even
# though Poland is in the EU; a "Spain HQ, fully remote in EU" job IS useful
# because Germany is covered.

_GERMANY_TERMS = (
    "germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
    "frankfurt", "cologne", "köln", "düsseldorf", "bochum", "dortmund",
    "essen", "stuttgart", "leipzig", "nrw", "bavaria", "bayern",
    "saxony", "sachsen", "hessen", "baden-württemberg",
)

# Phrases that confirm a remote role accepts Germany-based hires.
# If a non-German location appears in the location field, we require ONE of these
# in the description before keeping the job.
_REMOTE_COVERS_GERMANY_SIGNALS = (
    "remote in germany", "remote from germany", "remote within germany",
    "remote (germany", "germany-remote", "remote-germany",
    "remote in eu", "remote within the eu", "remote in the european union",
    "fully remote eu", "fully remote within europe", "fully remote in europe",
    "remote in europe", "remote within europe", "remote across europe",
    "remote anywhere in europe", "europe-wide remote", "eu-wide remote",
    "remote in dach", "dach region", "remote across the dach",
    "we hire across europe", "we hire across the eu",
    "open to candidates in germany", "open to applicants in germany",
    "hiring across europe", "hiring across the eu",
    "based in germany", "based anywhere in europe", "based anywhere in the eu",
    "you can work from anywhere in europe",
    "you can work from anywhere in the eu",
    "you can work from anywhere in the european union",
    "remote across emea",
)

# Phrases that REVOKE Germany eligibility — even if "remote" appears, if these
# show up the role is locked outside Germany.
_REMOTE_LOCKED_OUT_SIGNALS = (
    "us-based only", "us only", "united states only", "must be based in the us",
    "must reside in the us", "must be in the us", "us residents only",
    "uk only", "uk-based only", "must be based in the uk",
    "canada only", "must be based in canada",
    "latin america only", "latam only", "must be based in latam",
    "remote in latam", "remote in latin america",
    "remote in india", "india only", "must be based in india",
    "apac only", "must be based in apac",
)


def _is_attendable_from_germany(j: dict) -> bool:
    """
    Keep jobs Sherwan can actually do from Berlin:
      - Germany in location (any city/state)  → keep
      - "remote" in location with Germany/EU coverage confirmed in description → keep
      - Non-German location BUT description explicitly says remote-includes-Germany/EU → keep
      - Anything else (Poland F2F, Spain F2F, Brazil F2F, US-only remote) → drop
    """
    loc  = (j.get("location")    or "").lower()
    desc = (j.get("description") or "").lower()[:2000]

    # No location → let it through, Claude will score it
    if not loc and not desc:
        return True

    combined = f"{loc} {desc}"

    # Hard veto: description explicitly locks the role outside Germany
    if any(s in combined for s in _REMOTE_LOCKED_OUT_SIGNALS):
        return False

    # Germany in location → always keep (F2F, hybrid, or remote-Berlin)
    if any(t in loc for t in _GERMANY_TERMS):
        return True

    # Location says "remote" → keep only if Germany or EU coverage is confirmed
    if "remote" in loc:
        if any(t in combined for t in _GERMANY_TERMS):
            return True
        if any(s in desc for s in _REMOTE_COVERS_GERMANY_SIGNALS):
            return True
        # "Remote" with zero Germany/EU signal → drop (catches LATAM/US/global remote)
        return False

    # Location is a specific NON-German place (Warsaw, Paris, Madrid, São Paulo...).
    # Even if it's an EU country, Sherwan can't physically attend.
    # ONLY keep if description explicitly says the role is remote-from-Germany or
    # remote-EU-wide (so Germany is included).
    if any(s in desc for s in _REMOTE_COVERS_GERMANY_SIGNALS):
        return True

    # Otherwise drop — Sherwan would have to relocate, which he can't.
    return False


def _no_experience_overload(j: dict) -> bool:
    """Drop jobs that require 3+ years of experience anywhere in the description."""
    import re
    desc_lower = (j.get("description") or "").lower()

    patterns = [
        # "3+ years of [any qualifier] experience" — covers industry/hands-on/
        # relevant/practical/professional/work/applicable/proven experience
        r"\b([3-9]|\d{2})\+?\s*years?\s+(?:of\s+)?(?:[\w-]+\s+){0,3}experience",
        # "3+ years experience" or "3 years experience" without "of"
        r"\b([3-9]|\d{2})\+?\s*years?\s+experience",
        # "minimum 3 years"
        r"\bminimum\s*(?:of\s*)?([3-9]|\d{2})\s*\+?\s*years?",
        # "at least 3 years"
        r"\bat\s+least\s+([3-9]|\d{2})\+?\s*years?",
        # "3-5 years" / "3–5 years" — range form
        r"\b([3-9]|\d{2})\s*[-–]\s*\d+\s*years?\s+(?:of\s+)?(?:[\w-]+\s+){0,3}experience",
        # "3+ years Python" — bare "3+ years <skill>" (the + sign is the signal)
        r"\b([3-9]|\d{2})\+\s*years?",
        # "experience: 3+ years"
        r"\bexperience\s*:?\s*([3-9]|\d{2})\+?\s*years?",
        # Written-out forms: "three years", "minimum five years"
        r"\b(three|four|five|six|seven|eight|nine|ten)\s+(?:\(\s*\d+\s*\)\s+)?years?\s+(?:of\s+)?(?:[\w-]+\s+){0,3}experience",
        r"\b(minimum|at\s+least)\s+(of\s+)?(three|four|five|six|seven|eight|nine|ten)\s+(?:\(\s*\d+\s*\)\s+)?years?",
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
    import re
    desc_lower = (j.get("description") or "").lower()

    # Signals that Bachelor's is also fine — if any of these is present
    # alongside a Master's signal, we keep the job.
    bachelors_ok = (
        "bachelor", "b.sc", "bsc", "undergraduate",
        "or equivalent", "or related degree", "ba/bs",
    )
    has_bachelor_alt = any(b in desc_lower for b in bachelors_ok)

    # Signals that Master's is strictly required (verbose form)
    masters_required_verbose = (
        "master's degree required", "master degree required",
        "masters degree required", "msc required", "m.sc. required",
        "must have a master", "requires a master",
        "master's degree is required", "masterabschluss erforderlich",
        "abgeschlossenes masterstudium",
    )
    for signal in masters_required_verbose:
        if signal in desc_lower:
            if not has_bachelor_alt:
                return False

    # NEW: catch concise "Master Degree in X" / "Master's Degree in X" /
    # "Master of Science in X" / "MSc in X" — these are clear requirements
    # even without the word "required" attached.
    masters_concise = (
        r"\bmaster(?:'s)?\s+degree\s+in\b",
        r"\bmaster\s+of\s+science\s+in\b",
        r"\bmsc\s+in\b",
        r"\bm\.sc\.?\s+in\b",
    )
    for pat in masters_concise:
        if re.search(pat, desc_lower):
            if not has_bachelor_alt:
                return False

    # NEW: contextual — "Minimum Qualifications" / "Required Qualifications"
    # header followed within ~300 chars by "master" with no bachelor alternative
    # in the same window. This catches the Netlight-style listings.
    context_patterns = (
        r"(minimum|required|essential)\s+qualifications?[\s\S]{0,300}?\bmaster",
        r"requirements?\s*:[\s\S]{0,300}?\bmaster\s+degree",
    )
    for pat in context_patterns:
        m = re.search(pat, desc_lower)
        if m:
            window = m.group(0)
            if not any(b in window for b in bachelors_ok):
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

    # Germany on-site OR remote-that-includes-Germany only.
    # Drops: Poland F2F, Spain F2F, Brazil/Colombia, US-only remote, etc.
    new_jobs = [j for j in new_jobs if _is_attendable_from_germany(j)]
    print(f"After location filter (Germany-attendable): {len(new_jobs)}")

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

    # ── Disqualification histogram ───────────────────────────────────────────
    # Helps tune filters over time — if "experience" dominates, the bar is too
    # strict; if "german_required" is huge, search pool needs better targeting.
    from collections import Counter
    dq_counts = Counter(
        j.get("disqualified_category") or "(passed)"
        for j in scored
    )
    print("\n── Pre-screen disqualification histogram ──")
    for category, count in dq_counts.most_common():
        bar = "█" * min(count, 40)
        print(f"  {category:22s} {count:4d}  {bar}")

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
