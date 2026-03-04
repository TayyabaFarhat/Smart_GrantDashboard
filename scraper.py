#!/usr/bin/env python3
"""
CMACED Startup Intelligence Dashboard — scraper.py v3
Superior University × ID92

8-Layer Verification Pipeline:
L1 — Trusted Source Registry (trusted_sources.json only)
L2 — Opportunity Discovery (keyword signals)
L3 — Application Page Detection (apply/register link detection)
L4 — Link Validation (HTTP 200 only)
L5 — Data Extraction (structured fields)
L6 — Credibility Scoring (credibility_engine.py)
L7 — Duplicate Detection (fingerprint dedup)
L8 — Deadline Management (archive expired)
"""

import json
import re
import time
import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

# Local modules
sys.path.insert(0, str(Path(__file__).parent))
from credibility_engine import (
    compute_credibility, should_discard, should_archive, deduplicate,
    DISCARD_THRESHOLD
)

# ── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────
BASE     = Path(__file__).parent.parent
SOURCES  = BASE / 'data' / 'trusted_sources.json'
OPP_FILE = BASE / 'data' / 'opportunities.json'
ARCH_FILE= BASE / 'data' / 'archive.json'
LOG_FILE = BASE / 'scraper' / 'scraper.log'

TODAY    = datetime.utcnow().date()

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        'CMACED-Bot/3.0 (+https://superior.edu.pk/cmaced)'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}
TIMEOUT = 15

# ── L2: Discovery keywords ─────────────────────────────────
DISCOVERY_SIGNALS = re.compile(
    r'applications?\s+(?:open|now open|are open)|'
    r'startup\s+(?:competition|challenge|grant|program|fund)|'
    r'innovation\s+(?:challenge|grant|program|fund)|'
    r'accelerator\s+(?:program|cohort|batch)|'
    r'call\s+for\s+(?:applications?|startups?|proposals?)|'
    r'hackathon|fellowship\s+program|grant\s+program|'
    r'incubation\s+program|apply\s+now|'
    r'seed\s+fund(?:ing)?|entrepreneur(?:ship)?\s+(?:competition|program)',
    re.IGNORECASE
)

# ── L3: Application page markers ──────────────────────────
APPLY_URL_PATTERNS = re.compile(
    r'apply|application|register|submit|enrol|join.?program|'
    r'f6s\.com|devpost\.com|typeform\.com|airtable\.com|'
    r'forms\.google|tally\.so',
    re.IGNORECASE
)

# ── Bad link patterns (never store) ───────────────────────
BAD_LINK_RE = re.compile(
    r'news\.google\.com|google\.com/url|feedproxy|'
    r'bing\.com/news|/rss|\.rss|/feed\.xml|'
    r'[?&](utm_|fbclid=|gclid=)|/amp/',
    re.IGNORECASE
)

# ── Date patterns ──────────────────────────────────────────
DATE_FORMATS = [
    (r'\b(\d{4}-\d{2}-\d{2})\b',                   '%Y-%m-%d'),
    (r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b', '%d %B %Y'),
    (r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b', '%B %d %Y'),
    (r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b', '%d %b %Y'),
    (r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4})\b', '%b %d %Y'),
    (r'\b(\d{2}/\d{2}/\d{4})\b', '%d/%m/%Y'),
]
DEADLINE_KEYWORDS = [
    'deadline', 'apply by', 'last date', 'closing date', 'closes on',
    'due date', 'submission deadline', 'application deadline',
    'applications close', 'last day to apply',
]


# ── Helpers ────────────────────────────────────────────────
def load_json(path: Path) -> list:
    if path.exists():
        try:
            d = json.loads(path.read_text('utf-8'))
            return d if isinstance(d, list) else []
        except Exception as e:
            log.error(f'Load error {path}: {e}')
    return []


def save_json(path: Path, data: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), 'utf-8')
    log.info(f'Saved {len(data)} → {path.name}')


def clean_url(url: str) -> str:
    if not url: return ''
    try:
        p = urlparse(url)
        bad = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content',
               'fbclid','gclid','ref','referrer','mc_cid','mc_eid','source'}
        qs = {k:v for k,v in parse_qs(p.query, keep_blank_values=True).items()
              if k.lower() not in bad}
        return urlunparse(p._replace(query=urlencode(qs, doseq=True), fragment=''))
    except Exception:
        return url


def is_bad_url(url: str) -> bool:
    return bool(url) and bool(BAD_LINK_RE.search(url))


def parse_date_str(s: str) -> str:
    s = s.strip().replace(',', '').replace('.', '')
    for _, fmt in DATE_FORMATS:
        for f in [fmt, '%B %d %Y', '%b %d %Y', '%d %B %Y', '%d %b %Y', '%Y-%m-%d', '%d/%m/%Y']:
            try:
                d = datetime.strptime(s, f).date()
                if d >= TODAY - timedelta(days=14):  # allow slight past
                    return d.isoformat()
            except ValueError:
                pass
    return ''


