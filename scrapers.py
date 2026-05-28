"""
scrapers.py — pulls jobs from all configured sources.

Sources:
  1. JobSpy       → LinkedIn + Indeed (reliable, no Glassdoor — Cloudflare blocked)
  2. Arbeitnow    → free JSON API, English-language jobs, Germany-focused
  3. Remotive     → free JSON API, remote jobs worldwide
  4. Arbeitsagentur → official German employment agency API
  5. Workday      → BMW, Siemens, Bosch, SAP, Telekom, Zalando, etc.
  6. SuccessFactors → VW, Adidas, Porsche, E.ON, etc.
  7. Greenhouse   → Zalando, DeepL, Delivery Hero, N26, etc.
  8. Lever        → HelloFresh, etc.
  9. Company pages → direct career pages (GIZ, Bosch, BMW, etc.)
 10. Brave Search → official web search API (finds jobs across the whole web)
 11. DuckDuckGo   → fallback web search
"""

import hashlib
import os
import time
import traceback
from typing import Any

import requests
from bs4 import BeautifulSoup

from config import (
    GREENHOUSE_SLUGS,
    LEVER_SLUGS,
    LOCATION,
    SEARCH_QUERIES,
)

# These are imported lazily below to allow config.py to define them after the
# first import; not strictly necessary but defensive against load order issues.
try:
    from config import PERSONIO_SLUGS
except ImportError:
    PERSONIO_SLUGS: list[str] = []
try:
    from config import SMARTRECRUITERS_SLUGS
except ImportError:
    SMARTRECRUITERS_SLUGS: list[str] = []
try:
    from config import WORKDAY_CXS_TENANTS
except ImportError:
    WORKDAY_CXS_TENANTS: list[tuple[str, str, str]] = []
try:
    from config import ASHBY_SLUGS
except ImportError:
    ASHBY_SLUGS: list[str] = []
try:
    from config import RECRUITEE_SLUGS
except ImportError:
    RECRUITEE_SLUGS: list[str] = []

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── helpers ────────────────────────────────────────────────────────────────────

def make_id(url: str, title: str, company: str) -> str:
    raw = f"{url}{title}{company}".lower()
    return hashlib.md5(raw.encode()).hexdigest()


def job(title, company, location, url, source, description="", posted_at=""):
    return {
        "id": make_id(url, title, company),
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "source": source,
        "description": description[:5000],  # cap size — must be long enough that the requirements section isn't lost behind a verbose intro
        "posted_at": posted_at,  # ISO 8601 string, empty if source doesn't expose it
        "score": 0,
        "reason": "",
    }


# ── 1. JobSpy (LinkedIn + Indeed + Glassdoor) ──────────────────────────────────

def scrape_jobspy() -> list[dict]:
    try:
        from jobspy import scrape_jobs  # type: ignore

        results = []
        for query in SEARCH_QUERIES[:8]:  # limit to avoid rate limits
            try:
                df = scrape_jobs(
                    site_name=["linkedin", "indeed"],  # glassdoor = Cloudflare blocked
                    search_term=query,
                    location=LOCATION,
                    results_wanted=25,
                    # 72h window so one failed daily run doesn't permanently lose
                    # a day of LinkedIn/Indeed postings; seen_jobs dedup prevents
                    # repeats from the overlap.
                    hours_old=72,
                    country_indeed="Germany",
                )
                for _, row in df.iterrows():
                    url = str(row.get("job_url", "")) or str(row.get("url", ""))
                    if not url:
                        continue
                    posted = row.get("date_posted", "") or ""
                    results.append(job(
                        title=str(row.get("title", "")),
                        company=str(row.get("company", "")),
                        location=str(row.get("location", "")),
                        url=url,
                        source=str(row.get("site", "jobspy")),
                        description=str(row.get("description", "")),
                        posted_at=str(posted) if posted else "",
                    ))
                time.sleep(3)
            except Exception:
                continue
        print(f"  [JobSpy] {len(results)} jobs")
        return results
    except Exception as e:
        print(f"  [JobSpy] failed: {e}")
        return []


# ── 2. Arbeitnow API (free JSON API — English-language jobs, Germany-focused) ──

_ARBEITNOW_KEYWORDS = {
    "data scientist", "data science", "machine learning", "ml engineer",
    "data analyst", "ai engineer", "nlp", "deep learning", "data engineer",
    "junior data", "internship data", "praktikum data",
}


