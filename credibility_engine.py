#!/usr/bin/env python3
"""
CMACED Startup Intelligence Dashboard — credibility_engine.py
Superior University × ID92

Scores each opportunity for credibility/verification confidence.
Scoring is additive. Entries below DISCARD_THRESHOLD are dropped.
"""

import re
from datetime import datetime, date, timedelta
from urllib.parse import urlparse

DISCARD_THRESHOLD = 50  # Entries scoring below this are discarded

# ── Scoring weights ────────────────────────────────────────
WEIGHTS = {
    # Source type
    'source_government':   100,
    'source_university':    80,
    'source_intl_top':      95,  # YC, MIT, Google, etc.
    'source_intl_known':    80,
    'source_incubator':     75,
    'source_platform':      60,  # devpost, f6s, etc.

    # Link quality
    'link_verified_200':    50,
    'link_official_domain': 30,
    'link_apply_page':      20,

    # Data completeness
    'has_deadline':         30,
    'has_prize':            20,
    'has_description':      15,
    'has_requirements':     15,
    'has_organization':     10,

    # Deadline quality
    'deadline_future':      20,
    'deadline_far':         10,  # > 30 days

    # Negative signals
    'link_redirect':       -40,
    'link_news':           -50,
    'link_rss':            -60,
    'no_apply_link':       -20,
    'deadline_past':       -100,  # Forces archived
}

# Known top-tier international sources → full trust
TOP_INTL_DOMAINS = {
    'ycombinator.com', 'techstars.com', 'solve.mit.edu', 'hultprize.org',
    'startup.google.com', 'microsoft.com', 'aws.amazon.com', '500.co',
    'masschallenge.org', 'seedstars.com', 'devpost.com', 'f6s.com',
    'plugandplaytechcenter.com', 'un.org', 'worldbank.org', 'eic.ec.europa.eu',
    'startupchile.org', 'tonyelumelufoundation.org',
}

# Pakistani government domains → full trust
PK_GOV_DOMAINS = {
    'ignite.org.pk', 'plan9.pitb.gov.pk', 'pitb.gov.pk', 'pseb.org.pk',
    'hec.gov.pk', 'stza.gov.pk', 'navttc.gov.pk', 'pmyp.gov.pk',
    'nicislamabad.com', 'niclahore.com', 'nickarachi.com',
}

# Pakistani university domains
PK_UNI_DOMAINS = {
    'superior.edu.pk', 'lums.edu.pk', 'nust.edu.pk', 'ucp.edu.pk',
    'giki.edu.pk', 'aku.edu', 'nu.edu.pk', 'umt.edu.pk',
    'arfatechpark.com', 'innovistapakistan.com',
}

# Patterns that indicate a low-quality / unreliable link
BAD_URL_PATTERNS = re.compile(
    r'news\.google\.com|google\.com/url\?|feedproxy|'
    r'[?&](utm_|fbclid=|gclid=)|/rss|\.rss|/feed\.xml|/amp/',
    re.IGNORECASE
)

APPLY_KEYWORDS = re.compile(
    r'apply|application|register|submit|join|enrol',
    re.IGNORECASE
)


def get_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        host = urlparse(url).netloc.lower()
        return host.replace('www.', '')
    except Exception:
        return ''


def score_source(source_entry: dict, url: str) -> int:
    """Score based on source type and domain trust."""
    domain = get_domain(url)
    src_type = source_entry.get('type', '')

    if domain in PK_GOV_DOMAINS:
        return WEIGHTS['source_government']
    if domain in PK_UNI_DOMAINS:
        return WEIGHTS['source_university']
    if domain in TOP_INTL_DOMAINS:
        return WEIGHTS['source_intl_top']
    if src_type in ('government',):
        return WEIGHTS['source_government']
    if src_type in ('university',):
        return WEIGHTS['source_university']
    if src_type in ('accelerator', 'competition'):
        return WEIGHTS['source_intl_known']
    if src_type in ('incubator',):
        return WEIGHTS['source_incubator']
    return WEIGHTS['source_platform']


def score_link(url: str, link_validated: bool) -> int:
    """Score based on link quality."""
    total = 0
    if not url:
        return WEIGHTS['no_apply_link']

    if BAD_URL_PATTERNS.search(url):
        total += WEIGHTS['link_news']
        return total  # immediately penalised

    if link_validated:
        total += WEIGHTS['link_verified_200']

    domain = get_domain(url)
    if any(domain.endswith(d.replace('www.','')) for d in (PK_GOV_DOMAINS | PK_UNI_DOMAINS | TOP_INTL_DOMAINS)):
        total += WEIGHTS['link_official_domain']

    if APPLY_KEYWORDS.search(url):
        total += WEIGHTS['link_apply_page']

    return total


