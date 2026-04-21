"""
scorer.py — uses Claude to score each job against Sherwan's CV profile.

Pipeline:
  1. _hard_disqualify()  — regex pre-screen, sets score=0, skips Claude API call
  2. _score_batch()      — Claude Haiku scores the remaining jobs in batches of 10
"""

import json
import os
import re
import time

import anthropic

from config import CV_PROFILE

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

BATCH_SIZE = 10

# ── Hard disqualifiers — checked BEFORE any Claude API call ───────────────────
# These patterns catch clear mismatches and set score=0 without spending tokens.

_RE_EXP = re.compile(
    r"\b([3-9]|\d{2})\+?\s*years?\s*(of\s*)?(professional\s*)?(work\s*)?experience"
    r"|\bminimum\s*(of\s*)?([3-9]|\d{2})\s*years?"
    r"|\bat\s+least\s+([3-9]|\d{2})\s*years?"
    r"|\b([3-9]|\d{2})\s*[-–]\s*\d+\s*years?\s*(of\s*)?experience"
    r"|\b([3-9]|\d{2})\+\s*years?",
    re.IGNORECASE,
)

# Non-Python primary language signals in the JOB TITLE
_RE_NONPY_TITLE = re.compile(
    r"\b("
    r"golang|go\s+(developer|engineer|backend|programmer)|"
    r"rust\s+(developer|engineer|programmer)|"
    r"java\s+(developer|engineer|backend|programmer)|"   # NOT javascript
    r"c\+\+\s*(developer|engineer|programmer|specialist)|"
    r"embedded\s+c\b|"
    r"\.net\s+(developer|engineer|programmer)|"
    r"scala\s+(developer|engineer)|"
    r"kotlin\s+(developer|engineer)"
    r")\b",
    re.IGNORECASE,
)

# Non-Python keywords that appear anywhere (description), paired with absence of Python
_NONPY_DESC_SIGNALS = ("golang", "typescript developer", "typescript engineer",
                        "rust developer", "rust engineer")

# Wrong domain — completely different field
_RE_BAD_DOMAIN = re.compile(
    r"\b("
    r"embedded\s+systems?|tinyml|tiny\s*ml|fpga|microcontroller|"
    r"firmware\s+(developer|engineer)|vhdl|verilog|"
    r"hardware\s+(developer|engineer|design)|"
    r"biomedical\s+(engineer|scientist)|medical\s+device|"
    r"clinical\s+trial|histopath|patholog|radiology|oncolog|"
    r"laboratory\s+information|pharma\s+(engineer|developer)|"
    r"embedded\s+(linux|software|developer|engineer)"
    r")\b",
    re.IGNORECASE,
)

# Freelance / contractor-only signals
_RE_FREELANCE_TITLE = re.compile(
    r"\b(freelance|freelancer|freiberuflich)\b", re.IGNORECASE
)
_RE_FREELANCE_DESC = re.compile(
    r"\b("
    r"freelance\s+only|freelancer\s+only|contractors?\s+only|"
    r"contract\s+only|self.?employed|auf\s+freiberuflicher\s+basis|"
    r"als\s+freelancer|no\s+permanent"
    r")\b",
    re.IGNORECASE,
)

# Web analytics focus — GA4, tag management, etc.
_RE_WEB_ANALYTICS = re.compile(
    r"\b("
    r"ga4|google\s+analytics\s+4|looker\s+studio|econda|"
    r"tag\s+management|google\s+tag\s+manager|\bgtm\b|"
    r"adobe\s+analytics|piano\s+analytics|web\s+tracking|"
    r"tracking\s+pixel|conversion\s+tracking|matomo|"
    r"tag\s+implementation"
    r")\b",
    re.IGNORECASE,
)

# ML/AI signals — if present alongside web analytics, keep the job
_RE_ML_SIGNALS = re.compile(
    r"\b("
    r"machine\s+learning|deep\s+learning|neural\s+network|"
    r"data\s+science|large\s+language|llm|\bnlp\b|computer\s+vision|"
    r"model\s+train|pytorch|tensorflow|scikit|xgboost|langchain"
    r")\b",
    re.IGNORECASE,
)