def scrape_arbeitnow() -> list[dict]:
    """
    Arbeitnow.com free JSON API.
    All listings are English-language; Germany is the primary market.
    API docs: https://www.arbeitnow.com/api/job-board-api
    """
    results = []
    seen_slugs: set[str] = set()
    try:
        for page in range(1, 6):  # up to 5 pages (~100 jobs total)
            r = requests.get(
                "https://www.arbeitnow.com/api/job-board-api",
                params={"page": page},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                break
            data = r.json()
            items = data.get("data", [])
            if not items:
                break

            for item in items:
                title = item.get("title", "")
                slug = item.get("slug", "")
                if not title or slug in seen_slugs:
                    continue

                title_lower = title.lower()
                tags_str = " ".join(item.get("tags", [])).lower()
                if not any(kw in title_lower or kw in tags_str for kw in _ARBEITNOW_KEYWORDS):
                    continue

                seen_slugs.add(slug)
                location = item.get("location", "Germany")
                company = item.get("company_name", "")
                url = item.get("url", "")
                description = BeautifulSoup(
                    item.get("description", ""), "html.parser"
                ).get_text()[:1500]
                # Arbeitnow exposes created_at as Unix timestamp
                created = item.get("created_at")
                posted_at = ""
                if created:
                    try:
                        from datetime import datetime, timezone
                        posted_at = datetime.fromtimestamp(int(created), tz=timezone.utc).isoformat()
                    except Exception:
                        posted_at = ""
                results.append(job(title, company, location, url, "Arbeitnow", description, posted_at))

            time.sleep(1)
    except Exception as e:
        print(f"  [Arbeitnow] failed: {e}")
    print(f"  [Arbeitnow] {len(results)} jobs")
    return results


# ── 3. Remotive API (free JSON API — remote jobs worldwide) ───────────────────

def scrape_remotive() -> list[dict]:
    """
    Remotive.com free API — remote-only jobs, international.
    API docs: https://remotive.com/api/remote-jobs
    """
    results = []
    seen_ids: set[int] = set()
    queries = [
        "data scientist", "machine learning", "data analyst",
        "AI engineer", "NLP engineer", "data engineer",
    ]
    try:
        for q in queries:
            r = requests.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": q, "limit": 20},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            for item in data.get("jobs", []):
                job_id = item.get("id")
                if not job_id or job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                title = item.get("title", "")
                company = item.get("company_name", "")
                location = item.get("candidate_required_location", "Remote") or "Remote"
                url = item.get("url", "")
                description = BeautifulSoup(
                    item.get("description", ""), "html.parser"
                ).get_text()[:1500]
                if title:
                    posted_at = item.get("publication_date", "") or ""
                    results.append(job(title, company, location, url, "Remotive", description, posted_at))
            time.sleep(1)
    except Exception as e:
        print(f"  [Remotive] failed: {e}")
    print(f"  [Remotive] {len(results)} jobs")
    return results


# ── 3b. Hacker News "Who is hiring?" monthly thread ──────────────────────────
# Hidden gem: posted on the 1st of every month, ~600 hiring comments from
# YC and YC-adjacent companies. Founder-direct applications, much smaller
# applicant pools (10-30 typical) than LinkedIn. Free Algolia API.

_HN_SEARCH_API = "https://hn.algolia.com/api/v1/search"
_HN_ITEM_API   = "https://hn.algolia.com/api/v1/items"

# A comment must mention at least one of these to count as Germany/EU-relevant
_HN_LOCATION_KEYWORDS = (
    "berlin", "germany", "deutschland", "munich", "münchen", "muenchen",
    "hamburg", "frankfurt", "cologne", "köln", "stuttgart", "düsseldorf",
    "remote eu", "remote europe", "remote (eu", "remote (europe",
    "remote, eu", "remote, europe", "remote/eu", "remote/europe",
    "europe-wide", "eu-wide", "eu remote", "europe remote",
    "remote in eu", "remote in europe", "remote within eu",
    "remote within europe", "remote across europe", "remote across the eu",
    "anywhere in europe", "anywhere in the eu", "dach region",
)

# AND must mention at least one of these to be a relevant role
_HN_ROLE_KEYWORDS = (
    "ml", " ai ", "ai ", " ai,", " ai.", "machine learning", "data scientist",
    "data science", "data engineer", "data analyst", "llm", "nlp",
    "deep learning", "applied scientist", "research engineer", "ml engineer",
    "ai engineer", "foundation model", "generative ai", "genai",
    "junior", "intern", "graduate", "entry-level", "entry level",
    "python", "pytorch", "tensorflow", "applied ai",
)


def scrape_hn_who_is_hiring() -> list[dict]:
    """
    Scrape the latest 'Ask HN: Who is hiring?' monthly threads.
    Returns relevant comments as job postings — small pool, often founder-direct.
    """
    results = []
    try:
        # Find the latest "Who is hiring?" threads (posted by user `whoishiring`)
        r = requests.get(
            _HN_SEARCH_API,
            params={
                "query": "Ask HN: Who is hiring?",
                "tags": "story,author_whoishiring",
                "hitsPerPage": 3,
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  [HN-Hiring] Search API returned {r.status_code}")
            return []
        hits = r.json().get("hits", [])
        if not hits:
            print("  [HN-Hiring] No 'Who is hiring' threads found.")
            return []

        # Take the 2 most recent threads (current month + previous, in case a
        # month just turned and the new thread is small)
        thread_ids = [h["objectID"] for h in hits[:2]]

        for thread_id in thread_ids:
            try:
                r = requests.get(f"{_HN_ITEM_API}/{thread_id}", timeout=20)
                if r.status_code != 200:
                    continue
                thread = r.json()
                comments = thread.get("children", []) or []

                for c in comments:
                    text = (c.get("text") or "").strip()
                    if not text or len(text) < 80:
                        continue
                    text_lower = text.lower()

                    # Must mention a Germany/EU location
                    if not any(loc in text_lower for loc in _HN_LOCATION_KEYWORDS):
                        continue
                    # Must mention a relevant role/skill
                    if not any(kw in text_lower for kw in _HN_ROLE_KEYWORDS):
                        continue

                    # Strip HTML
                    clean = BeautifulSoup(text, "html.parser").get_text(separator="\n").strip()

                    # HN convention: "Company | Role | Location | Onsite/Remote | ..."
                    first_line = clean.split("\n", 1)[0].strip()
                    parts = [p.strip() for p in first_line.split("|")]
                    company = (parts[0][:80] if parts and parts[0] else "HN Hiring")
                    title = (parts[1][:120] if len(parts) > 1 and parts[1] else first_line[:120])
                    location = (parts[2][:80] if len(parts) > 2 and parts[2] else "See post")

                    # Posted timestamp (HN gives Unix ts via created_at_i)
                    posted_at = ""
                    ts = c.get("created_at_i")
                    if ts:
                        try:
                            from datetime import datetime, timezone
                            posted_at = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                        except Exception:
                            posted_at = c.get("created_at", "") or ""
                    else:
                        posted_at = c.get("created_at", "") or ""

                    url = f"https://news.ycombinator.com/item?id={c.get('id')}"

                    results.append(job(
                        title=title,
                        company=company,
                        location=location,
                        url=url,
                        source="HN-Hiring",
                        description=clean[:1800],
                        posted_at=posted_at,
                    ))
                time.sleep(1)
            except Exception as e:
                print(f"  [HN-Hiring] thread {thread_id} failed: {e}")
                continue
    except Exception as e:
        print(f"  [HN-Hiring] failed: {e}")

    print(f"  [HN-Hiring] {len(results)} jobs")
    return results


# ── 4. Greenhouse API ──────────────────────────────────────────────────────────

def scrape_greenhouse() -> list[dict]:
    results = []
    for slug in GREENHOUSE_SLUGS:
        try:
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
                timeout=15,
            )
            data = r.json()
            for j in data.get("jobs", []):
                title = j.get("title", "")
                location = j.get("location", {}).get("name", "")
                url = j.get("absolute_url", "")
                description = BeautifulSoup(j.get("content", ""), "html.parser").get_text()[:1500]
                posted_at = j.get("updated_at", "") or j.get("first_published", "") or ""

                # Only include Germany-based roles (or remote)
                loc_lower = location.lower()
                if "germany" in loc_lower or "deutschland" in loc_lower or "remote" in loc_lower or not location:
                    results.append(job(title, slug.title(), location, url, "Greenhouse", description, posted_at))
            time.sleep(1)
        except Exception:
            continue
    print(f"  [Greenhouse] {len(results)} jobs")
    return results


# ── 5. Lever API ───────────────────────────────────────────────────────────────

def scrape_lever() -> list[dict]:
    results = []
    for slug in LEVER_SLUGS:
        try:
            r = requests.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json",
                timeout=15,
            )
            postings = r.json()
            for p in postings:
                location = p.get("categories", {}).get("location", "")
                loc_lower = location.lower()
                if "germany" not in loc_lower and "deutschland" not in loc_lower and "remote" not in loc_lower and location:
                    continue
                title = p.get("text", "")
                url = p.get("hostedUrl", "")
                description = BeautifulSoup(
                    p.get("descriptionPlain", "") or p.get("description", ""), "html.parser"
                ).get_text()[:1500]
                # Lever createdAt is epoch ms
                created_ms = p.get("createdAt")
                posted_at = ""
                if created_ms:
                    try:
                        from datetime import datetime, timezone
                        posted_at = datetime.fromtimestamp(int(created_ms) / 1000, tz=timezone.utc).isoformat()
                    except Exception:
                        posted_at = ""
                results.append(job(title, slug.title(), location, url, "Lever", description, posted_at))
            time.sleep(1)
        except Exception:
            continue
    print(f"  [Lever] {len(results)} jobs")
    return results


# ── 7. Arbeitsagentur (German Federal Employment Agency — official API) ────────

ARBEITSAGENTUR_QUERIES = [
    "Data Science",
    "Machine Learning",
    "Data Analyst",
    "Artificial Intelligence",
    "Junior Data Scientist",
    "Junior ML Engineer",
    "Data Science Internship",
    "Praktikum Data Science",
]

def scrape_arbeitsagentur() -> list[dict]:
    """Uses the unofficial but stable Arbeitsagentur API — free, no auth needed."""
    results = []
    seen_refs: set[str] = set()

    for query in ARBEITSAGENTUR_QUERIES:
        try:
            params = {
                "angebotsart": 1,      # job listings
                "was": query,          # search term
                "wo": "Deutschland",   # whole Germany
                "umkreis": 200,        # radius km
                "size": 25,
                "page": 1,
            }
            r = requests.get(
                "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs",
                params=params,
                headers={**HEADERS, "X-API-Key": "jobboerse-jobsuche"},
                timeout=15,
            )
            data = r.json()
            for item in data.get("stellenangebote", []):
                ref = item.get("refnr", "")
                if not ref or ref in seen_refs:
                    continue
                seen_refs.add(ref)

                title = item.get("titel", "")
                company = item.get("arbeitgeber", "")
                location = item.get("arbeitsort", {}).get("ort", "Germany")
                job_url = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref}"
                description = item.get("kurzbeschreibung", "") or ""

                results.append(job(title, company, location, job_url, "Arbeitsagentur", description))

            time.sleep(1)
        except Exception as e:
            print(f"  [Arbeitsagentur] query '{query}' failed: {e}")
            continue

    print(f"  [Arbeitsagentur] {len(results)} jobs")
    return results


