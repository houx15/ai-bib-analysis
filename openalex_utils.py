"""
Shared helpers for the OpenAlex API steps (08a DOI lookup and 08b search).

Keeps auth/rate-limit/normalization logic in one place so the two stage
scripts stay focused on their specific flow.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from dblp_config import OPENALEX_MAILTO, OPENALEX_API_KEY


API_BASE = 'https://api.openalex.org/works'
USER_AGENT = f'dblp-ai-analysis/1.0 (mailto:{OPENALEX_MAILTO})'

# Fuzzy-match thresholds used by the search stage (08b).
JACCARD_STRONG       = 0.90
JACCARD_TITLE_AUTHOR = 0.60
JACCARD_WEAK         = 0.50
RELEVANCE_WEAK_FLOOR = 50.0
YEAR_TOLERANCE       = 1

_NON_ALNUM = re.compile(r'[^a-z0-9\s]')
_WS = re.compile(r'\s+')


# ── Auth ────────────────────────────────────────────────────────────────────

def auth_params() -> dict:
    if OPENALEX_API_KEY:
        return {'api_key': OPENALEX_API_KEY}
    return {'mailto': OPENALEX_MAILTO}


def print_auth_banner() -> None:
    if OPENALEX_API_KEY:
        print("Auth: api_key set", file=sys.stderr)
    elif OPENALEX_MAILTO != 'you@example.com':
        print(f"Auth: mailto={OPENALEX_MAILTO} (polite pool)", file=sys.stderr)
    else:
        print("WARNING: neither OPENALEX_API_KEY nor OPENALEX_MAILTO is set — "
              "anonymous pool, expect 429 errors.", file=sys.stderr)


# ── Title / author normalization ────────────────────────────────────────────

def normalize_title(title: str) -> str:
    if not title:
        return ''
    t = title.lower()
    t = _NON_ALNUM.sub(' ', t)
    return _WS.sub(' ', t).strip()


def title_tokens(title: str) -> set[str]:
    return set(normalize_title(title).split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def surname(full_name: str) -> str:
    """Best-effort surname extraction. DBLP uses 'First Middle Last' order."""
    if not full_name:
        return ''
    # Strip trailing disambiguation like "John Smith 0001"
    s = re.sub(r'\s+\d{2,}$', '', full_name).strip()
    s = re.sub(r'[^\w\s\-]', '', s)
    parts = s.split()
    return parts[-1].lower() if parts else ''


def dblp_surnames(authors_field: str) -> set[str]:
    """DBLP stores authors as '; '-joined."""
    if not authors_field:
        return set()
    return {surname(a) for a in authors_field.split(';') if a.strip()}


def oa_surnames(work: dict) -> set[str]:
    out = set()
    for a in work.get('authorships') or []:
        name = ((a.get('author') or {}).get('display_name')) or ''
        s = surname(name)
        if s:
            out.add(s)
    return out


# ── API calls with 429 backoff ──────────────────────────────────────────────

def normalize_doi(doi: str) -> str:
    """Strip scheme/host so OpenAlex sees a bare DOI."""
    doi = (doi or '').strip()
    if not doi:
        return ''
    low = doi.lower()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'doi:'):
        if low.startswith(prefix):
            return doi[len(prefix):]
    return doi


def _request(url: str, timeout: float, retries: int) -> dict | None:
    """GET with exponential backoff on 429. Returns parsed JSON, or None on 404."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    wait = 60.0
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 and attempt < retries:
                print(f"  429 — sleeping {wait:.0f}s "
                      f"(attempt {attempt+1}/{retries})", file=sys.stderr)
                time.sleep(wait)
                wait = min(wait * 2, 600)
            else:
                raise


def query_doi(doi: str, timeout: float = 20.0, retries: int = 4) -> dict | None:
    """GET /works/doi:<doi> — filter pool, much cheaper than search.
    Returns work dict, or None if OpenAlex doesn't have this DOI (404)."""
    doi = normalize_doi(doi)
    if not doi:
        return None
    params = auth_params()
    params['select'] = 'id,doi,title,display_name,publication_year,authorships'
    url = f'{API_BASE}/doi:{urllib.parse.quote(doi, safe="")}?{urllib.parse.urlencode(params)}'
    return _request(url, timeout, retries)


def query_top1(title: str, year: int,
               timeout: float = 20.0, retries: int = 6) -> dict | None:
    """GET /works?search=<title>&filter=publication_year:<y-1>-<y+1>&per-page=1.
    Search pool — counts against the paid quota. Returns top-1 result or None."""
    params = auth_params()
    params.update({
        'search': title[:250],
        'filter': f'publication_year:{year-YEAR_TOLERANCE}-{year+YEAR_TOLERANCE}',
        'per-page': '1',
        'select': 'id,doi,title,display_name,publication_year,authorships,relevance_score',
    })
    url = f'{API_BASE}?{urllib.parse.urlencode(params)}'
    data = _request(url, timeout, retries)
    if data is None:
        return None
    results = data.get('results') or []
    return results[0] if results else None


# ── Fuzzy classify for search results ───────────────────────────────────────

def classify(dblp_title: str, dblp_year: int, dblp_authors: str,
             oa: dict) -> tuple[str, float, int, float]:
    """Return (tier, title_sim, author_overlap, relevance_score).
    tier ∈ {'', 'strong', 'title_author', 'weak'}; '' means reject."""
    oa_title = oa.get('title') or oa.get('display_name') or ''
    oa_year = oa.get('publication_year') or 0
    rel = float(oa.get('relevance_score') or 0.0)

    sim = jaccard(title_tokens(dblp_title), title_tokens(oa_title))
    overlap = len(dblp_surnames(dblp_authors) & oa_surnames(oa))

    if abs(dblp_year - oa_year) > YEAR_TOLERANCE:
        return ('', sim, overlap, rel)

    if sim >= JACCARD_STRONG:
        return ('strong', sim, overlap, rel)
    if sim >= JACCARD_TITLE_AUTHOR and overlap >= 1:
        return ('title_author', sim, overlap, rel)
    if sim >= JACCARD_WEAK and overlap >= 1 and rel >= RELEVANCE_WEAK_FLOOR:
        return ('weak', sim, overlap, rel)
    return ('', sim, overlap, rel)