# Non-Germany locations (in-person signals — remote overrides this)
_RE_NONGER_LOC = re.compile(
    r"\b("
    r"london|manchester|birmingham|paris|milan|rome|madrid|barcelona|"
    r"amsterdam|new\s+york|san\s+francisco|seattle|boston|chicago|"
    r"toronto|sydney|melbourne|dubai|singapore|hong\s+kong|"
    r"united\s+states\b|united\s+kingdom\b"
    r")\b",
    re.IGNORECASE,
)


def _hard_disqualify(j: dict) -> tuple[bool, str]:
    """
    Run hard pre-screening checks.
    Returns (True, reason) → score=0, skip Claude.
    Returns (False, "")   → proceed to Claude scoring.
    """
    title   = (j.get("title")       or "")
    desc    = (j.get("description") or "")
    loc     = (j.get("location")    or "")
    t_low   = title.lower()
    d_low   = desc.lower()
    combined = f"{t_low} {d_low}"

    # 1. Experience requirement ≥ 3 years
    if _RE_EXP.search(d_low):
        return True, "Requires 3+ years experience"

    # 2. Non-Python primary language
    if _RE_NONPY_TITLE.search(title) and "python" not in combined:
        return True, "Primary language is not Python (no Python mentioned)"
    for signal in _NONPY_DESC_SIGNALS:
        if signal in combined and "python" not in combined:
            return True, f"Primary language appears non-Python ({signal})"

    # 3. Wrong domain
    if _RE_BAD_DOMAIN.search(combined):
        return True, "Wrong domain (embedded / hardware / biomedical / pharma)"

    # 4. Location clearly outside Germany with no remote signal
    loc_low = loc.lower()
    if _RE_NONGER_LOC.search(loc_low):
        if "remote" not in loc_low and "remote" not in d_low[:600]:
            return True, "Location is not Germany-commutable and not remote"

    # 5. Freelance / contractor only
    if _RE_FREELANCE_TITLE.search(title):
        return True, "Freelance role — seeking permanent/fixed-term employment"
    if _RE_FREELANCE_DESC.search(d_low):
        return True, "Contractor/freelance only — not permanent employment"

    # 6. Web analytics primary focus without any ML/AI component
    if _RE_WEB_ANALYTICS.search(combined):
        if not _RE_ML_SIGNALS.search(combined) and "python" not in combined:
            return True, "Primary focus is web analytics (GA4/tag management), not ML/AI"

    return False, ""