# ── L4: Link validation ────────────────────────────────────
def validate_link(url: str) -> bool:
    if not url or not url.startswith('http') or is_bad_url(url):
        return False
    url = clean_url(url)
    try:
        resp = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if is_bad_url(resp.url):
            return False
        if resp.status_code == 200:
            return True
        if resp.status_code in (405, 406, 403):
            r2 = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, stream=True)
            r2.close()
            return r2.status_code == 200 and not is_bad_url(r2.url)
        return False
    except Exception:
        return False


# ── Page fetcher ───────────────────────────────────────────
def fetch(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        log.debug(f'Fetch error {url}: {e}')
    return None


# ── L2: Opportunity signal detection ──────────────────────
def has_opportunity_signals(soup: BeautifulSoup) -> bool:
    text = soup.get_text(' ', strip=True)[:5000]
    return bool(DISCOVERY_SIGNALS.search(text))


# ── L3: Application page detection ────────────────────────
def find_apply_links(soup: BeautifulSoup, base_url: str, org_domain: str) -> list[str]:
    """Find all potential application links on page. Returns list of valid URLs."""
    candidates = []
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        if not href or href.startswith('#') or href.startswith('mailto:'):
            continue
        text = a.get_text(strip=True).lower()
        full = urljoin(base_url, href)
        if not full.startswith('http'):
            continue
        if is_bad_url(full):
            continue
        # Must match apply keyword OR be on same domain
        is_apply = bool(APPLY_URL_PATTERNS.search(full) or APPLY_URL_PATTERNS.search(text))
        is_own   = org_domain in urlparse(full).netloc
        if is_apply or is_own:
            candidates.append(clean_url(full))
    # Deduplicate preserving order
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c); result.append(c)
    return result


# ── L5: Deadline extraction ────────────────────────────────
def extract_deadline(soup: BeautifulSoup) -> str:
    text = soup.get_text(' ', strip=True)
    text_lower = text.lower()
    for kw in DEADLINE_KEYWORDS:
        idx = text_lower.find(kw)
        if idx == -1: continue
        snippet = text[idx:idx+200]
        for pattern, fmt in DATE_FORMATS:
            m = re.search(pattern, snippet, re.IGNORECASE)
            if m:
                parsed = parse_date_str(m.group(1))
                if parsed:
                    log.debug(f'  Deadline: {parsed} (from "{kw}")')
                    return parsed
    return ''


