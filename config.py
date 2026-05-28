# ─────────────────────────────────────────────
#  config.py  —  edit this file to customise
# ─────────────────────────────────────────────

# ── Your CV profile (used by Claude for scoring) ──────────────────────────────
CV_PROFILE = """
Name: Sherwan Ali
Location: Bochum, Germany | Full work authorisation (valid residence permit)
Availability: Currently interning at iseremo GmbH (Apr 2026–present). Open to internships now and full-time from July 2026.
NOT eligible for Werkstudent — not enrolled at a German university.
Target roles: Junior AI Engineer, Junior ML Engineer, Junior Data Scientist, LLM Engineer, Data Analyst, AI Internship

LANGUAGE REQUIREMENT (critical for scoring):
- English: C1 — STRONGLY prefer English-speaking roles or teams
- German: B1 — can work in German-light environments but NOT suited for roles requiring fluent/advanced German
- PENALISE roles requiring C1/C2 German or "verhandlungssicheres Deutsch"
- Turkish: C1, Arabic: Native, Kurdish: Native

Education:
- B.Sc. Computer Engineering, Üsküdar University, Istanbul (GPA 3.41/4.00, graduating June 2026)
- Focus: AI, Machine Learning, Data Analytics
- Coursework: Machine Learning, Deep Learning, Database Systems, Statistics, Data Mining, Linear Algebra, Computer Vision

Technical Skills:
- Programming: Python (advanced), SQL, JavaScript, Excel
- AI & LLMs: LLMs, RAG, LangChain, Prompt Engineering, Agent Workflows, LLM Evaluation, Fine-tuning
- ML: Classification, Regression, Neural Networks, CNNs, Transformers, Hyperparameter Tuning, Imbalanced Learning
- Libraries & Frameworks: PyTorch, TensorFlow, Keras, scikit-learn, XGBoost, Pandas, NumPy, React, Node.js
- Infrastructure & Tools: Git, GitHub Actions, Docker, REST APIs, Web Scraping, VS Code, Jupyter Notebooks

Work Experience:
- Software & AI Intern, iseremo GmbH, Düsseldorf (Apr 2026 – Present):
  Building LLM-powered chatbot and AI agent systems end-to-end; owns prompting strategies, tool integrations,
  and agent workflows. Designs evaluation and testing frameworks for AI systems. Works full-stack: databases,
  backend logic, web development.
- IT Support & Website Management Intern, Salam Institute for Peace and Justice (Dec 2024 – Aug 2025, Remote):
  Led WordPress migration, built vendor evaluation framework covering 15+ firms, translated business
  requirements into technical specifications, trained non-technical staff.

Key Projects:
- Forensic Audit of CSRBoost — Graduation Thesis (solo) (Python, scikit-learn, PyTorch, imbalanced-learn):
  Reverse-engineered Yadav et al. (IEEE Access 2025) over 3 months, ~75,000 configurations, 900+ compute-hours.
  Mathematically proved the published Table 2 cannot come from any single coherent ML pipeline. Documented
  eight per-cell undocumented evaluation choices behind 143 of 143 reproduced metrics including test-set
  leakage on GAN-family methods, mid-table F1-averaging substitution, sub-zero AP thresholds, AP polarity
  inversion. github.com/SherwanAli0/csrboost-audit
- FUS Recommender System Replication — 4-author team (Python, NumPy, scikit-learn, GitHub Actions):
  Replicated D'Aniello et al. (IEEE Access 2026) on MovieLens 100k under 10-fold cross-validation. Owned FUS
  and CF implementations end-to-end. Reproduced FUS > CF > GIM > PF ordering; MAE_users at k=50 matched
  paper to four decimals (0.7025 vs 0.703). Co-designed 12-test CI suite on GitHub Actions.
  github.com/SherwanAli0/Recommender-System-Paper-Replication
- Daily AI-Powered Job Hunter — solo (Python, GitHub Actions, Anthropic API, Greenhouse/Lever APIs):
  Built and shipped end-to-end automated job matching system. Scrapes Greenhouse, Lever, plus 15+ German
  company career pages including Zalando, DeepL, SAP, Siemens, BMW, Bosch, Celonis. Claude scoring 0–100;
  daily Notion + email digest at 7AM via GitHub Actions. ~50–100 jobs/day at under €0.10/day.
  github.com/SherwanAli0/job-hunter
- AI-Powered German Language Learning App — solo (React, Vite, Tailwind, Zustand, Node.js, Anthropic API):
  Full-stack language learning app: React + Vite frontend, Node.js proxy backend, live LLM integration.
  Prompt-engineering patterns for contextual exercises, adaptive feedback, dynamic difficulty.
  github.com/SherwanAli0/German-App

Certifications:
- IBM AI Engineering Professional Certificate (Sep 2025) — 13 courses: ML, Deep Learning, CV, Transformers,
  LLM fine-tuning, RAG, LangChain
- Google Advanced Data Analytics Professional Certificate (Mar 2026) — statistics, regression, ML, Tableau
- Databases and SQL for Data Science with Python — IBM/Coursera (Apr 2026)
"""