# ── 8. Workday API (used by BMW, Siemens, Bosch, Telekom, SAP, etc.) ──────────

# Companies using Workday — format: (tenant, site, display_name)
WORKDAY_TENANTS = [
    ("bmwgroup", "BMW_Group_External", "BMW Group"),
    ("siemens", "siemens_career", "Siemens"),
    ("bosch", "bosch_external", "Bosch"),
    ("deutschetelekom", "telekom_career", "Deutsche Telekom"),
    ("allianz", "allianz", "Allianz"),
    ("sap", "SAP", "SAP"),
    ("continental", "conti_career", "Continental"),
    ("infineon", "infineon_careers", "Infineon"),
    ("zalando", "zalando", "Zalando"),
    ("delivery-hero", "delivery_hero", "Delivery Hero"),
    ("bayer", "bayer_career", "Bayer"),
    ("basf", "basf_career", "BASF"),
    ("dhl", "dhl_group", "DHL Group"),
    ("lufthansa", "lufthansa_career", "Lufthansa"),
    ("merck", "merck_career", "Merck"),
]

WORKDAY_KEYWORDS = [
    "data science", "machine learning", "data analyst",
    "artificial intelligence", "data engineer", "NLP",
]

def _scrape_workday_tenant(tenant: str, site: str, company_name: str) -> list[dict]:
    results = []
    for keyword in WORKDAY_KEYWORDS:
        try:
            for dc in ["wd3", "wd5", "wd1"]:
                url = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
                payload = {
                    "appliedFacets": {},
                    "limit": 20,
                    "offset": 0,
                    "searchText": keyword,
                }
                r = requests.post(url, json=payload, headers=HEADERS, timeout=10)
                if r.status_code != 200:
                    continue
                data = r.json()
                for item in data.get("jobPostings", []):
                    title = item.get("title", "")
                    location = item.get("locationsText", "Germany")
                    path = item.get("externalPath", "")
                    job_url = f"https://{tenant}.{dc}.myworkdayjobs.com/{site}/job/{path}" if path else ""
                    if title:
                        results.append(job(title, company_name, location, job_url, "Workday"))
                break  # found working datacenter
        except Exception:
            continue
    return results


def scrape_workday() -> list[dict]:
    results = []
    for tenant, site, name in WORKDAY_TENANTS:
        try:
            jobs = _scrape_workday_tenant(tenant, site, name)
            results.extend(jobs)
            if jobs:
                print(f"  [Workday] {name}: {len(jobs)} jobs")
            else:
                print(f"  [Workday] {name}: 0 (check tenant/site or Cloudflare-blocked)")
            time.sleep(1)
        except Exception as e:
            print(f"  [Workday] {name}: ERROR {type(e).__name__}: {e}")
            continue
    print(f"  [Workday] TOTAL {len(results)} jobs across {len(WORKDAY_TENANTS)} tenants")
    return results


# ── 9. SAP SuccessFactors (large German companies) ────────────────────────────

SF_COMPANIES = [
    ("volkswagen", "Volkswagen"),
    ("eon-energy", "E.ON"),
    ("munichre", "Munich Re"),
    ("tuigroup", "TUI Group"),
    ("henkel", "Henkel"),
    ("adidas", "Adidas"),
    ("porsche", "Porsche"),
]

SF_KEYWORDS = ["data", "machine learning", "analyst", "science", "AI", "intelligence"]

def scrape_successfactors() -> list[dict]:
    results = []
    for company_id, company_name in SF_COMPANIES:
        try:
            url = f"https://career4.successfactors.com/career?company={company_id}&resultType=XML"
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "xml")
            for item in soup.find_all("job")[:50]:
                title = item.findtext("title") or item.findtext("jobTitle") or ""
                location = item.findtext("location") or item.findtext("city") or "Germany"
                job_url = item.findtext("url") or item.findtext("applyUrl") or ""

                title_lower = title.lower()
                if not any(kw in title_lower for kw in SF_KEYWORDS):
                    continue
                if "germany" not in location.lower() and "deutschland" not in location.lower() and "de" not in location.lower():
                    continue

                results.append(job(title, company_name, location, job_url, "SuccessFactors"))
            time.sleep(1)
        except Exception:
            continue
    print(f"  [SuccessFactors] {len(results)} jobs")
    return results


# ── 10. Brave Search API (official, reliable web search) ─────────────────────

def scrape_brave_search() -> list[dict]:
    """Brave Search API — official, reliable alternative to DuckDuckGo."""
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        print("  [Brave] BRAVE_API_KEY not set, skipping.")
        return []

    results = []
    seen_urls: set[str] = set()

    for query in _WEB_QUERIES:
        try:
            r = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
                params={
                    "q": query,
                    "count": 20,
                    "country": "de",
                    "search_lang": "en",
                    "freshness": "pw",  # past week
                },
                timeout=15,
            )
            data = r.json()
            for item in data.get("web", {}).get("results", []):
                url = item.get("url", "")
                title = item.get("title", "")
                snippet = item.get("description", "")

                if not url or not title or url in seen_urls:
                    continue

                try:
                    domain = url.split("/")[2].replace("www.", "")
                except IndexError:
                    continue
                if any(skip in domain for skip in _SKIP_DOMAINS):
                    continue

                title_lower = title.lower()
                url_lower = url.lower()
                if not any(kw in title_lower or kw in url_lower for kw in (
                    "job", "career", "stelle", "position", "work", "hiring",
                    "data", "machine", "analyst", "engineer", "scientist",
                    "werkstudent", "praktikum", "internship",
                )):
                    continue

                seen_urls.add(url)
                parts = domain.split(".")
                company = parts[-2].title() if len(parts) >= 2 else domain

                # Fetch full description from the page
                full_desc = _fetch_full_description(url)
                description = full_desc if len(full_desc) > len(snippet) else snippet

                # Don't blindly tag as "Germany" — extract the actual location
                # from the description so the location filter can do its job.
                location_hint = _extract_location_hint(description) or _extract_location_hint(snippet)

                results.append(job(
                    title=title,
                    company=company,
                    location=location_hint,
                    url=url,
                    source="BraveSearch",
                    description=description,
                ))
            time.sleep(1)
        except Exception as e:
            print(f"  [Brave] query failed: {e}")
            continue

    print(f"  [Brave] {len(results)} jobs")
    return results