# ── L5: Prize extraction ───────────────────────────────────
def extract_prize(soup: BeautifulSoup, fallback: str = '') -> str:
    if fallback:
        return fallback
    text = soup.get_text(' ', strip=True)[:3000]
    patterns = [
        r'(?:prize|award|grant|funding|reward|worth)\s*(?:of|:)?\s*((?:USD?|PKR|EUR|GBP|Rs\.?)\s*[\d,]+(?:\s*(?:million|M|K|thousand))?)',
        r'((?:USD?|PKR|EUR|GBP|Rs\.?)\s*[\d,]+(?:\s*(?:million|M|K|thousand))?)\s*(?:prize|award|grant)',
        r'up\s+to\s+((?:USD?|PKR|EUR)\s*[\d,]+(?:\s*(?:million|M|K))?)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ''


# ── Core scraper ───────────────────────────────────────────
def process_source(src: dict, existing: dict) -> dict | None:
    """
    Process one trusted source. Returns opportunity dict or None if discarded.
    """
    sid  = src['id']
    base = src['base_url'].rstrip('/')
    org_domain = urlparse(base).netloc.replace('www.', '')

    log.info(f'\n→ [{sid}] {src["name"]}')

    apply_url    = None
    deadline_str = ''
    prize_str    = src.get('notes_prize', '')  # optional override in source
    soup_main    = None
    link_ok      = False

    # Try each crawl page
    for path in src.get('crawl_pages', ['/']):
        page_url = base + path
        soup = fetch(page_url)
        if not soup:
            log.debug(f'  No response: {page_url}')
            continue

        # L2: Check for opportunity signals
        if not has_opportunity_signals(soup):
            log.debug(f'  No signals on: {page_url}')
            # Still look for apply link if it's a known program page
            if path in ('/apply', '/programs', '/apply/'):
                pass  # fall through
            else:
                continue

        if not soup_main:
            soup_main = soup

        # L3: Find apply links
        candidates = find_apply_links(soup, page_url, org_domain)

        # L4: Validate candidates
        for candidate in candidates[:5]:  # limit attempts
            log.debug(f'  Checking link: {candidate}')
            if validate_link(candidate):
                apply_url = candidate
                link_ok   = True
                log.info(f'  ✓ Apply link: {apply_url}')
                break

        # L5: Extract deadline
        if not deadline_str:
            deadline_str = extract_deadline(soup)

        if apply_url:
            break  # found what we need

    # Fallback: use base URL if it validates
    if not apply_url:
        fallback = src.get('fallback_apply', base)
        if validate_link(fallback):
            apply_url = fallback
            link_ok   = True
            log.info(f'  ✓ Fallback link: {apply_url}')
        else:
            log.warning(f'  ✗ No valid apply link for {sid}')
            return None

    # Prize from page
    if soup_main and not prize_str:
        prize_str = extract_prize(soup_main, prize_str)

    # Preserve existing date_added
    old       = existing.get(sid, {})
    date_added= old.get('date_added', TODAY.isoformat())
    deadline  = deadline_str or old.get('deadline', '')

    # Build entry
    entry = {
        'id':               sid,
        'name':             src['name'],
        'organization':     src['name'],
        'type':             src.get('category', _infer_type(src)),
        'country':          src.get('country', ''),
        'region':           src.get('region', ''),
        'deadline':         deadline,
        'prize':            prize_str,
        'description':      src.get('description', ''),
        'requirements':     src.get('requirements', ''),
        'application_link': clean_url(apply_url),
        'source_url':       base,
        'credibility_score':0,
        'date_added':       date_added,
        'status':           'Open',
    }

    # L6: Credibility scoring
    raw_score = compute_credibility(entry, src, link_ok)
    log.info(f'  Score: {entry["credibility_score"]}/100 (raw {raw_score})')

    # Discard if too low
    if should_discard(entry, raw_score):
        log.warning(f'  ✗ Score too low — discarding {sid}')
        return None

    # Mark for archiving (handled by pipeline)
    entry['_should_archive'] = should_archive(entry, raw_score)
    entry['status'] = 'Closed' if entry['_should_archive'] else _compute_status(entry)

    return entry


def _infer_type(src: dict) -> str:
    src_type = src.get('type', '').lower()
    if src_type in ('government', 'incubator'): return 'grant'
    if src_type in ('university',):             return 'accelerator'
    if src_type in ('accelerator',):            return 'accelerator'
    if src_type in ('competition',):            return 'competition'
    if src_type in ('hackathon',):              return 'hackathon'
    if src_type in ('fellowship',):             return 'fellowship'
    return 'grant'


def _compute_status(entry: dict) -> str:
    dl_str = entry.get('deadline', '')
    if not dl_str: return 'Open'
    try:
        dl = date.fromisoformat(dl_str[:10])
        today = datetime.utcnow().date()
        if dl < today: return 'Closed'
        if (dl - today).days <= 7: return 'Closing Soon'
        added = date.fromisoformat(entry.get('date_added', '')[:10])
        if (today - added).days <= 2: return 'New'
    except Exception:
        pass
    return 'Open'


# ── Main pipeline ──────────────────────────────────────────
def run():
    # Load trusted sources
    sources_raw = load_json(SOURCES)
    if not sources_raw:
        log.error(f'No trusted sources found at {SOURCES}')
        return

    existing = {o['id']: o for o in load_json(OPP_FILE)}
    archive  = {o['id']: o for o in load_json(ARCH_FILE)}

    active    = []
    to_arch   = []
    discarded = 0

    for src in sources_raw:
        try:
            result = process_source(src, existing)
            time.sleep(1.5)  # polite rate limiting

            if result is None:
                discarded += 1
                continue

            # L8: Deadline management
            if result.pop('_should_archive', False):
                clean = {k: v for k, v in result.items() if not k.startswith('_')}
                to_arch.append(clean)
                log.info(f'  → Archived (expired)')
            else:
                clean = {k: v for k, v in result.items() if not k.startswith('_')}
                active.append(clean)

        except Exception as e:
            log.error(f'Error processing {src.get("id","?")}: {e}')
            discarded += 1

    # L7: Deduplication
    active = deduplicate(active)

    # Merge archive
    for entry in to_arch:
        if entry['id'] not in archive:
            archive[entry['id']] = entry

    # Save
    save_json(OPP_FILE, active)
    save_json(ARCH_FILE, list(archive.values()))

    # Summary
    log.info(f"""
{'='*55}
Scrape Complete — {TODAY}
  Active:    {len(active)}
  Archived:  {len(to_arch)}
  Discarded: {discarded}
  Archive total: {len(archive)}
{'='*55}""")

    # Write log
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f'[{datetime.utcnow().isoformat()}] active={len(active)} archived={len(to_arch)} discarded={discarded}\n')


if __name__ == '__main__':
    run()