# ── Search queries sent to job boards ─────────────────────────────────────────
# Curated list — every query targets a role Sherwan's CV qualifies him for.
# Data Analyst queries removed: pull in too many off-target roles for an AI/ML CV.
SEARCH_QUERIES = [
    "Junior AI Engineer Germany English",
    "Junior ML Engineer Germany English",
    "Junior Data Scientist Germany English",
    "AI Engineer LLM Germany English",
    "LLM Engineer Germany English",
    "GenAI Engineer Germany English",
    "AI Agent Engineer Germany English",
    "Applied AI Engineer Germany English",
    # Internships are OK — they're employment, not student-status-dependent
    "AI Internship Germany English",
    "ML Internship Germany English",
    "Graduate Data Scientist Germany English",
    "Graduate ML Engineer Germany English",
    "Junior Data Scientist Berlin English",
    "Junior ML Engineer Berlin English",
    "AI Engineer Berlin English",
    "Junior ML Engineer NRW English",
    "AI Engineer Düsseldorf English",
    "Remote AI Engineer Germany English",
    "Remote LLM Engineer Europe English",
]

LOCATION = "Germany"

# Minimum Claude score (0–100) to include a job in the digest.
# 45 is the cutoff for "borderline worth looking at" — anything below is a
# weak/long-shot match. The notifier tiers the digest into bands:
#   70-100 → "Apply now"  (Band A)
#   55-69  → "Worth a look"  (Band B)
#   45-54  → "Long shots"  (Band C — collapsed at the bottom)
# Pre-screened jobs (Werkstudent, fluent-German, 5+ years exp, senior title,
# etc.) get score=0 and are excluded by the >=45 cutoff.
MIN_SCORE = 45

# Per-band caps for email size (no more global MAX_RESULTS truncation that
# silently hid borderline matches).
BAND_A_MAX = 20   # high-confidence — always show
BAND_B_MAX = 20
BAND_C_MAX = 15

# Legacy alias retained for any code still importing MAX_RESULTS.
MAX_RESULTS = BAND_A_MAX + BAND_B_MAX + BAND_C_MAX