# ── 11. Web search (DuckDuckGo — finds jobs on ANY company website) ───────────

# Domains already covered by other scrapers — skip to avoid duplicates
_SKIP_DOMAINS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "stepstone.de",
    "xing.com", "monster.de", "karriere.at", "jobs.ch", "jobware.de",
    "greenhouse.io", "lever.co", "workday.com", "smartrecruiters.com",
    "recruitee.com", "bamboohr.com", "join.com", "jobteaser.com",
}

# Broad queries designed to surface jobs on company career pages
_WEB_QUERIES = [
    # Junior roles + English
    '"junior data scientist" Germany "English"',
    '"junior machine learning engineer" Germany "English"',
    '"junior AI engineer" Germany "English"',
    '"junior data analyst" Germany "English"',
    '"junior NLP engineer" Germany "English"',
    # Entry level + English
    '"entry level" "data science" Germany "English"',
    '"entry level" "machine learning" Germany "English"',
    '"graduate" "data scientist" Germany "English"',
    '"associate data scientist" Germany "English"',
    # Internships
    '"data science internship" Germany "English"',
    '"machine learning internship" Germany "English"',
    '"AI internship" Germany "English"',
    '"data analyst internship" Germany "English"',
    '"praktikum" "data science" "English"',
    # Specific skills + English
    '"python" "machine learning" junior Germany "English"',
    '"llm" OR "nlp" junior Germany "English"',
    '"deep learning" junior Germany "English"',
    # Remote / hybrid + English
    '"remote" "junior data scientist" Germany "English"',
    '"hybrid" "junior data scientist" Germany "English"',
    '"remote" "machine learning engineer" Germany "English"',
    '"fully remote" "data science" Germany "English"',
    # Dedicated remote searches — any location, English-speaking
    '"fully remote" "data scientist" "English"',
    '"fully remote" "machine learning" "English"',
    '"fully remote" "data analyst" "English"',
    '"remote first" "data science" "English"',
    '"remote" "junior ML" "English"',
    '"remote" "data science" internship "English"',
    '"work from anywhere" "data science" "English"',
    '"work from home" "junior data scientist" "English"',
    '"remote" "AI engineer" junior "English"',
    '"remote" "NLP" junior "English"',
]


def _extract_location_hint(text: str) -> str:
    """
    Cheap heuristic to pull a location hint from a JD description.
    Returns the first matching city/country phrase, or empty string if none.
    Used for web-search scrapers where we don't get a structured location field.
    Returning empty is now SAFE for keep-on-unknown: main.py's location filter
    treats empty as 'pass through to the scorer'.
    """
    t = text.lower()[:3000]
    # German cities first — expanded list per recall fix
    GERMAN_CITIES = (
        "berlin", "munich", "münchen", "muenchen", "hamburg", "frankfurt",
        "köln", "cologne", "düsseldorf", "duesseldorf", "stuttgart", "leipzig",
        "bochum", "dortmund", "essen", "bonn", "germany", "deutschland",
        # Newly added cities — expanded recall
        "heidelberg", "nürnberg", "nuernberg", "nuremberg",
        "mannheim", "karlsruhe", "aachen", "bremen",
        "hannover", "hanover", "mainz", "wiesbaden",
        "münster", "muenster", "augsburg", "freiburg",
        "bielefeld", "dresden", "duisburg", "wuppertal",
        "kiel", "lübeck", "luebeck", "rostock", "jena",
        "kassel", "braunschweig",
    )
    for city in GERMAN_CITIES:
        if city in t:
            return city.title()
    # Other places — surface them so the location filter can drop accordingly
    for place in ("london", "paris", "amsterdam", "madrid", "warsaw", "milan",
                  "new york", "san francisco", "boston", "toronto",
                  "sydney", "dubai", "singapore", "mumbai", "bangalore",
                  "são paulo", "bogotá", "remote", "worldwide", "anywhere"):
        if place in t:
            return place.title()
    return ""


