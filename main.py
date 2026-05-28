"""
main.py — daily job hunt orchestrator.

Run locally:  python main.py
Run on CI:    triggered by GitHub Actions (.github/workflows/daily.yml)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from config import BAND_A_MAX, BAND_B_MAX, BAND_C_MAX, MAX_RESULTS, MIN_SCORE
from notifier import add_to_notion, send_email
from scrapers import scrape_all
from scorer import score_jobs


# ── Cross-source dedup ────────────────────────────────────────────────────────
# Same job listed on LinkedIn + the company's Greenhouse board + a web search
# creates three competing entries. Normalize (company, title) and keep ONE,
# preferring the most direct source.

# Higher number = preferred source. ATSs > aggregators > web search.
_SOURCE_PRIORITY: dict[str, int] = {
    # Tier 1 — direct company ATSs (cleanest, full descriptions)
    "Greenhouse":      100,
    "Lever":            95,
    "Ashby":            90,
    "Workday-CXS":      85,
    "Workday":          80,
    "Personio":         80,
    "SmartRecruiters":  78,
    "Amazon":           76,
    "Recruitee":        74,
    # Tier 2 — government / aggregator job boards
    "Arbeitsagentur":   60,
    "Arbeitnow":        55,
    "Remotive":         50,
    # Tier 3 — HN, search
    "HN-Hiring":        40,
    "Adzuna":           38,
    "BraveSearch":      20,
    "DuckDuckGoSearch": 18,
}

# Gender/seniority noise tokens to strip from titles before key construction
_TITLE_NOISE_RE = re.compile(
    r"\(\s*(m/w/d|m/f/d|w/m/d|d/m/w|f/m/x|m/f/x|x/m/f|all\s+genders?)\s*\)"
    r"|\b(m/w/d|m/f/d|w/m/d|d/m/w|f/m/x|m/f/x|all\s+genders?)\b",
    re.IGNORECASE,
)
# Corporate suffixes stripped from the END of company names. Per review,
# this list includes "ai" / "labs" too — necessary for matching
# "Mistral AI" against "mistral", "Stability AI" against "stability", etc.
# Known tradeoff: "Open AI" → "open" while "OpenAI" → "openai" (one token,
# no internal word boundary, so suffix regex can't fire). Rare in practice.
# Applied REPEATEDLY so "X Labs Inc" → "X labs" → "X" → "x" all collapse.
_COMPANY_SUFFIX_RE = re.compile(
    r"\s+(ai|labs|inc|incorporated|gmbh|ag|se|kg|ohg|ltd|limited|llc|"
    r"corp|corporation|group|holdings?|technologies|tech)\.?$",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")


def _normalize(s: str) -> str:
    """lowercase, strip gender markers, collapse whitespace."""
    s = (s or "").lower()
    s = _TITLE_NOISE_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _normalize_company(s: str) -> str:
    """
    Aggressively normalize a company name for dedup keys:
      1. lowercase, strip gender markers, collapse whitespace
      2. repeatedly strip trailing tokens (ai, labs, inc, gmbh, ltd, …)
      3. remove ALL non-alphanumeric characters
    So both "Delivery Hero" and "Deliveryhero" collapse to "deliveryhero",
    "Mistral AI" and "mistral" collapse to "mistral",
    "Stability AI Labs Inc." collapses to "stability".
    """
    s = _normalize(s)
    # Strip trailing tokens repeatedly so "X Labs Inc" → "X labs" → "X"
    for _ in range(5):  # cap to avoid infinite loop on pathological input
        new = _COMPANY_SUFFIX_RE.sub("", s).strip()
        if new == s:
            break
        s = new
    # Remove all non-alphanumeric: spaces, punctuation, accents stripped to nothing
    s = _NON_ALNUM_RE.sub("", s)
    return s


def _dedup_cross_source(jobs: list[dict]) -> list[dict]:
    """
    Collapse duplicates across sources keyed on (normalized company, title).
    Keeps one row per logical job, preferring the highest-priority source.
    """
    best: dict[str, dict] = {}
    for j in jobs:
        key = f"{_normalize_company(j.get('company',''))}::{_normalize(j.get('title',''))}"
        if not key.strip(":"):
            continue
        prior = best.get(key)
        if prior is None:
            best[key] = j
            continue
        cur_pri = _SOURCE_PRIORITY.get(j.get("source", ""), 0)
        prv_pri = _SOURCE_PRIORITY.get(prior.get("source", ""), 0)
        if cur_pri > prv_pri:
            # New source wins; preserve URL from kept row (which is the new one).
            best[key] = j
        elif cur_pri == prv_pri:
            # Tie-break: prefer the row with the longer description (more signal)
            if len(j.get("description", "")) > len(prior.get("description", "")):
                best[key] = j
    return list(best.values())

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


# Specific non-EU cities/countries — positive identification triggers drop.
# Anything NOT in this list and NOT in _GERMANY_TERMS is treated as "unknown"
# and KEPT, so the scorer can decide from the description.
_NON_EU_LOCATIONS = (
    # USA
    "united states", " usa ", "(usa)", "/usa",
    "new york", "san francisco", "boston", "chicago", "los angeles",
    "seattle", "austin", "denver", "atlanta", "washington d.c.",
    "washington dc", "miami", "philadelphia", "houston", "dallas",
    # UK
    "london", "manchester", "birmingham", "united kingdom", " uk ",
    "(uk)", "/uk", "edinburgh", "glasgow", "leeds",
    # Canada
    "toronto", "vancouver", "montreal", "canada",
    # Australia / NZ
    "sydney", "melbourne", "brisbane", "australia", "new zealand",
    # Latin America
    "brazil", "brasil", "colombia", "mexico", "méxico",
    "argentina", "chile", "peru",
    "são paulo", "rio de janeiro", "buenos aires",
    "bogotá", "bogota", "medellín", "medellin",
    "santiago", "lima", "mexico city",
    "latin america", "latam",
    # Middle East (non-EU)
    "dubai", "abu dhabi", "saudi arabia", "qatar", "bahrain",
    "kuwait", "oman", "united arab emirates", " uae ",
    # Asia
    "singapore", "hong kong", "tokyo",
    "bangalore", "bengaluru", "hyderabad", "mumbai", "delhi",
    "chennai", "pune", " india ", "(india)",
    "china", " japan ", "south korea", "taiwan",
    "philippines", "vietnam", "thailand", "indonesia",
    "malaysia", "pakistan",
    # Africa
    "nigeria", "kenya", "south africa", "egypt",
    "nairobi", "lagos", "cape town", "johannesburg",
)


def _is_attendable_from_germany(j: dict) -> bool:
    """
    Recall-friendly location filter:
      - Empty / unknown location          → KEEP (let scorer decide)
      - Hard veto (US-only / UK-only etc) → DROP
      - Germany / DACH / EU coverage      → KEEP
      - Positively non-EU city            → DROP (Bangalore, NYC, São Paulo, etc.)
      - Anything else                     → KEEP (unknown wins)

    The change from the previous behaviour: a location string we don't
    recognise (e.g. "Some Town, Some Country" with no clear signal) used to
    be dropped. Now it passes through. Recall over precision; the scorer is
    smart enough to read the description.
    """
    loc  = (j.get("location")    or "").strip().lower()
    desc = (j.get("description") or "").lower()[:2000]

    # Empty location → KEEP (let scorer judge from description)
    if not loc:
        return True

    combined = f"{loc} {desc}"

    # Hard veto: explicit lock to non-EU region
    if any(s in combined for s in _REMOTE_LOCKED_OUT_SIGNALS):
        return False

    # Germany or DACH signal in location → keep
    if any(t in loc for t in _GERMANY_TERMS):
        return True

    # "Remote" in location → keep if Germany/EU coverage signal exists
    if "remote" in loc:
        if any(t in combined for t in _GERMANY_TERMS):
            return True
        if any(s in desc for s in _REMOTE_COVERS_GERMANY_SIGNALS):
            return True
        # Plain "Remote" with no coverage signal — could still be EU/global.
        # Recall over precision: KEEP and let the scorer judge.
        return True

    # Positively-identified non-EU city/country → drop
    # (use loc + first 200 chars of desc to catch JDs like "based in Mumbai")
    loc_check = f" {loc} {desc[:200]} "
    if any(s in loc_check for s in _NON_EU_LOCATIONS):
        # Non-EU positively identified — only keep if description says
        # explicit remote-from-EU coverage
        if any(s in desc for s in _REMOTE_COVERS_GERMANY_SIGNALS):
            return True
        return False

    # Location is unknown to us — could be a small German town, EU city, etc.
    # Default KEEP so the scorer can decide.
    return True


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


# Senior-title detector — robust against ALL the ways recruiters format titles:
#   "Senior AI Engineer", "Senior_AI_Engineer" (LinkedIn slug),
#   "Senior-Engineer", "(Senior)", "AI Engineer, Senior",
#   "Lead/Principal Data Scientist", "Engineer III/IV"
# Negative lookbehind/lookahead use [a-z] only (NOT \w which includes "_"),
# so underscores, hyphens, slashes, parens, and brackets all act as boundaries.
import re as _re_senior

_RE_SENIOR_IN_TITLE = _re_senior.compile(
    r"(?<![a-z])"
    r"(senior|sr\.?|lead|principal|staff|"
    r"head[\s_\-]of|director|vice[\s_\-]president|\bvp\b|"
    r"chief|architect|"
    r"engineer[\s_\-]+(ii|iii|iv|v)|"
    r"manager|leiter|leiterin|führung|fuehrung|bereichsleiter)"
    r"(?![a-z])",
    _re_senior.IGNORECASE,
)


def _not_fulltime_senior(j: dict) -> bool:
    """
    Drop senior/lead/principal/manager/architect/director roles.

    Sherwan is targeting roles with ≤ 2 years of experience. The experience
    check (_no_experience_overload) already blocks "3+ years" requirements;
    this filter catches title-level seniority signals even when the JD
    doesn't state an explicit year count.

    Allows the role through ONLY if a junior/entry/intern/graduate qualifier
    is also present in the title (e.g. "Junior Engineering Manager" is rare
    but legitimate).
    """
    title = j.get("title", "")
    title_lower = title.lower()

    if _RE_SENIOR_IN_TITLE.search(title):
        # Pass-through if explicitly qualified as junior/entry-level.
        # NOTE: "working student / werkstudent" are NOT here on purpose —
        # Sherwan is not enrolled at a German university and cannot do those.
        junior_qualifiers = (
            "junior", "entry", "entry-level", "entry level",
            "intern", "internship", "praktikum",
            "graduate", "grad ", "trainee",
            "associate", "jr.", "jr ",
        )
        if any(q in title_lower for q in junior_qualifiers):
            return True
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


def main(dry_run: bool = False) -> None:
    print("=" * 60)
    print("  Daily Job Hunter — starting run" + ("  [DRY RUN]" if dry_run else ""))
    print("=" * 60)

    seen = load_seen()
    print(f"Previously seen jobs: {len(seen)}")

    # ── Scrape ────────────────────────────────────────────────────────────────
    all_jobs = scrape_all()

    # ── Cross-source dedup (before unseen filtering so logs are intuitive) ────
    before = len(all_jobs)
    all_jobs = _dedup_cross_source(all_jobs)
    after = len(all_jobs)
    print(f"Cross-source dedup: merged {before} jobs, {after} after dedup")

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

    # ── Tiered bands ─────────────────────────────────────────────────────────
    # MIN_SCORE = 45 is the absolute floor. Within it, group into 3 bands and
    # cap each separately instead of a single global MAX_RESULTS truncation.
    good = [j for j in scored if j["score"] >= MIN_SCORE]
    good.sort(key=lambda x: x["score"], reverse=True)

    band_a = [j for j in good if j["score"] >= 70][:BAND_A_MAX]
    band_b = [j for j in good if 55 <= j["score"] < 70][:BAND_B_MAX]
    band_c = [j for j in good if 45 <= j["score"] < 55][:BAND_C_MAX]
    top = band_a + band_b + band_c

    print(f"\nBand A (Apply now,   70–100): {len(band_a)} jobs")
    print(f"Band B (Worth a look, 55–69): {len(band_b)} jobs")
    print(f"Band C (Long shots,   45–54): {len(band_c)} jobs")
    print(f"Total in digest: {len(top)}\n")

    for j in top[:10]:  # print preview in CI logs
        print(f"  [{j['score']:3d}] {j['title']} @ {j['company']} ({j['source']})")

    # ── Notify ────────────────────────────────────────────────────────────────
    if dry_run:
        print("\n[DRY RUN] Skipping email + Notion. Pipeline complete.")
    elif top:
        send_email(top)
        add_to_notion(top)
    else:
        print("No jobs above threshold — no notifications sent.")

    # ── Update seen ───────────────────────────────────────────────────────────
    if not dry_run:
        seen.update(j["id"] for j in new_jobs)
        save_seen(seen)
        print("\nDone. seen_jobs.json updated.")
    else:
        print("\n[DRY RUN] seen_jobs.json NOT updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Job Hunter")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=bool(os.environ.get("DRY_RUN")),
        help="Run the full pipeline but skip email/Notion delivery and don't update seen_jobs.json. Useful for local testing.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