# ── Companies with Greenhouse JSON API (free, no scraping needed) ──────────────
# Add more slugs from: boards-api.greenhouse.io/v1/boards/{SLUG}/jobs
# Verified: each slug returned 200 OK with > 0 jobs at time of addition.
# Location filter (_is_attendable_from_germany) drops anything that isn't
# Germany on-site / hybrid / EU-wide remote, so US-only roles auto-drop.
GREENHOUSE_SLUGS = [
    # ── German tech / e-commerce (original list)
    "zalando", "deepl", "deliveryhero", "cognigy", "n26", "sumup",
    "personio", "celonis", "biontech", "flixbus", "zattoo", "razor-group",
    # ── German / EU AI-first startups (verified)
    "parloa",          # 58 jobs, conversational AI agents
    "helsing",         # 105 jobs, defence AI
    "blackforestlabs", # 12 jobs, image generation (FLUX)
    "traderepublic",   # fintech with AI/data work
    "raisin",          # 49 jobs, Berlin fintech
    # ── Top AI/ML labs hiring EU-remote
    "anthropic",       # 397 jobs
    "scaleai",         # 180 jobs
    "togetherai",      # 54 jobs
    "snorkelai",       # 48 jobs
    "stabilityai",     # 12 jobs
    "labelbox",        # 10 jobs
    # ── Data & infra giants with EU hiring
    "databricks",      # 785 jobs (huge ML hiring)
    "mongodb",         # 415 jobs
    "datadog",         # 406 jobs
    "elastic",         # 152 jobs, Berlin office
    "grafanalabs",     # 152 jobs
    "cloudflare",      # 144 jobs
    "fastly",          # 67 jobs
    "newrelic",        # 78 jobs
    "sumologic",       # 47 jobs
    "honeycomb",       # 12 jobs
    "planetscale",     # 5 jobs
    "vercel",          # 78 jobs
    # ── Berlin / EU consumer & SaaS using Greenhouse
    "contentful",      # 102 jobs, Berlin tech
    "scout24",         # 37 jobs, Berlin
    "freenow",         # 63 jobs, mobility (Berlin/Hamburg)
    "wolt",            # 286 jobs, EU food delivery
    "konux",           # 1 job, Munich industrial AI
    "adahealth",       # 2 jobs, Berlin health AI
    "isaraerospace",   # 96 jobs, Munich rocket startup with heavy ML
    # ── International ML-heavy companies (will hit our EU filter)
    "stripe",          # 478 jobs
    "hellofresh",      # 396 jobs (Berlin HQ — moved from LEVER_SLUGS, more jobs here)
    "okta",            # 370 jobs
    "verkada",         # 301 jobs
    "lucidmotors",     # 261 jobs
    "remotecom",       # 253 jobs
    "coreweave",       # 248 jobs, GPU cloud — direct AI/ML fit
    "adyen",           # 248 jobs
    "brex",            # 237 jobs
    "airbnb",          # 234 jobs
    "xai",             # 221 jobs, Elon's AI
    "doctolib",        # 213 jobs, EU health
    "gitlab",          # 173 jobs (remote-first)
    "intercom",        # 168 jobs
    "block",           # 168 jobs (Square's parent)
    "pinterest",       # 162 jobs
    "twilio",          # 156 jobs
    "reddit",          # 153 jobs
    "fivetran",        # 136 jobs
    "asana",           # 136 jobs
    "robinhood",       # 134 jobs
    "lyft",            # 125 jobs
    "smartsheet",      # 124 jobs
    "instacart",       # 124 jobs
    "postman",         # 118 jobs
    "flexport",        # 97 jobs
    "psiquantum",      # 85 jobs, quantum
    "dialpad",         # 82 jobs
    "tripadvisor",     # 79 jobs
    "discord",         # 77 jobs
    "gusto",           # 74 jobs
    "monzo",           # 68 jobs, UK neobank
    "amplitude",       # 66 jobs
    "getyourguide",    # 65 jobs, Berlin
    "mercury",         # 56 jobs, fintech
    "carta",           # 56 jobs
    "cabify",          # 56 jobs
    "tailscale",       # 50 jobs
    "launchdarkly",    # 49 jobs
    "autoscout24",     # 41 jobs, Berlin
    "immoscout24",     # 39 jobs, Berlin
    "bird",            # 37 jobs
    "lucidsoftware",   # 37 jobs
    "project44",       # 37 jobs, logistics ML
    "mixpanel",        # 37 jobs
    "calendly",        # 21 jobs
    "skyscanner",      # 20 jobs
    "stockx",          # 20 jobs
    "tomorrow",        # 16 jobs, Berlin neobank
    "dominodatalab",   # 13 jobs
    "wunderkind",      # 12 jobs
    "wallapop",        # 11 jobs
    "bitwarden",       # 8 jobs
    "buynomics",       # 8 jobs, Cologne pricing AI
    "watershed",       # 8 jobs, climate tech
    "trivago",         # 7 jobs, Düsseldorf
    "inflectionai",    # 6 jobs
    "public",          # 5 jobs
    "warp",            # 5 jobs, AI terminal
    "lattice",         # 3 jobs
    "mercari",         # 3 jobs
    "solarisbank",     # 3 jobs, Berlin BaaS
    "netlify",         # 2 jobs
    "kayak",           # 1 job
    "lottoland",       # 1 job
    "medium",          # 1 job
    # NOTE: aleph-alpha, deepset, n8n, langfuse, huggingface, cohere, kontist,
    # tier-mobility, wandelbots, 1komma5grad, pigment, circula, enpal,
    # paretos, otto, mediamarkt, klarna, statista, babbel, revolut, wise all
    # 404 on Greenhouse — they use other ATSs (Lever, Workable, Personio,
    # custom). See LEVER_SLUGS below for the ones found on Lever.
]