def _fetch_full_description(url: str) -> str:
    """Visit a URL and extract meaningful text from the page."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find the main job content block first
        for selector in [
            "[class*='job-description']", "[class*='job-detail']",
            "[class*='description']", "[class*='content']",
            "main", "article", "[role='main']",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:3000]

        # Fallback: full page text
        return soup.get_text(separator=" ", strip=True)[:3000]
    except Exception:
        return ""


def scrape_web_search() -> list[dict]:
    """
    Two-stage web search:
    1. DuckDuckGo finds relevant URLs across the entire web
    2. We visit each URL and fetch the full job description
    """
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except ImportError:
        print("  [WebSearch] duckduckgo-search not installed, skipping.")
        return []

    # Stage 1: collect candidate URLs from DDG
    candidates = []  # list of (url, title, snippet, company)
    seen_urls: set[str] = set()

    try:
        ddgs = DDGS()
        for query in _WEB_QUERIES:
            try:
                hits = list(ddgs.text(
                    query,
                    max_results=30,
                    region="de-de",
                    timelimit="w",
                ))
                for h in hits:
                    url = h.get("href", "")
                    title = h.get("title", "")
                    snippet = h.get("body", "")

                    if not url or not title or url in seen_urls:
                        continue

                    try:
                        domain = url.split("/")[2].replace("www.", "")
                    except IndexError:
                        continue
                    if any(skip in domain for skip in _SKIP_DOMAINS):
                        continue

                    title_lower = title.lower()
                    url_lower = url.lower()
                    if not any(kw in title_lower or kw in url_lower for kw in (
                        "job", "career", "stelle", "position", "work", "hiring",
                        "data", "machine", "analyst", "engineer", "scientist",
                        "werkstudent", "praktikum", "internship",
                    )):
                        continue

                    seen_urls.add(url)
                    parts = domain.split(".")
                    company = parts[-2].title() if len(parts) >= 2 else domain
                    candidates.append((url, title, snippet, company))

                time.sleep(2)
            except Exception as e:
                print(f"  [WebSearch] query '{query[:40]}' failed: {e}")
                continue
    except Exception as e:
        print(f"  [WebSearch] DDG search failed: {e}")

    print(f"  [WebSearch] Found {len(candidates)} candidate URLs, fetching full descriptions...")

    # Stage 2: visit each URL and fetch full description
    results = []
    for url, title, snippet, company in candidates:
        full_desc = _fetch_full_description(url)
        # Use full description if we got something meaningful, else fall back to snippet
        description = full_desc if len(full_desc) > len(snippet) else snippet
        # Extract real location from description rather than tagging "Germany"
        location_hint = _extract_location_hint(description) or _extract_location_hint(snippet)
        results.append(job(
            title=title,
            company=company,
            location=location_hint,
            url=url,
            source="WebSearch",
            description=description,
        ))
        time.sleep(1)  # be polite

    print(f"  [WebSearch] {len(results)} jobs with full descriptions")
    return results


# ── 12. Amazon Jobs API (custom public JSON) ─────────────────────────────────
# Amazon is the largest single tech employer in Germany. Their own API is
# public, no auth, returns JSON. We run multiple queries because their search
# only matches the query string, not a category.

_AMAZON_API = "https://www.amazon.jobs/en/search.json"
_AMAZON_QUERIES = (
    "machine learning", "data scientist", "applied scientist",
    "AI engineer", "data engineer", "ML engineer",
    "research scientist", "applied AI", "data analyst",
    "software development engineer ML", "scientist intern",
    "machine learning intern", "data science intern",
)


def scrape_amazon() -> list[dict]:
    """
    Scrape Amazon Jobs for Germany-based AI/ML/data roles via their public API.
    Runs multiple targeted queries and dedupes by job_path.
    """
    seen_paths: set[str] = set()
    results: list[dict] = []

    for q in _AMAZON_QUERIES:
        try:
            r = requests.get(
                _AMAZON_API,
                params={
                    "base_query": q,
                    "country": "DEU",  # Germany only at API level
                    "result_limit": 100,
                    "offset": 0,
                },
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                continue
            for jb in r.json().get("jobs", []) or []:
                path = jb.get("job_path", "")
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                title = jb.get("title", "") or ""
                location = (
                    jb.get("normalized_location", "")
                    or jb.get("location", "")
                    or "Germany"
                )
                url = "https://www.amazon.jobs" + path
                desc = (
                    jb.get("description_short", "")
                    or jb.get("description", "")
                    or ""
                )
                posted = jb.get("posted_date", "") or jb.get("updated_time", "")
                results.append(job(
                    title=title,
                    company="Amazon",
                    location=location,
                    url=url,
                    source="Amazon",
                    description=desc,
                    posted_at=posted,
                ))
            time.sleep(0.6)  # be polite to Amazon's endpoint
        except Exception as e:
            print(f"  [Amazon] query '{q}' failed: {e}")
            continue

    print(f"  [Amazon] {len(results)} jobs (deduped across {len(_AMAZON_QUERIES)} queries)")
    return results


# ── 13. Personio XML feeds ───────────────────────────────────────────────────
# Personio is the German Mittelstand's favourite HR system. Each company has
# a public XML feed at {slug}.jobs.personio.de/xml — no auth, full descriptions.

def _personio_text(el, tag):
    """Find a child tag by name and return its text, or empty string."""
    if el is None:
        return ""
    child = el.find(tag)
    if child is None:
        return ""
    return (child.text or "").strip()


def scrape_personio() -> list[dict]:
    """
    Iterate PERSONIO_SLUGS, parse each company's XML feed, return all positions.
    Catches German AI/ML/Mittelstand companies that 404 on Greenhouse.
    """
    results: list[dict] = []
    for slug in PERSONIO_SLUGS:
        try:
            r = requests.get(
                f"https://{slug}.jobs.personio.de/xml",
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "xml")
            positions = soup.find_all("position")
            company_name = slug.replace("-", " ").title()

            for pos in positions:
                title = _personio_text(pos, "name") or _personio_text(pos, "title")
                if not title:
                    continue
                location = (
                    _personio_text(pos, "office")
                    or _personio_text(pos, "location")
                    or "Germany"
                )
                # Personio URLs come either as <url> or constructed via id
                url = _personio_text(pos, "url")
                if not url:
                    pid = _personio_text(pos, "id")
                    url = f"https://{slug}.jobs.personio.de/job/{pid}" if pid else ""

                # Build description from nested <jobDescription> blocks
                desc_parts: list[str] = []
                for jd in pos.find_all("jobDescription"):
                    section = _personio_text(jd, "name")
                    body = _personio_text(jd, "value")
                    if section:
                        desc_parts.append(section)
                    if body:
                        desc_parts.append(body)
                # Fallback: <recruitingCategory> or any <description>
                if not desc_parts:
                    fallback = (
                        _personio_text(pos, "description")
                        or _personio_text(pos, "subcompany")
                        or _personio_text(pos, "recruitingCategory")
                    )
                    if fallback:
                        desc_parts.append(fallback)
                desc_raw = "\n\n".join(desc_parts)
                # Strip nested HTML (Personio descriptions are often HTML inside XML)
                desc = BeautifulSoup(desc_raw, "html.parser").get_text(separator="\n")

                posted = _personio_text(pos, "createdAt") or _personio_text(pos, "createdDate")

                results.append(job(
                    title=title,
                    company=company_name,
                    location=location,
                    url=url,
                    source="Personio",
                    description=desc,
                    posted_at=posted,
                ))
            time.sleep(0.4)
        except Exception as e:
            print(f"  [Personio/{slug}] failed: {e}")
            continue

    print(f"  [Personio] {len(results)} jobs across {len(PERSONIO_SLUGS)} companies")
    return results


# ── 14. SmartRecruiters API (enterprise ATS) ─────────────────────────────────
# Used by Bosch, Continental, Visa, Roland Berger, and many other large
# industrial/consultancy employers. Public API, country pre-filter, no auth.

_SR_API = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
# Only run the SR scraper if a relevant role title or function. Postings list
# does NOT include the full description — that requires per-posting fetch.
# We keep description as the company industry + function as a stub; main.py
# filters and Claude will see title + this stub.

_SR_RELEVANT_KEYWORDS = (
    "data", "ai", "ml", "machine learning", "artificial intelligence",
    "scientist", "analyst", "intern", "praktikum", "research", "applied",
    "engineer", "developer", "software", "python", "junior", "graduate",
    "associate", "computer", "informatik",
)


def scrape_smartrecruiters() -> list[dict]:
    """
    Iterate SMARTRECRUITERS_SLUGS, fetch Germany-filtered postings, return jobs.
    Description is left as a short industry+function stub since fetching the
    full description per posting would be 5000+ extra HTTP calls (Bosch alone
    has 4641 postings before filtering).
    """
    results: list[dict] = []
    for slug in SMARTRECRUITERS_SLUGS:
        try:
            offset = 0
            company_total = 0
            while True:
                r = requests.get(
                    _SR_API.format(slug=slug),
                    params={
                        "country": "de",  # Germany at API level
                        "limit": 100,
                        "offset": offset,
                    },
                    timeout=15,
                )
                if r.status_code != 200:
                    break
                data = r.json()
                postings = data.get("content", []) or []
                if not postings:
                    break

                for p in postings:
                    title = p.get("name", "") or ""
                    title_low = title.lower()
                    # Pre-filter to AI/ML/data-relevant roles — Bosch has
                    # thousands of roles; we only want the relevant ones
                    if not any(k in title_low for k in _SR_RELEVANT_KEYWORDS):
                        continue

                    loc_obj = p.get("location", {}) or {}
                    location = (
                        loc_obj.get("fullLocation", "")
                        or ", ".join(filter(None, [
                            loc_obj.get("city", ""),
                            loc_obj.get("country", ""),
                        ]))
                        or "Germany"
                    )
                    pid = p.get("id", "")
                    url = f"https://jobs.smartrecruiters.com/{slug}/{pid}" if pid else ""

                    # Build description stub from available metadata
                    industry = (p.get("industry") or {}).get("label", "")
                    function = (p.get("function") or {}).get("label", "")
                    department = (p.get("department") or {}).get("label", "")
                    experience = (p.get("experienceLevel") or {}).get("label", "")
                    employment = (p.get("typeOfEmployment") or {}).get("label", "")
                    desc_parts = [
                        f"Industry: {industry}" if industry else "",
                        f"Function: {function}" if function else "",
                        f"Department: {department}" if department else "",
                        f"Experience level: {experience}" if experience else "",
                        f"Employment type: {employment}" if employment else "",
                        f"View full job: {url}" if url else "",
                    ]
                    desc = "\n".join(filter(None, desc_parts))

                    results.append(job(
                        title=title,
                        company=slug,
                        location=location,
                        url=url,
                        source="SmartRecruiters",
                        description=desc,
                        posted_at=p.get("releasedDate", "") or "",
                    ))
                    company_total += 1

                # Pagination
                if len(postings) < 100:
                    break
                offset += 100
                if offset >= 500:  # safety cap at 500 postings per company
                    break
                time.sleep(0.3)
            time.sleep(0.5)
        except Exception as e:
            print(f"  [SmartRecruiters/{slug}] failed: {e}")
            continue

    print(f"  [SmartRecruiters] {len(results)} relevant jobs across {len(SMARTRECRUITERS_SLUGS)} companies")
    return results


# ── 15. Workday CXS API (public POST endpoint) ───────────────────────────────
# Each Workday-using company exposes a hosted career site at
# {tenant}.wd{N}.myworkdayjobs.com/{site}. The page is backed by the CXS API:
#   POST  https://{host}/wday/cxs/{tenant}/{site}/jobs        — list jobs
#   GET   https://{host}/wday/cxs/{tenant}/{site}/job/{path}  — job detail
# Public, no auth. Tenant slug + Workday region (wd1, wd3, wd5, wd12) + site
# name vary per company and must be discovered manually (browser network tab).
# We pre-filter at title level to AI/ML/data-relevant roles before fetching
# the full description, otherwise tenants like NVIDIA (2000+ jobs) would
# spam ~50 description fetches per scrape.

_WD_AI_KEYWORDS = (
    "machine learning", "deep learning", "data scientist", "data science",
    "ml engineer", "ml ", "ai engineer", " ai ", "artificial intelligence",
    "applied scientist", "research scientist", "research engineer",
    "data engineer", "data analyst", "analytics", "nlp",
    "computer vision", "llm", "generative", "junior", "intern",
    "praktikum", "graduate", "associate", "entry level", "entry-level",
    "python developer", "ml ops", "mlops",
)

_WD_PAYLOAD = {
    "appliedFacets": {},
    "limit": 20,
    "offset": 0,
    "searchText": "",
}


def _wd_headers(host: str) -> dict:
    return {
        "User-Agent": HEADERS["User-Agent"],
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": f"https://{host}",
        "Referer": f"https://{host}/",
    }


def _wd_fetch_description(host: str, tenant: str, site: str, external_path: str) -> str:
    """
    Second-stage GET to pull the full job description.
    externalPath from the listing already starts with '/job/...', so the
    detail URL is just /wday/cxs/{tenant}/{site}{externalPath} — no extra
    /job/ prefix, that's how Workday wired it.
    """
    if not external_path:
        return ""
    if not external_path.startswith("/"):
        external_path = "/" + external_path
    detail_url = f"https://{host}/wday/cxs/{tenant}/{site}{external_path}"
    try:
        r = requests.get(detail_url, headers=_wd_headers(host), timeout=10)
        if r.status_code != 200:
            return ""
        info = (r.json().get("jobPostingInfo") or {})
        desc_html = info.get("jobDescription", "") or ""
        # Strip HTML, keep text
        return BeautifulSoup(desc_html, "html.parser").get_text(separator="\n").strip()
    except Exception:
        return ""


def scrape_workday_cxs() -> list[dict]:
    """
    Scrape Workday CXS endpoints (the modern JSON API). Distinct from the
    older `scrape_workday()` which scrapes HTML — that one mostly fails on
    JS-rendered career pages.
    """
    results: list[dict] = []
    for entry in WORKDAY_CXS_TENANTS:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3:
            continue
        tenant, region, site = entry
        host = f"{tenant}.{region}.myworkdayjobs.com"
        list_url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        per_tenant_fetched = 0
        per_tenant_added = 0
        offset = 0

        try:
            while offset < 200:  # safety cap: never walk past 200 postings per tenant
                payload = dict(_WD_PAYLOAD)
                payload["offset"] = offset
                payload["limit"] = 20
                r = requests.post(
                    list_url,
                    json=payload,
                    headers=_wd_headers(host),
                    timeout=15,
                )
                if r.status_code != 200:
                    break
                data = r.json()
                postings = data.get("jobPostings", []) or []
                if not postings:
                    break

                for jp in postings:
                    title = (jp.get("title") or "").strip()
                    if not title:
                        continue
                    title_low = title.lower()

                    # Pre-filter at title level to AI/ML/data-relevant only.
                    # NVIDIA has 2000 jobs total; we only want maybe 30 of them.
                    if not any(k in title_low for k in _WD_AI_KEYWORDS):
                        continue
                    # Cap at ~30 relevant jobs per tenant to keep scrape fast
                    if per_tenant_added >= 30:
                        break

                    location = (
                        jp.get("locationsText", "")
                        or (jp.get("locations") or [{}])[0].get("descriptor", "")
                        or ""
                    )
                    posted = jp.get("postedOn", "") or ""
                    external_path = jp.get("externalPath", "") or ""
                    job_url = f"https://{host}{external_path}" if external_path else list_url

                    # Pull full description (one extra GET per relevant job)
                    desc = _wd_fetch_description(host, tenant, site, external_path)
                    if not desc:
                        # Fallback stub if description fetch failed
                        desc = f"View full job on Workday: {job_url}"

                    results.append(job(
                        title=title,
                        company=tenant,
                        location=location,
                        url=job_url,
                        source="Workday-CXS",
                        description=desc,
                        posted_at=posted,
                    ))
                    per_tenant_added += 1
                    time.sleep(0.15)  # rate-limit description fetches

                per_tenant_fetched += len(postings)
                if per_tenant_added >= 30 or len(postings) < 20:
                    break
                offset += 20
                time.sleep(0.3)
        except Exception as e:
            print(f"  [WD-CXS/{tenant}] failed: {e}")
            continue

    print(f"  [WD-CXS] {len(results)} AI/ML-relevant jobs across {len(WORKDAY_CXS_TENANTS)} tenants")
    return results


# ── 16. Adzuna API (aggregator) ──────────────────────────────────────────────
# Adzuna aggregates German job postings from company career pages that are
# otherwise impossible to scrape directly (Mercedes-Benz, BMW, VW, Audi,
# Porsche, Allianz, Deutsche Bank, Bayer, BASF, Henkel, P&G, Unilever, etc.).
# They've solved the Cloudflare-protected SPA scraping problem; we consume
# their API.
#
# Free tier: 1000 calls/month, 50 results per call.
# Setup: sign up at https://developer.adzuna.com (5 min), add as GH secrets:
#   ADZUNA_APP_ID    = your application ID
#   ADZUNA_APP_KEY   = your API key
# If either secret is missing, this scraper is a graceful no-op.

_ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs/de/search/{page}"

# Search terms designed to maximise AI/ML/data coverage in DE
_ADZUNA_QUERIES = (
    "machine learning",
    "data scientist",
    "AI engineer",
    "data analyst",
    "applied scientist",
    "ML engineer",
    "data engineer",
    "Praktikum Data",
    "Praktikum KI",
    "Werkstudent AI",  # we drop these later but include for broader coverage
    "Junior Data",
    "Junior AI",
    "LLM engineer",
    "Python developer",
)


def scrape_adzuna() -> list[dict]:
    """
    Pull aggregated job listings from Adzuna for Germany. Adzuna indexes
    Mercedes, BMW, Allianz, Deutsche Bank, Bayer, P&G, Unilever, etc. that we
    can't reach via Greenhouse/Lever/Workday/SmartRecruiters.

    No-op if ADZUNA_APP_ID + ADZUNA_APP_KEY env vars (GH secrets) aren't set.
    """
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        print("  [Adzuna] ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping. "
              "Sign up at developer.adzuna.com (free) to enable.")
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    for query in _ADZUNA_QUERIES:
        try:
            r = requests.get(
                _ADZUNA_BASE.format(page=1),
                params={
                    "app_id":           app_id,
                    "app_key":          app_key,
                    "results_per_page": 50,
                    "what":             query,
                    "where":            "Deutschland",  # Germany
                    "max_days_old":     14,             # last 2 weeks only
                    "content-type":     "application/json",
                },
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                # Free tier rate limit hit, or auth error
                if r.status_code == 401:
                    print(f"  [Adzuna] 401 unauthorized — check APP_ID/APP_KEY")
                    return []
                if r.status_code == 429:
                    print(f"  [Adzuna] 429 rate limit hit on '{query}', stopping early")
                    break
                continue

            data = r.json()
            for posting in data.get("results", []) or []:
                url = posting.get("redirect_url", "") or posting.get("__CLASS__", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = posting.get("title", "") or ""
                # Adzuna strips HTML from descriptions for us
                description = posting.get("description", "") or ""
                company_obj = posting.get("company", {}) or {}
                company = company_obj.get("display_name", "") or "Unknown"
                location_obj = posting.get("location", {}) or {}
                # Use the most specific location available
                area = location_obj.get("area", []) or []
                location = ", ".join(area[1:]) if len(area) > 1 else location_obj.get("display_name", "Germany")
                posted = posting.get("created", "") or ""

                results.append(job(
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    source="Adzuna",
                    description=description,
                    posted_at=posted,
                ))
            time.sleep(0.5)  # be polite — free tier
        except Exception as e:
            print(f"  [Adzuna] query '{query}' failed: {e}")
            continue

    print(f"  [Adzuna] {len(results)} jobs across {len(_ADZUNA_QUERIES)} queries")
    return results


# ── 17. Ashby ATS (used by frontier AI startups: Perplexity, Deepgram, etc.) ─
# Public, no auth: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
# Response: top-level "jobs" array. Per-slug try/except so one bad slug
# never aborts the run.

def scrape_ashby() -> list[dict]:
    """
    Pull jobs from each company in ASHBY_SLUGS. Same Germany-eligibility logic
    as Greenhouse: keep Germany / Deutschland / remote / unknown; downstream
    filters in main.py make the final call.
    """
    results: list[dict] = []
    if not ASHBY_SLUGS:
        print("  [Ashby] no slugs configured — skipping")
        return results

    for slug in ASHBY_SLUGS:
        try:
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                params={"includeCompensation": "true"},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                print(f"  [Ashby/{slug}] HTTP {r.status_code}")
                continue
            data = r.json()
            per_slug = 0
            for jp in data.get("jobs", []) or []:
                if not jp.get("isListed", True):
                    continue

                title = (jp.get("title") or "").strip()
                if not title:
                    continue

                # Location signals — Ashby exposes location, isRemote, workplaceType
                location = jp.get("location") or ""
                is_remote = jp.get("isRemote") or jp.get("workplaceType") == "Remote"
                if is_remote and "remote" not in location.lower():
                    location = (location + " (Remote)").strip()

                # Same coarse filter as Greenhouse — keep DE / Deutschland /
                # Remote / Unknown. Downstream filter in main.py decides finally.
                loc_low = location.lower()
                if loc_low and not any(k in loc_low for k in (
                    "germany", "deutschland", "berlin", "munich", "münchen",
                    "hamburg", "frankfurt", "köln", "cologne", "düsseldorf",
                    "stuttgart", "bochum", "remote", "eu", "europe",
                )):
                    # Skip obviously non-EU specific cities; if location is
                    # empty/unknown we let it through.
                    if any(c in loc_low for c in (
                        "new york", "san francisco", "boston", "chicago",
                        "los angeles", "seattle", "austin", "denver",
                        "toronto", "vancouver", "sydney", "melbourne",
                        "tokyo", "singapore", "mumbai", "delhi", "bangalore",
                        "bengaluru", "são paulo", "bogotá", "mexico city",
                        "dubai", "nairobi", "lagos",
                    )):
                        continue

                desc = (jp.get("descriptionPlain") or "").strip()
                if not desc:
                    # Fall back to HTML description, strip tags
                    desc_html = jp.get("descriptionHtml") or jp.get("description") or ""
                    desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n").strip()
                url = jp.get("jobUrl") or jp.get("applyUrl") or ""
                posted = jp.get("publishedAt") or jp.get("updatedAt") or ""

                results.append(job(
                    title=title,
                    company=slug,
                    location=location or "Unknown",
                    url=url,
                    source="Ashby",
                    description=desc,
                    posted_at=posted,
                ))
                per_slug += 1
            if per_slug:
                print(f"  [Ashby/{slug}] {per_slug} jobs")
            time.sleep(0.3)
        except Exception as e:
            print(f"  [Ashby/{slug}] failed: {e}")
            continue

    print(f"  [Ashby] TOTAL {len(results)} jobs across {len(ASHBY_SLUGS)} companies")
    return results


# ── 18. Recruitee ATS (EU startups) ──────────────────────────────────────────
# Public, no auth: GET https://{slug}.recruitee.com/api/offers

def scrape_recruitee() -> list[dict]:
    """
    Pull jobs from each company in RECRUITEE_SLUGS. Same coarse Germany-
    eligibility filter as Ashby; downstream filters decide finally.
    """
    results: list[dict] = []
    if not RECRUITEE_SLUGS:
        print("  [Recruitee] no slugs configured — skipping")
        return results

    for slug in RECRUITEE_SLUGS:
        try:
            r = requests.get(
                f"https://{slug}.recruitee.com/api/offers",
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                print(f"  [Recruitee/{slug}] HTTP {r.status_code}")
                continue
            data = r.json()
            per_slug = 0
            for offer in data.get("offers", []) or []:
                title = (offer.get("title") or "").strip()
                if not title:
                    continue

                # Recruitee location can be in city/country fields or a
                # 'location' string. Try multiple.
                loc_parts = [
                    offer.get("city", "") or "",
                    offer.get("country", "") or "",
                ]
                location = ", ".join(p for p in loc_parts if p) or (offer.get("location") or "")
                loc_low = location.lower()
                # Drop obviously non-EU specific cities; unknown → keep.
                if loc_low and any(c in loc_low for c in (
                    "new york", "san francisco", "boston", "chicago",
                    "los angeles", "seattle", "toronto", "sydney",
                    "tokyo", "singapore", "mumbai", "bangalore",
                    "são paulo", "bogotá", "mexico city",
                )):
                    continue

                desc_html = offer.get("description") or offer.get("requirements") or ""
                desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n").strip()
                url = offer.get("careers_url") or offer.get("careers_apply_url") or ""
                posted = offer.get("created_at") or offer.get("published_at") or ""

                results.append(job(
                    title=title,
                    company=slug,
                    location=location or "Unknown",
                    url=url,
                    source="Recruitee",
                    description=desc,
                    posted_at=posted,
                ))
                per_slug += 1
            if per_slug:
                print(f"  [Recruitee/{slug}] {per_slug} jobs")
            time.sleep(0.3)
        except Exception as e:
            print(f"  [Recruitee/{slug}] failed: {e}")
            continue

    print(f"  [Recruitee] TOTAL {len(results)} jobs across {len(RECRUITEE_SLUGS)} companies")
    return results


# ── 19. germantechjobs.de RSS ────────────────────────────────────────────────
# Public, no auth: https://www.germantechjobs.de/rss
# Big German tech-jobs aggregator. Each <item> title is formatted as
# "{role} @ {company} [{salary range}]". We split on " @ " to lift the
# company out of the title. Feed is ~8 MB; we cap items processed.

_GERMANTECHJOBS_RSS = "https://www.germantechjobs.de/rss"


def _parse_gtj_title(raw: str) -> tuple[str, str]:
    """
    Split 'Role Title @ Company GmbH [salary range]' into (title, company).
    Falls back to (raw, '') if no ' @ ' separator.
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    # Strip trailing [salary] bracket
    bracket = raw.rfind("[")
    if bracket > 0 and raw.endswith("]"):
        raw = raw[:bracket].strip()
    # Split on " @ "
    if " @ " in raw:
        title, _, company = raw.rpartition(" @ ")
        return title.strip(), company.strip()
    return raw, ""