SYSTEM_PROMPT = f"""You are a strict job-matching assistant. Score each job 0-100 against the candidate profile below.

Scoring guide:
- 85-100: Excellent - role maps directly to target titles, skills match, location fine
- 70-84:  Good - most criteria align, minor gaps
- 55-69:  Decent - worth applying, some gaps
- 40-54:  Weak - meaningful mismatch in stack or seniority
- 0-39:   Poor - wrong field, wrong stack, or wrong seniority

CANDIDATE PROFILE:
{CV_PROFILE}

TARGET ROLES — if a role does not map to one of these, cap score at 45:
  Junior ML Engineer | AI Engineer | Data Scientist | Applied AI | LLM / Agent Systems Engineer

HARD PENALTIES — apply these first, they override everything else:
- PENALISE (-40) roles requiring 3+ years professional experience — candidate has under 1 year
- PENALISE (-35) roles where the PRIMARY stack is non-Python (Go, Rust, Java, C++, .NET, Scala) with no Python mentioned — candidate cannot do these
- PENALISE (-35) wrong domain: embedded systems, TinyML, hardware engineering, biomedical, pharma, radiology — completely different field
- PENALISE (-30) freelance or contractor-only with no permanent option
- PENALISE (-30) web analytics primary focus (GA4, Looker Studio, tag management, Econda) with no ML/AI component
- PENALISE (-25) strictly requires Master's/PhD with no Bachelor's alternative — candidate has B.Sc. in progress
- PENALISE (-20) Senior, Lead, Head, Principal, Director, Staff Engineer titles

STACK AND DOMAIN PENALTIES:
- PENALISE (-20) DevOps / platform engineering primary focus (Kubernetes, Terraform, CI/CD, infrastructure) — candidate is not a DevOps engineer
- PENALISE (-15) data engineering primary focus (Spark, Kafka, Airflow, dbt pipelines) with no ML component
- PENALISE (-10) domain-specific hard requirements candidate clearly lacks (pharma regulatory, medical imaging, financial risk, supply chain optimisation)

BOOSTS:
- BOOST (+15) Junior, Entry-level, Graduate, Associate, Internship/Praktikum in ML/AI/Data Science
- BOOST (+12) role explicitly mentions Python, PyTorch, scikit-learn, LangChain, RAG, LLMs, or AI agents
- BOOST (+10) LLM engineering, AI agents, prompt engineering, GenAI — candidate builds these at iseremo GmbH
- BOOST (+5) NRW cities (Bochum, Dusseldorf, Cologne, Dortmund, Essen) or fully remote within Germany
- NEUTRAL — all other German cities (Berlin, Munich, Hamburg, Frankfurt) — acceptable, no penalty
- NEUTRAL — Werkstudent roles — candidate legally cannot work Werkstudent, do not boost

LANGUAGE:
- BOOST (+8) English-speaking team / working language English / job posted in English
- NEUTRAL for B1/B2 German
- PENALISE (-20) C1/C2 German required, "verhandlungssicheres Deutsch", or fully German posting with no English mention

Respond ONLY with a valid JSON array. No preamble, no markdown fences.
"""

USER_TEMPLATE = """Score these {n} jobs. Return a JSON array with one object per job in the same order:
[{{"index": 0, "score": 75, "reason": "one-line reason"}}, ...]

JOBS:
{jobs_block}"""


def _format_job_block(jobs: list[dict]) -> str:
    lines = []
    for i, j in enumerate(jobs):
        lines.append(
            f"[{i}] Title: {j['title']}\n"
            f"    Company: {j['company']}\n"
            f"    Location: {j['location']}\n"
            f"    Description snippet: {j['description'][:400] or 'N/A'}"
        )
    return "\n\n".join(lines)


def _score_batch(batch: list[dict]) -> list[dict]:
    jobs_block = _format_job_block(batch)
    prompt = USER_TEMPLATE.format(n=len(batch), jobs_block=jobs_block)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        scores = json.loads(raw)
        for item in scores:
            idx = item["index"]
            if 0 <= idx < len(batch):
                batch[idx]["score"] = item.get("score", 0)
                batch[idx]["reason"] = item.get("reason", "")
        return batch

    except Exception as e:
        print(f"  [Scorer] batch failed: {e}")
        # Return batch with score 0 so they're still deduplicated
        return batch


def score_jobs(jobs: list[dict]) -> list[dict]:
    print(f"Scoring {len(jobs)} jobs...")

    # ── Stage 1: hard pre-screening (no Claude API call) ──────────────────────
    to_score: list[dict] = []
    prescreened_out = 0
    for j in jobs:
        disqualified, reason = _hard_disqualify(j)
        if disqualified:
            j["score"] = 0
            j["reason"] = f"[Pre-screened] {reason}"
            prescreened_out += 1
        else:
            to_score.append(j)

    print(f"  Pre-screened out: {prescreened_out} | Sending to Claude: {len(to_score)}")

    # ── Stage 2: Claude scoring for remaining jobs ─────────────────────────────
    scored = []
    for i in range(0, len(to_score), BATCH_SIZE):
        batch = to_score[i : i + BATCH_SIZE]
        result = _score_batch(batch)
        scored.extend(result)
        time.sleep(1)
        print(f"  Scored {min(i + BATCH_SIZE, len(to_score))}/{len(to_score)}")

    # Merge Claude-scored jobs with pre-screened (score=0) jobs
    scored_ids = {j["id"] for j in scored}
    all_results = scored + [j for j in jobs if j["id"] not in scored_ids]
    return all_results