# ── Companies with Lever JSON API (free, no scraping needed) ──────────────────
# Verified: each slug returned 200 OK with > 0 jobs at time of addition.
# NOTE: hellofresh moved to GREENHOUSE_SLUGS (396 jobs there vs Lever).
LEVER_SLUGS = [
    "nuri",
    "mistral",         # 161 jobs, top AI lab — Paris, EU-hires
    "qonto",           # 35 jobs, French fintech, EU remote
    "moonpay",         # 24 jobs, fintech / crypto
    "neon",            # 14 jobs, Postgres-as-a-service
    "trustyou",        # 5 jobs, Munich travel tech
]

# ── Companies with Personio public XML feeds ──────────────────────────────────
# Personio is the German Mittelstand's HR system. Each company exposes
# {slug}.jobs.personio.de/xml as a public feed (no auth, full descriptions).
# These are companies that 404 on Greenhouse — Personio catches them.
# Verified: each returned 200 OK with > 0 positions.
PERSONIO_SLUGS = [
    "1komma5grad",     # 352 positions, solar/energy AI
    "westwing",        # 61, e-commerce
    "vivid",           # 19, Berlin fintech
    "merantix",        # 19, Berlin AI venture studio
    "pitch",           # 10, presentation SaaS
    "verivox",         # 9, comparison platform
    "deepset",         # 6, RAG / search AI
    "horizn-studios",  # 5, travel goods
    "snocks",          # 5
    "circula",         # 4, expense management
    "celonis",         # 3, process mining (also on Greenhouse)
    "wandelbots",      # 3, Dresden industrial robotics
    "candis",          # 3, fintech
    "audibene",        # 2, healthtech
    "limehome",        # 2, hospitality
    "finway",          # 2, fintech
    "penta",           # 1, banking
    "smava",           # 2, loan platform
    "personio",        # 1
    "ada",             # 1
]

