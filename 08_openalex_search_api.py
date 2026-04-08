"""
Step 8: Recover DBLP AI papers missed by bulk scan, via OpenAlex Search API.

Pipeline position (three cumulative strategies):
  (1) DOI exact match                                  — step 06
  (2) + normalized-title exact match on DOI residual   — step 06
  (3) + OpenAlex Search API on DOI|Title residual      — THIS STEP

For each unmatched DBLP AI paper we query:
    https://api.openalex.org/works?search=<title>&filter=publication_year:<y>&per-page=1
We take ONLY the top-1 result (we trust OpenAlex's relevance ranking) and
then apply fuzzy accept/reject gates:

  title_sim   = token-set Jaccard(dblp_title, oa_title)
  author_hit  = |dblp_surnames ∩ oa_surnames| ≥ 1
  year_ok     = |dblp_year - oa_year| ≤ 1

  ACCEPT (year_ok required) if any of:
    - title_sim ≥ 0.9                           → tier "strong"
    - title_sim ≥ 0.6 AND author_hit            → tier "title_author"
    - title_sim ≥ 0.5 AND author_hit AND rel ≥ 50   → tier "weak"

Output CSV records every probe (matched or not) with all signals so you
can re-tune thresholds after the fact without re-querying.

Input:  data/output/dblp_ai_unmatched.csv   (from step 06)
Output: data/output/dblp_ai_api_matches.csv (resumable)

Usage:
    python 08_openalex_search_api.py                 # run/resume
    python 08_openalex_search_api.py --limit 5000    # first N unprocessed
    python 08_openalex_search_api.py --sleep 0.12
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from dblp_config import OUTPUT_DIR, OPENALEX_MAILTO


API_BASE = 'https://api.openalex.org/works'
USER_AGENT = f'dblp-ai-analysis/1.0 (mailto:{OPENALEX_MAILTO})'

_NON_ALNUM = re.compile(r'[^a-z0-9\s]')
_WS = re.compile(r'\s+')

# Thresholds (kept simple and named so you can tune later)
JACCARD_STRONG        = 0.90
JACCARD_TITLE_AUTHOR  = 0.60
JACCARD_WEAK          = 0.50
RELEVANCE_WEAK_FLOOR  = 50.0
YEAR_TOLERANCE        = 1


# ── Title normalization & similarity ─────────────────────────────────────────

def normalize_title(title: str) -> str:
    if not title:
        return ''
    t = title.lower()
    t = _NON_ALNUM.sub(' ', t)
    t = _WS.sub(' ', t).strip()
    return t


def title_tokens(title: str) -> set[str]:
    return set(normalize_title(title).split())


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Author normalization ─────────────────────────────────────────────────────

def surname(full_name: str) -> str:
    """Best-effort surname extraction. DBLP uses 'First Middle Last' order."""
    if not full_name:
        return ''
    # Strip trailing disambiguation like "John Smith 0001"
    s = re.sub(r'\s+\d{2,}$', '', full_name).strip()
    # Remove punctuation
    s = re.sub(r'[^\w\s\-]', '', s)
    parts = s.split()
    if not parts:
        return ''
    return parts[-1].lower()


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


# ── API call ────────────────────────────────────────────────────────────────

def query_top1(title: str, year: int, timeout: float = 20.0) -> dict | None:
    """Query OpenAlex Search API and return the top-1 result or None."""
    params = {
        'search': title[:250],
        'filter': f'publication_year:{year-YEAR_TOLERANCE}-{year+YEAR_TOLERANCE}',
        'per-page': '1',
        'mailto': OPENALEX_MAILTO,
        'select': 'id,doi,title,display_name,publication_year,authorships,relevance_score',
    }
    url = f'{API_BASE}?{urllib.parse.urlencode(params)}'
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    results = data.get('results') or []
    return results[0] if results else None


# ── Decision ────────────────────────────────────────────────────────────────

def classify(dblp_title: str, dblp_year: int, dblp_authors: str,
             oa: dict) -> tuple[str, float, int, float]:
    """
    Return (tier, title_sim, author_overlap, relevance_score).
    tier ∈ {'', 'strong', 'title_author', 'weak'}; '' means reject.
    """
    oa_title = (oa.get('title') or oa.get('display_name') or '')
    oa_year = oa.get('publication_year') or 0
    rel = float(oa.get('relevance_score') or 0.0)

    sim = jaccard(title_tokens(dblp_title), title_tokens(oa_title))
    overlap = len(dblp_surnames(dblp_authors) & oa_surnames(oa))

    year_ok = abs(dblp_year - oa_year) <= YEAR_TOLERANCE
    if not year_ok:
        return ('', sim, overlap, rel)

    if sim >= JACCARD_STRONG:
        return ('strong', sim, overlap, rel)
    if sim >= JACCARD_TITLE_AUTHOR and overlap >= 1:
        return ('title_author', sim, overlap, rel)
    if sim >= JACCARD_WEAK and overlap >= 1 and rel >= RELEVANCE_WEAK_FLOOR:
        return ('weak', sim, overlap, rel)
    return ('', sim, overlap, rel)


# ── Main ────────────────────────────────────────────────────────────────────

def load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done = set()
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            done.add(row['dblp_key'])
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default=str(OUTPUT_DIR / 'dblp_ai_unmatched.csv'))
    ap.add_argument('--output', default=str(OUTPUT_DIR / 'dblp_ai_api_matches.csv'))
    ap.add_argument('--sleep', type=float, default=0.11)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    if OPENALEX_MAILTO == 'you@example.com':
        print("WARNING: OPENALEX_MAILTO not set — you will be on the slow pool.",
              file=sys.stderr)

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        sys.exit(f"Missing input: {in_path}. Run step 06 first.")

    done = load_checkpoint(out_path)
    print(f"Checkpoint: {len(done):,} rows already processed", file=sys.stderr)

    todo: list[dict] = []
    with open(in_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('dblp_key') in done:
                continue
            todo.append(row)
    print(f"To process: {len(todo):,}", file=sys.stderr)
    if args.limit:
        todo = todo[:args.limit]
        print(f"Limiting to first {len(todo):,}", file=sys.stderr)

    fieldnames = [
        'dblp_key', 'year', 'title', 'dblp_doi',
        'matched', 'tier',
        'title_sim', 'author_overlap', 'relevance_score',
        'openalex_id', 'openalex_doi', 'openalex_title', 'openalex_year',
        'error',
    ]
    write_header = not out_path.exists()
    fout = open(out_path, 'a', newline='', encoding='utf-8')
    writer = csv.DictWriter(fout, fieldnames=fieldnames)
    if write_header:
        writer.writeheader()
        fout.flush()

    n_matched = 0
    n_by_tier: dict[str, int] = {'strong': 0, 'title_author': 0, 'weak': 0}
    n_errors = 0
    t0 = time.time()

    for i, row in enumerate(todo):
        dblp_key = row.get('dblp_key', '')
        title = row.get('title', '') or ''
        authors = row.get('authors', '') or ''
        try:
            year = int(row['year'])
        except (KeyError, ValueError):
            continue

        out_row = {
            'dblp_key': dblp_key, 'year': year, 'title': title,
            'dblp_doi': row.get('doi', ''),
            'matched': '0', 'tier': '',
            'title_sim': '', 'author_overlap': '', 'relevance_score': '',
            'openalex_id': '', 'openalex_doi': '', 'openalex_title': '',
            'openalex_year': '', 'error': '',
        }

        try:
            oa = query_top1(title, year)
            if oa is not None:
                tier, sim, overlap, rel = classify(title, year, authors, oa)
                out_row['title_sim'] = f"{sim:.3f}"
                out_row['author_overlap'] = overlap
                out_row['relevance_score'] = f"{rel:.1f}"
                out_row['openalex_id'] = oa.get('id', '')
                out_row['openalex_doi'] = oa.get('doi', '') or ''
                out_row['openalex_title'] = (oa.get('title') or oa.get('display_name') or '')
                out_row['openalex_year'] = oa.get('publication_year', '')
                if tier:
                    out_row['matched'] = '1'
                    out_row['tier'] = tier
                    n_matched += 1
                    n_by_tier[tier] += 1
        except Exception as e:
            out_row['error'] = str(e)[:200]
            n_errors += 1
            time.sleep(1.0)

        writer.writerow(out_row)

        if (i + 1) % 100 == 0:
            fout.flush()
            elapsed = time.time() - t0
            rate = (i + 1) / max(elapsed, 1e-9)
            eta = (len(todo) - i - 1) / max(rate, 1e-9)
            print(f"  {i+1:,}/{len(todo):,} | matched={n_matched:,} "
                  f"(S={n_by_tier['strong']} TA={n_by_tier['title_author']} "
                  f"W={n_by_tier['weak']}) err={n_errors} | "
                  f"{rate:.1f} req/s | eta {eta/60:.1f}m",
                  file=sys.stderr)

        time.sleep(args.sleep)

    fout.close()
    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s", file=sys.stderr)
    print(f"  processed: {len(todo):,}", file=sys.stderr)
    print(f"  matched:   {n_matched:,} "
          f"(strong={n_by_tier['strong']:,} "
          f"title+author={n_by_tier['title_author']:,} "
          f"weak={n_by_tier['weak']:,})", file=sys.stderr)
    print(f"  errors:    {n_errors:,}", file=sys.stderr)
    print(f"Output: {out_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