def scrape_germantechjobs() -> list[dict]:
    """
    Pull the germantechjobs.de RSS feed. Each <item> is a job posting with
    title, link, pubDate, and HTML description. No auth, no rate limit.
    """
    results: list[dict] = []
    try:
        r = requests.get(_GERMANTECHJOBS_RSS, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"  [GermanTechJobs] HTTP {r.status_code}, skipping")
            return results
        soup = BeautifulSoup(r.text, "xml")
        items = soup.find_all("item")
        # Cap at 300 items (most recent first) — keeps scrape time reasonable
        for item in items[:300]:
            raw_title = (item.find("title").text if item.find("title") else "").strip()
            title, company = _parse_gtj_title(raw_title)
            if not title:
                continue
            url = (item.find("link").text if item.find("link") else "").strip()
            posted = (item.find("pubDate").text if item.find("pubDate") else "").strip()
            desc_html = (item.find("description").text if item.find("description") else "")
            # Fall back to <content:encoded> for richer body if present
            encoded = item.find("encoded")
            if encoded and len(encoded.text) > len(desc_html):
                desc_html = encoded.text
            desc = BeautifulSoup(desc_html or "", "html.parser").get_text(separator="\n").strip()
            results.append(job(
                title=title,
                company=company or "GermanTechJobs",
                location="Germany",   # feed is Germany-focused by definition
                url=url,
                source="GermanTechJobs",
                description=desc,
                posted_at=posted,
            ))
    except Exception as e:
        print(f"  [GermanTechJobs] failed: {e}")
        return results
    print(f"  [GermanTechJobs] {len(results)} jobs from RSS")
    return results