# ── Workday CXS tenants (modern JSON API) ─────────────────────────────────────
# Each tuple: (tenant_slug, workday_region, site_name)
# Discovered manually by HTTP-testing — these all return 200 OK with jobs.
# The scraper pre-filters titles to AI/ML/data-relevant before fetching the
# full description per posting (cap 30 per tenant for sane runtime).
#
# NOTE: I tested ~50 candidate German DAX companies (Mercedes-Benz, BMW, VW,
# Audi, Porsche, Bayer, BASF, Henkel, Allianz, Deutsche Bank, Commerzbank,
# Lufthansa, Vodafone, Deutsche Telekom). NONE of them returned data via
# Workday — they either use SuccessFactors or their own bespoke ATS. The
# entries below are companies that DO work and have major German offices.
WORKDAY_CXS_TENANTS = [
    # (tenant, region, site_name) — total raw jobs at verification time
    ("nvidia",      "wd5",  "NVIDIAExternalCareerSite"),   # 2000  jobs — Munich office
    ("abbott",      "wd5",  "abbottcareers"),              # 2000  jobs — Wiesbaden
    ("citi",        "wd5",  "2"),                          # 2000  jobs — Frankfurt
    ("astrazeneca", "wd3",  "Careers"),                    # 1585  jobs — Wedel/Hamburg
    ("sanofi",      "wd3",  "SanofiCareers"),              # 1473  jobs — Frankfurt
    ("salesforce",  "wd12", "External_Career_Site"),       # 1441  jobs — Munich/Berlin
    ("adobe",       "wd5",  "external_experienced"),       # 1193  jobs — Hamburg/Munich
    ("philips",     "wd3",  "jobs-and-careers"),           # 1026  jobs — Hamburg/Aachen
    ("kone",        "wd3",  "Careers"),                    # 1000  jobs — Hannover area
    ("novartis",    "wd3",  "Novartis_Careers"),           # 760   jobs — Nuremberg
    ("intel",       "wd1",  "External"),                   # 727   jobs — Munich
    ("gsk",         "wd5",  "GSKCareers"),                 # 708   jobs — Munich
    ("autodesk",    "wd1",  "Ext"),                        # 648   jobs — Munich
    ("pfizer",      "wd1",  "PfizerCareers"),              # 493   jobs — Berlin
    ("workday",     "wd5",  "Workday"),                    # 322   jobs — Munich
]

# ── Companies on SmartRecruiters (enterprise ATS) ─────────────────────────────
# Used by Bosch, Continental, and many other industrial/consultancy giants.
# Public API at api.smartrecruiters.com/v1/companies/{slug}/postings, with
# country=de filter so we only get Germany-eligible jobs.
# The scraper pre-filters to AI/ML/data-relevant titles since Bosch alone has
# 4641 active jobs (across all functions). Only relevant ones reach Claude.
SMARTRECRUITERS_SLUGS = [
    "BoschGroup",      # 4641 total jobs, ~947 in Germany
    "Continental",     # 1188 jobs
    "RolandBerger",    # 213 jobs, top European consultancy
    "Visa",            # 20 jobs
    "ContinentalAG",   # 2 jobs (different listing)
]

# ── Ashby ATS slugs (https://api.ashbyhq.com/posting-api/job-board/{slug}) ────
# Slug = the final path segment of a company's jobs.ashbyhq.com/{slug} board.
# Verified: each returned 200 OK with > 0 jobs at time of addition.
ASHBY_SLUGS = [
    "ramp",          # 121 jobs, fintech
    "deepgram",      # 61 jobs, speech AI — direct AI/ML fit
    "perplexity",    # 59 jobs, frontier AI lab
    "supabase",      # 43 jobs, dev infra
    "speak",         # 40 jobs, language learning AI
    "dust",          # 25 jobs, agent platform (Paris)
    "linear",        # 23 jobs, dev tools (Berlin office)
    "browserbase",   # 7 jobs, browser-as-a-service for agents
    "letta",         # 5 jobs, AI memory
    "weaviate",      # 4 jobs, vector DB
    # TODO add more as discovered:
    # "cursor",      # presumably uses Ashby — verify slug
    # "anysphere",   # parent of Cursor
    # "harvey",      # legal AI
]

# ── Recruitee ATS slugs (https://{slug}.recruitee.com/api/offers) ─────────────
RECRUITEE_SLUGS = [
    "limehome",      # 16 jobs, Munich hospitality
    "personio",      # 1 job
    # TODO: search for more EU startups using Recruitee
]
