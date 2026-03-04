#!/usr/bin/env python3
"""
CMACED Startup Intelligence Dashboard — link_validator.py v3
Superior University × ID92

Runs after scraper.py on every daily GitHub Actions run.
1. Re-validates every application_link (HTTP 200)
2. Removes broken/bad links
3. Archives entries with passed deadlines
4. Recomputes status for all entries
5. Deduplicates by fingerprint
6. Writes validation.log
"""

import json
import logging
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

import requests

sys.path.insert(0, str(Path(__file__).parent))
from credibility_engine import deduplicate, should_archive

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger(__name__)

BASE      = Path(__file__).parent.parent
OPP_FILE  = BASE / 'data' / 'opportunities.json'
ARCH_FILE = BASE / 'data' / 'archive.json'
LOG_FILE  = BASE / 'scraper' / 'validation.log'

TODAY     = datetime.utcnow().date()
TIMEOUT   = 12
WORKERS   = 6

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; CMACED-Validator/3.0; +https://superior.edu.pk/cmaced)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

BAD_PATTERNS = re.compile(
    r'news\.google\.com|google\.com/url\?|feedproxy|'
    r'bing\.com/news|[?&](?:utm_|fbclid=|gclid=)|'
    r'/rss|\.rss|/feed(?:\.xml)?|/amp/',
    re.IGNORECASE
)


# ── Helpers ────────────────────────────────────────────────
def load_json(p: Path) -> list:
    if p.exists():
        try:
            d = json.loads(p.read_text('utf-8'))
            return d if isinstance(d, list) else []
        except Exception as e:
            log.error(f'Load {p}: {e}')
    return []


def save_json(p: Path, data: list) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), 'utf-8')
    log.info(f'Saved {len(data)} → {p.name}')


def clean_url(url: str) -> str:
    if not url: return ''
    try:
        p = urlparse(url)
        bad = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content',
               'fbclid','gclid','ref','referrer','mc_cid','mc_eid'}
        qs = {k:v for k,v in parse_qs(p.query, keep_blank_values=True).items()
              if k.lower() not in bad}
        return urlunparse(p._replace(query=urlencode(qs,doseq=True), fragment=''))
    except Exception:
        return url


def parse_dl(s: str):
    if not s: return None
    try: return date.fromisoformat(s[:10])
    except ValueError: return None


def recompute_status(entry: dict) -> str:
    dl = parse_dl(entry.get('deadline', ''))
    if not dl: return 'Open'
    if dl < TODAY: return 'Closed'
    if (dl - TODAY).days <= 7: return 'Closing Soon'
    try:
        added = date.fromisoformat(entry.get('date_added','')[:10])
        if (TODAY - added).days <= 2: return 'New'
    except Exception: pass
    return 'Open'


# ── Link checker ──────────────────────────────────────────
def check(url: str) -> tuple[bool, str]:
    """Returns (ok, reason)."""
    if not url:
        return False, 'empty'
    if not url.startswith('http'):
        return False, 'non-http'
    if BAD_PATTERNS.search(url):
        return False, 'bad pattern'

    url = clean_url(url)
    try:
        r = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if BAD_PATTERNS.search(r.url):
            return False, f'redirected to bad: {r.url}'
        if r.status_code == 200:
            return True, 'HTTP 200'
        if r.status_code in (405, 406, 403):
            r2 = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                              allow_redirects=True, stream=True)
            r2.close()
            if BAD_PATTERNS.search(r2.url):
                return False, f'GET redirect bad: {r2.url}'
            if r2.status_code == 200:
                return True, 'HTTP 200 (GET)'
            return False, f'HTTP {r2.status_code}'
        return False, f'HTTP {r.status_code}'
    except requests.exceptions.SSLError:
        return False, 'SSL error'
    except requests.exceptions.ConnectionError:
        return False, 'connection error'
    except requests.exceptions.Timeout:
        return False, f'timeout {TIMEOUT}s'
    except Exception as e:
        return False, f'error: {e}'


def validate_entry(entry: dict) -> dict:
    r = entry.copy()
    ok, reason = check(entry.get('application_link', ''))
    r['_ok']     = ok
    r['_reason'] = reason
    dl = parse_dl(entry.get('deadline', ''))
    r['_expired'] = bool(dl and dl < TODAY)
    r['status']   = recompute_status(entry)
    sym = '✓' if ok else '✗'
    lvl = log.info if ok else log.warning
    lvl(f'  {sym} [{entry.get("id","")}] {reason}')
    return r


# ── Main ───────────────────────────────────────────────────
def run():
    opps    = load_json(OPP_FILE)
    archive = load_json(ARCH_FILE)

    if not opps:
        log.warning('No opportunities to validate.')
        return

    log.info(f'Validating {len(opps)} entries with {WORKERS} workers…')

    validated = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(validate_entry, e): e for e in opps}
        for fut in as_completed(futs):
            try:
                validated.append(fut.result())
            except Exception as err:
                e = futs[fut]
                log.error(f'Worker error [{e.get("id","?")}]: {err}')
                e2 = e.copy()
                e2.update({'_ok':False,'_reason':str(err),'_expired':False})
                validated.append(e2)

    active   = []
    to_arch  = []
    log_lines= [f'=== {datetime.utcnow().isoformat()} ===']

    for e in validated:
        clean = {k:v for k,v in e.items() if not k.startswith('_')}
        if e.get('_expired'):
            clean['status'] = 'Closed'
            to_arch.append(clean)
            log_lines.append(f'ARCHIVED  {e["id"]} | deadline {e.get("deadline","")}')
        elif not e.get('_ok'):
            log_lines.append(f'REMOVED   {e["id"]} | {e["_reason"]} | {e.get("application_link","")}')
        else:
            active.append(clean)

    # Merge archive
    arch_ids = {a['id'] for a in archive}
    for entry in to_arch:
        if entry['id'] not in arch_ids:
            archive.append(entry)

    # Deduplicate
    active  = deduplicate(active)
    archive = deduplicate(archive)

    save_json(OPP_FILE, active)
    save_json(ARCH_FILE, archive)

    removed  = sum(1 for l in log_lines if l.startswith('REMOVED'))
    archived_n = len(to_arch)

    log.info(f"""
{'='*55}
Validation — {TODAY}
  Active:   {len(active)}
  Archived: {archived_n}
  Removed:  {removed}
{'='*55}""")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write('\n'.join(log_lines) + '\n')
        f.write(f'SUMMARY active={len(active)} archived={archived_n} removed={removed}\n\n')


if __name__ == '__main__':
    run()