# ── Main entry point ───────────────────────────────────────────────────────────

def scrape_all() -> list[dict]:
    print("Scraping all sources...")
    all_jobs: list[dict] = []

    for scraper in [
        scrape_jobspy,             # LinkedIn + Indeed
        scrape_arbeitnow,          # Free JSON API — English jobs, Germany-focused
        scrape_remotive,           # Free JSON API — remote jobs worldwide
        scrape_hn_who_is_hiring,   # HIDDEN GEM: HN monthly hiring thread (YC-heavy, low competition)
        scrape_arbeitsagentur,     # Official German employment agency API
        scrape_amazon,             # Amazon Jobs API (Germany filter at API level)
        scrape_personio,           # German Mittelstand + AI startups (20 companies)
        scrape_smartrecruiters,    # Bosch, Continental, Visa, Roland Berger
        scrape_workday_cxs,        # NVIDIA, Adobe, Salesforce, AstraZeneca, Pfizer, Sanofi, Intel, Philips, etc. (15 tenants)
        scrape_adzuna,             # Aggregator — Mercedes, BMW, Allianz, DB, P&G, Unilever, etc. (needs ADZUNA_APP_ID/KEY)
        scrape_workday,            # Legacy HTML scraper — kept for any URL it still works on
        scrape_successfactors,     # VW, Adidas, Porsche, etc.
        scrape_greenhouse,         # Zalando, DeepL, Delivery Hero, 108 companies
        scrape_lever,              # Mistral, Qonto, MoonPay, Neon, TrustYou, Nuri
        scrape_ashby,              # Perplexity, Deepgram, Ramp, Supabase, Linear, etc.
        scrape_recruitee,          # Limehome and other EU startups
        scrape_germantechjobs,     # germantechjobs.de RSS — German tech aggregator
        scrape_brave_search,       # Brave web search API
        scrape_web_search,         # DuckDuckGo web search
    ]:
        try:
            jobs = scraper()
            all_jobs.extend(jobs)
        except Exception:
            traceback.print_exc()

    # Deduplicate by job id
    seen_ids: set[str] = set()
    unique: list[dict] = []
    for j in all_jobs:
        if j["id"] not in seen_ids:
            seen_ids.add(j["id"])
            unique.append(j)

    print(f"Total unique jobs from all sources: {len(unique)}")
    return unique
