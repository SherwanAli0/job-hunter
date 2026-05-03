# Job Hunter Daily AI-Powered Job Digest

Runs every morning at 7AM Germany time. Scrapes Greenhouse/Lever APIs, and 15+ major German company career pages.
Claude scores each job against your CV (0–100). Top matches land in your inbox
and/or Notion before you wake up.
---

## What it scrapes

| Source | Method |
|--------|--------|
| Zalando, DeepL, Delivery Hero, N26, Celonis, Personio, … | Greenhouse JSON API |
| HelloFresh, … | Lever JSON API |
| Siemens, SAP, BMW, Bosch, Continental, Infineon, Telekom, E.ON, TUI, CHECK24, VW, Allianz, Munich Re, Siemens Healthineers | Career page scraping |

---

## Setup (one-time, ~20 minutes)

### 1. Fork / create the repo

Push all these files to a new **private** GitHub repo.

### 2. Get your API keys

**Anthropic API key**
1. Go to https://console.anthropic.com
2. API Keys → Create Key
3. Copy it

**Gmail App Password** (do NOT use your real Gmail password)
1. Go to https://myaccount.google.com/security
2. Enable 2-Step Verification if not already on
3. Search "App passwords" → create one → copy the 16-char password

**Notion** (optional but recommended)
1. Go to https://www.notion.so/my-integrations → New integration
2. Copy the "Internal Integration Token"
3. Create a new Notion database with these properties:
   - Title (title)
   - Company (text)
   - Location (text)
   - Score (number)
   - Label (select: Excellent / Good / Decent)
   - Source (select)
   - URL (url)
   - Reason (text)
   - Status (select: New / Applied / Rejected / Offer)
   - Date (date)
4. Open the database → Share → Invite your integration
5. Copy the database ID from the URL:
   `https://www.notion.so/YOUR-DATABASE-ID?v=...`

### 3. Add GitHub Secrets

In your repo: Settings → Secrets and variables → Actions → New repository secret

| Secret name | Value |
|-------------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic key |
| `GMAIL_USER` | your.email@gmail.com |
| `GMAIL_APP_PASSWORD` | The 16-char app password |
| `GMAIL_TO` | Where to send the digest (can be same as GMAIL_USER) |
| `NOTION_TOKEN` | (optional) Your Notion integration token |
| `NOTION_DATABASE_ID` | (optional) Your Notion database ID |

### 4. Enable GitHub Actions

Go to your repo → Actions tab → Enable workflows (if prompted).

### 5. Test it manually

Actions tab → "Daily Job Hunt" → Run workflow

Check your inbox and Notion. First run may take 3–5 minutes.

---

## Customising

All config is in `config.py`:

- **CV_PROFILE** — update if your CV changes
- **SEARCH_QUERIES** — add/remove job title searches
- **MIN_SCORE** — lower to 45 for more results, raise to 70 for fewer
- **GREENHOUSE_SLUGS** — add any company that uses Greenhouse (check: `boards.greenhouse.io/COMPANY`)
- **COMPANY_PAGES** — add any company career URL

---


---

## Local testing

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export GMAIL_USER=you@gmail.com
export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
export GMAIL_TO=you@gmail.com

python main.py
```