def score_completeness(entry: dict) -> int:
    """Score based on how complete the data is."""
    total = 0
    if entry.get('deadline'):     total += WEIGHTS['has_deadline']
    if entry.get('prize'):        total += WEIGHTS['has_prize']
    if entry.get('description'):  total += WEIGHTS['has_description']
    if entry.get('requirements'): total += WEIGHTS['has_requirements']
    if entry.get('organization'): total += WEIGHTS['has_organization']
    return total


def score_deadline(deadline_str: str) -> int:
    """Score based on deadline validity and how far in the future it is."""
    if not deadline_str:
        return 0
    try:
        dl = date.fromisoformat(deadline_str[:10])
        today = datetime.utcnow().date()
        if dl < today:
            return WEIGHTS['deadline_past']  # will trigger archiving
        total = WEIGHTS['deadline_future']
        if (dl - today).days > 30:
            total += WEIGHTS['deadline_far']
        return total
    except ValueError:
        return 0


def compute_credibility(entry: dict, source_entry: dict, link_validated: bool) -> int:
    """
    Compute overall credibility score for an opportunity entry.
    Returns integer 0–200 (capped at 100 for display).
    Negative result (from past deadline) triggers archiving.
    """
    apply_url  = entry.get('application_link', '')
    source_url = entry.get('source_url', '')

    s = 0
    s += score_source(source_entry, source_url)
    s += score_link(apply_url, link_validated)
    s += score_completeness(entry)
    s += score_deadline(entry.get('deadline', ''))

    # Cap display score
    display = max(0, min(100, s))
    entry['credibility_score'] = display
    entry['_raw_score'] = s  # used internally to detect archived

    return s


def should_discard(entry: dict, raw_score: int) -> bool:
    """True if entry should be discarded (too low score or expired)."""
    if raw_score <= DISCARD_THRESHOLD:
        return True
    return False


def should_archive(entry: dict, raw_score: int) -> bool:
    """True if entry should be moved to archive (deadline passed)."""
    if raw_score < 0:
        return True
    dl_str = entry.get('deadline', '')
    if dl_str:
        try:
            dl = date.fromisoformat(dl_str[:10])
            if dl < datetime.utcnow().date():
                return True
        except ValueError:
            pass
    return False


def deduplicate(entries: list) -> list:
    """
    Remove duplicate opportunities.
    Fingerprint: normalized name + organization + deadline.
    Keep highest credibility_score.
    """
    seen: dict = {}
    for entry in entries:
        fp = _fingerprint(entry)
        if fp not in seen:
            seen[fp] = entry
        else:
            existing_score = seen[fp].get('credibility_score', 0)
            new_score = entry.get('credibility_score', 0)
            if new_score > existing_score:
                seen[fp] = entry
    return list(seen.values())


def _fingerprint(entry: dict) -> str:
    """Create a normalized fingerprint for duplicate detection."""
    name = re.sub(r'\W+', '', (entry.get('name') or '').lower())
    org  = re.sub(r'\W+', '', (entry.get('organization') or '').lower())[:20]
    dl   = (entry.get('deadline') or '')[:7]  # year-month
    return f'{name}|{org}|{dl}'


# ── CLI usage ──────────────────────────────────────────────
if __name__ == '__main__':
    import json

    sample = {
        'id': 'test-entry',
        'name': 'Test Program',
        'organization': 'Test Org',
        'type': 'grant',
        'country': 'Pakistan',
        'region': 'national',
        'deadline': (datetime.utcnow().date() + timedelta(days=30)).isoformat(),
        'prize': 'USD 10,000',
        'description': 'Test description',
        'requirements': 'Test requirements',
        'application_link': 'https://ignite.org.pk/programs/',
        'source_url': 'https://ignite.org.pk',
    }
    src = {'type': 'government'}
    raw = compute_credibility(sample, src, link_validated=True)
    print(f'Sample score: {sample["credibility_score"]}/100 (raw: {raw})')
    print(f'Should discard: {should_discard(sample, raw)}')
    print(f'Should archive: {should_archive(sample, raw)}')
