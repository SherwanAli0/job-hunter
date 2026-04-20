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
    COMPANY_PAGES,
    GREENHOUSE_SLUGS,
    LEVER_SLUGS,
    LOCATION,
    SEARCH_QUERIES,
)

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


def job(title, company, location, url, source, description=""):
    return {
        "id": make_id(url, title, company),
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "source": source,
        "description": description[:2000],  # cap size for Claude
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
                    hours_old=24,
                    country_indeed="Germany",
                )
                for _, row in df.iterrows():
                    url = str(row.get("job_url", "")) or str(row.get("url", ""))
                    if not url:
                        continue
                    results.append(job(
                        title=str(row.get("title", "")),
                        company=str(row.get("company", "")),
                        location=str(row.get("location", "")),
                        url=url,
                        source=str(row.get("site", "jobspy")),
                        description=str(row.get("description", "")),
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
                results.append(job(title, company, location, url, "Arbeitnow", description))

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
                    results.append(job(title, company, location, url, "Remotive", description))
            time.sleep(1)
    except Exception as e:
        print(f"  [Remotive] failed: {e}")
    print(f"  [Remotive] {len(results)} jobs")
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

                # Only include Germany-based roles (or remote)
                loc_lower = location.lower()
                if "germany" in loc_lower or "deutschland" in loc_lower or "remote" in loc_lower or not location:
                    results.append(job(title, slug.title(), location, url, "Greenhouse", description))
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
                results.append(job(title, slug.title(), location, url, "Lever", description))
            time.sleep(1)
        except Exception:
            continue
    print(f"  [Lever] {len(results)} jobs")
    return results


# ── 6. Company career pages (generic HTML) ────────────────────────────────────

def scrape_company_page(company_cfg: dict[str, Any]) -> list[dict]:
    results = []
    name = company_cfg["name"]
    url = company_cfg["url"]
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        # Generic heuristic: look for job-like links
        job_links = soup.select(
            "a[href*='job'], a[href*='career'], a[href*='position'], "
            "a[href*='stelle'], a[href*='vacancy']"
        )
        seen_titles = set()
        for link in job_links[:30]:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or len(title) < 5 or len(title) > 120:
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            job_url = href if href.startswith("http") else f"https://{url.split('/')[2]}{href}"
            results.append(job(title, name, "Germany", job_url, name))
    except Exception as e:
        print(f"  [{name}] failed: {e}")
    return results


def scrape_company_pages() -> list[dict]:
    results = []
    for cfg in COMPANY_PAGES:
        jobs = scrape_company_page(cfg)
        results.extend(jobs)
        time.sleep(1)
    print(f"  [Company pages] {len(results)} jobs")
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
            time.sleep(1)
        except Exception:
            continue
    print(f"  [Workday] {len(results)} jobs")
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

                results.append(job(
                    title=title,
                    company=company,
                    location="Germany",
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
        results.append(job(
            title=title,
            company=company,
            location="Germany",
            url=url,
            source="WebSearch",
            description=description,
        ))
        time.sleep(1)  # be polite

    print(f"  [WebSearch] {len(results)} jobs with full descriptions")
    return results


# ── Main entry point ───────────────────────────────────────────────────────────

def scrape_all() -> list[dict]:
    print("Scraping all sources...")
    all_jobs: list[dict] = []

    for scraper in [
        scrape_jobspy,          # LinkedIn + Indeed
        scrape_arbeitnow,       # Free JSON API — English jobs, Germany-focused
        scrape_remotive,        # Free JSON API — remote jobs worldwide
        scrape_arbeitsagentur,  # Official German employment agency API
        scrape_workday,         # BMW, Siemens, Bosch, SAP, etc.
        scrape_successfactors,  # VW, Adidas, Porsche, etc.
        scrape_greenhouse,      # Zalando, DeepL, Delivery Hero, etc.
        scrape_lever,           # HelloFresh, etc.
        scrape_company_pages,   # Direct career pages
        scrape_brave_search,    # Brave web search API
        scrape_web_search,      # DuckDuckGo web search
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
