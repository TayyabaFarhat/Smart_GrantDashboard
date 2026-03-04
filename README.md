# CMACED Startup Intelligence Dashboard
### Superior University × Innovation District 92 (ID92)

> Official startup opportunity intelligence platform. Verified daily. Official sources only.

---

## Overview

A production-grade static dashboard hosted on **GitHub Pages**, automated via **GitHub Actions**. Scrapes 35 official Pakistani and international sources, validates all links, scores credibility, and publishes results daily.

---

## Project Structure

```
cmaced-startup-dashboard/
├── index.html                   ← Dashboard UI
├── style.css                    ← Styles (light/dark, responsive)
├── script.js                    ← Frontend logic
│
├── data/
│   ├── opportunities.json       ← Active verified opportunities
│   ├── archive.json             ← Expired/closed programs
│   └── trusted_sources.json    ← 35 trusted source definitions
│
├── scraper/
│   ├── scraper.py               ← 8-layer scraping pipeline
│   ├── link_validator.py        ← Daily link revalidation
│   ├── credibility_engine.py    ← Scoring & deduplication
│   ├── requirements.txt
│   ├── scraper.log              ← Auto-generated
│   └── validation.log           ← Auto-generated
│
└── .github/workflows/
    └── auto_update.yml          ← Daily automation
```

---

## Deployment (3 Steps)

### 1. Create GitHub Repository
```bash
git clone https://github.com/YOUR_ORG/cmaced-startup-dashboard.git
# OR upload files via GitHub web interface
```

### 2. Enable GitHub Pages
1. Settings → Pages
2. Source: Deploy from branch → `main` → `/` (root)
3. Save → live at `https://YOUR_ORG.github.io/cmaced-startup-dashboard/`

### 3. Enable GitHub Actions
1. Settings → Actions → General
2. Workflow permissions → Read and write
3. Go to Actions tab → "CMACED Daily Update" → Run workflow (first manual run)

---

## 8-Layer Scraping Pipeline

```
L1  Trusted Source Registry   → Only crawl trusted_sources.json
L2  Opportunity Discovery      → Keyword signal detection on pages
L3  Application Page Detection → Find apply/register links
L4  Link Validation            → HTTP 200 check, reject bad URLs
L5  Data Extraction            → Name, deadline, prize, description
L6  Credibility Scoring        → 0–100 score, discard below 50
L7  Duplicate Detection        → Fingerprint dedup, keep highest score
L8  Deadline Management        → Auto-archive expired entries
```

---

## Credibility Scoring

| Signal | Score |
|---|---|
| Government source | +100 |
| International top-tier (YC, MIT, Google) | +95–100 |
| University program | +80 |
| Link validates HTTP 200 | +50 |
| Official domain link | +30 |
| Deadline present (future) | +30 |
| Prize amount present | +20 |
| Description present | +15 |
| **Discard threshold** | **< 50** |
| Redirected/news/RSS link | −40 to −60 |
| Deadline passed | −100 (force archive) |

---

## Adding New Sources

Add an entry to `data/trusted_sources.json`:

```json
{
  "id": "unique-id",
  "name": "Program Name",
  "country": "Pakistan",
  "region": "national",
  "type": "government",
  "base_url": "https://official-site.org",
  "crawl_pages": ["/programs", "/apply"],
  "credibility_base": 85,
  "notes": "Brief description"
}
```

Types: `government` · `university` · `incubator` · `accelerator` · `competition` · `hackathon` · `fellowship`

**Rules:** URL must be official. No news sites. No social media.

---

## Link Validation Rules

Every link is rejected if it:
- Returns non-200 HTTP status
- Matches `news.google.com`, RSS, redirect patterns
- Contains tracking parameters (UTM, fbclid, gclid)
- Times out after 12 seconds

HEAD request is tried first; falls back to GET if server rejects HEAD.

---

## Archive & CSV Export

- Entries with passed deadlines auto-move to `data/archive.json`
- Archive remains visible in dashboard under "Archive" tab
- Click **Export CSV** or **Download Archive CSV** in footer
- Generates `cmaced-archive-YYYY.csv` client-side

---

## Local Development

```bash
# Serve dashboard
python3 -m http.server 8080
# → http://localhost:8080

# Run scraper
cd scraper
pip install -r requirements.txt
python scraper.py
python link_validator.py
```

---

## Logos

Drop your logo files in the root:
- `cmaced-logo.png`
- `superior-logo.png`
- `id92-logo.png`

Update `index.html` brand section to use `<img>` tags.

---

**CMACED – Superior University × Innovation District 92**  
Lahore, Pakistan
