"""
scorer.py — uses Claude to score each job against Sherwan's CV profile.

Batches jobs into groups of 10 to stay within context limits and reduce API cost.
Each job gets a score 0–100 and a one-line reason.
"""

import json
import os
import time

import anthropic

from config import CV_PROFILE

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

BATCH_SIZE = 10

SYSTEM_PROMPT = f"""You are a job-matching assistant. Given a candidate profile and a list of job listings,
score each job from 0 to 100 for how well it matches the candidate.

Scoring guide:
- 85–100: Excellent match — role fits skills, seniority, and location perfectly
- 70–84:  Good match — most criteria align, minor gaps
- 55–69:  Decent match — worth applying, some gaps
- 40–54:  Weak match — significant mismatch in skills or seniority
- 0–39:   Poor match — wrong field, country, or seniority level

CANDIDATE PROFILE:
{CV_PROFILE}

Rules:
- BOOST Junior, Entry-level, Graduate, Associate, and Internship (Praktikum) roles
- Candidate CANNOT work as Werkstudent (not enrolled at German university) — do NOT boost Werkstudent roles
- PENALISE (-30) roles requiring 3+ years of experience
- PENALISE (-25) roles that strictly require a Master's degree (MSc/MA) with no Bachelor's alternative — candidate has B.Sc. in progress (graduating June 2026)
- PENALISE (-20) Senior, Lead, Head, Principal, Director titles
- NEUTRAL or slight boost for roles that accept Bachelor's or equivalent
- All German cities are acceptable (Berlin, Munich, Hamburg, Frankfurt, Stuttgart, Cologne, etc.) — do NOT penalise any German location
- Slight boost for NRW (Düsseldorf, Cologne, Dortmund, Essen, Bochum) and remote/hybrid since candidate is based in Bochum
- Boost fully remote and hybrid roles — candidate can work anywhere in Germany
- Boost roles with Python, ML, data science, AI, LLM, NLP keywords
- Penalise roles in non-German-speaking countries (unless fully remote)
- LANGUAGE — this is the most important scoring factor:
  * BOOST (+15) roles that explicitly say "English-speaking team", "working language is English", "English is a must", or the job posting is written in English
  * NEUTRAL for roles that say B1/B2 German is sufficient
  * PENALISE (-20) roles that require C1/C2 German, "verhandlungssicheres Deutsch", "fließende Deutschkenntnisse", or where the job posting is entirely in German with no mention of English being acceptable
  * If unclear, assume international/tech companies are English-friendly and do not penalise
- Respond ONLY with a valid JSON array. No preamble, no markdown fences.
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
    print(f"Scoring {len(jobs)} jobs with Claude...")
    scored = []
    for i in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[i : i + BATCH_SIZE]
        result = _score_batch(batch)
        scored.extend(result)
        time.sleep(1)  # gentle rate limiting
        print(f"  Scored {min(i + BATCH_SIZE, len(jobs))}/{len(jobs)}")
    return scored
