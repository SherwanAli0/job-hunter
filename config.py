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
- Job Hunter — Daily AI-Powered Job Digest (Python, GitHub Actions, Anthropic API, Greenhouse/Lever APIs):
  Built and shipped end-to-end automated job matching system. Scrapes 15+ company career pages, scores
  listings 0-100 against a CV using Claude, delivers ranked digest to email every morning via GitHub Actions.
  Fully automated, zero manual input. Public repo: github.com/SherwanAli0/job-hunter
- German Language Learning App (React, Vite, Tailwind CSS, Node.js, Anthropic API):
  Full-stack AI language learning app from scratch. Prompt engineering for contextual exercises, adaptive
  feedback, and dynamic difficulty. github.com/SherwanAli0/German-App
- ML Reproducibility Study — Graduation Project (Python, scikit-learn, PyTorch, imbalanced-learn):
  Verified 143 reported results across 15 datasets and 10 algorithms. ~75,000 configurations over 900+
  compute-hours. 143/143 replications within 3% average error. github.com/SherwanAli0/csrboost-replication
- Diabetes Risk Prediction (scikit-learn, imbalanced-learn, Pandas):
  Full ML pipeline with SMOTE balancing, SVM/KNN comparison. 75.32% accuracy, 81.8% post-SMOTE recall.

Certifications:
- IBM AI Engineering Professional Certificate (Sep 2025) — 13 courses: ML, Deep Learning, CV, Transformers,
  LLM fine-tuning, RAG, LangChain
- Google Advanced Data Analytics Professional Certificate (Mar 2026) — statistics, regression, ML, Tableau
- Databases and SQL for Data Science with Python — IBM/Coursera (Apr 2026)
"""

# ── Search queries sent to job boards ─────────────────────────────────────────
SEARCH_QUERIES = [
    # Junior / entry level
    "Junior Data Scientist Germany English",
    "Junior Machine Learning Engineer Germany English",
    "Junior Data Analyst Germany English",
    "Junior AI Engineer Germany English",
    "Junior NLP Engineer Germany English",
    "Junior LLM Engineer Germany English",
    "Entry Level Data Scientist Germany English",
    "Entry Level Machine Learning Germany English",
    "Entry Level AI Engineer Germany English",
    "Graduate Data Scientist Germany English",
    "Associate Data Scientist Germany English",
    # LLM / GenAI / Agent roles (new — matches iseremo experience)
    "LLM Engineer Germany English",
    "GenAI Engineer Germany English",
    "AI Agent Engineer Germany English",
    "Prompt Engineer Germany English",
    "Junior LLM Developer Germany English",
    "AI Engineer LLM Germany English",
    # Internships (no student visa required)
    "Data Science Internship Germany English",
    "Machine Learning Internship Germany English",
    "AI Internship Germany English",
    "LLM Internship Germany English",
    "Data Analyst Internship Germany English",
    "Praktikum Data Science English",
    # Mid level (open to strong junior candidates)
    "Data Scientist Germany English",
    "Machine Learning Engineer Germany English",
    "AI Engineer Germany English",
    "Data Analyst Germany English",
    # Remote specific
    "Remote Data Scientist Germany English",
    "Remote Machine Learning Engineer Germany English",
    "Remote AI Engineer Germany English",
    "Remote LLM Engineer Germany English",
    "Remote Junior Data Scientist English",
    "Remote Data Science Internship English",
]

LOCATION = "Germany"

# Minimum Claude score (0–100) to include a job in the digest
MIN_SCORE = 55

# Max jobs per email/Notion update
MAX_RESULTS = 30

# ── Companies with Greenhouse JSON API (free, no scraping needed) ──────────────
# Add more slugs from: boards-api.greenhouse.io/v1/boards/{SLUG}/jobs
GREENHOUSE_SLUGS = [
    "zalando",
    "deepl",
    "deliveryhero",
    "cognigy",
    "n26",
    "sumup",
    "personio",
    "celonis",
    "biontech",
    "flixbus",
    "zattoo",
    "razor-group",
]

# ── Companies with Lever JSON API (free, no scraping needed) ──────────────────
LEVER_SLUGS = [
    "hellofresh",
    "nuri",
]

# ── Major German companies — direct career page scraping ──────────────────────
# type: "workday" | "successfactors" | "generic"
COMPANY_PAGES = [
    {
        "name": "Siemens",
        "url": "https://jobs.siemens.com/careers?location=Germany&search=data+science",
        "type": "generic",
    },
    {
        "name": "SAP",
        "url": "https://jobs.sap.com/search/?q=data+scientist&locname=Germany&country=DE",
        "type": "generic",
    },
    {
        "name": "BMW Group",
        "url": "https://www.bmwgroup.jobs/de/en/jobfinder.html?search=data+science",
        "type": "generic",
    },
    {
        "name": "Bosch",
        "url": "https://careers.bosch.com/en/jobs/?q=data+scientist&location=Germany",
        "type": "generic",
    },
    {
        "name": "Continental",
        "url": "https://jobs.continental.com/en/search/?q=data+scientist&location=Germany",
        "type": "generic",
    },
    {
        "name": "Infineon",
        "url": "https://www.infineon.com/cms/en/careers/job-opportunities/?search=data+scientist",
        "type": "generic",
    },
    {
        "name": "Deutsche Telekom",
        "url": "https://careers.telekom.com/jobs?q=data+scientist&location=Germany",
        "type": "generic",
    },
    {
        "name": "E.ON",
        "url": "https://careers.eon.com/jobs?q=data+scientist&location=Germany",
        "type": "generic",
    },
    {
        "name": "TUI",
        "url": "https://careers.tuigroup.com/jobs?q=data+scientist&location=Germany",
        "type": "generic",
    },
    {
        "name": "CHECK24",
        "url": "https://careers.check24.de/?s=data",
        "type": "generic",
    },
    {
        "name": "Volkswagen",
        "url": "https://www.volkswagenag.com/en/group/careers/job-portal.html",
        "type": "generic",
    },
    {
        "name": "Allianz",
        "url": "https://careers.allianz.com/search?q=data+scientist&country=DE",
        "type": "generic",
    },
    {
        "name": "Munich Re",
        "url": "https://careers.munichre.com/search?q=data+science&country=DE",
        "type": "generic",
    },
    {
        "name": "Siemens Healthineers",
        "url": "https://www.siemens-healthineers.com/en-de/careers/open-positions?q=data+science",
        "type": "generic",
    },
    {
        "name": "Siemens Advanta",
        "url": "https://jobs.siemens.com/careers?location=Germany&search=analytics+AI",
        "type": "generic",
    },
]
