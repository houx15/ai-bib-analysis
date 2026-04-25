"""
Step 10b: API top-up for country attribution. Run AFTER step 10a, on a
host with outbound network (free filter pool — `/works/<id>` is NOT
charged against the search quota; ~10k/day free with API key).

Reads strong API matches from steps 08a/08b (tier ∈ {doi_api, strong}).
For any whose dblp_key is missing from data/output/dblp_ai_country.csv
(or has a non-bulk attribution that you want to refresh), fetches the
work by openalex_id and infers country with the same reference logic
as step 10a.

Inputs:
  data/output/dblp_ai_country.csv          (from 10a)
  data/output/dblp_ai_doi_matches.csv      (from 08a; tier=doi_api)
  data/output/dblp_ai_search_matches.csv   (from 08b; tier=strong only)

Output (upsert by dblp_key):
  data/output/dblp_ai_country.csv
    country_source ∈ {api_doi, api_search} for rows added here.

Resumable: re-run any time, it skips rows already present.

Usage:
  python 10b_country_api.py
  python 10b_country_api.py --limit 500
  python 10b_country_api.py --sleep 0.1
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from dblp_config import OUTPUT_DIR, YEAR_MIN, YEAR_MAX
from openalex_utils import print_auth_banner, query_by_id


ALLOWED_COUNTRIES = {'CN', 'HK', 'TW', 'US'}

FIELDNAMES = ['dblp_key', 'year', 'openalex_id', 'country', 'country_source']


def infer_country(authorships: list) -> str | None:
    """Raw country code in {CN, HK, TW, US} — kept distinct.
    See 10a_country_bulk.py for the rationale."""
    for a in authorships or []:
        if a.get('is_corresponding') and a.get('countries'):
            c = a['countries'][0]
            return c if c in ALLOWED_COUNTRIES else None
    for a in authorships or []:
        if a.get('author_position') == 'first' and a.get('countries'):
            c = a['countries'][0]
            return c if c in ALLOWED_COUNTRIES else None
    return None


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            key = row.get('dblp_key', '')
            if key:
                out[key] = {k: row.get(k, '') for k in FIELDNAMES}
    return out


def write_all(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for v in records.values():
            w.writerow({k: v.get(k, '') for k in FIELDNAMES})
    tmp.replace(path)


def load_strong_api_matches() -> dict[str, dict]:
    """Return {dblp_key: {year, openalex_id, tier}} for tiers
    {doi_api, strong} — 08a wins on conflict (DOI > search)."""
    out: dict[str, dict] = {}
    sources = [
        ('doi_api', OUTPUT_DIR / 'dblp_ai_doi_matches.csv'),
        ('strong',  OUTPUT_DIR / 'dblp_ai_search_matches.csv'),
    ]
    for label, path in sources:
        if not path.exists():
            print(f"NOTE: {path} not found — skipping {label}", file=sys.stderr)
            continue
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('matched', '0') != '1':
                    continue
                tier = row.get('tier', '') or ''
                if tier not in ('doi_api', 'strong'):
                    continue
                key = row.get('dblp_key', '')
                if not key or key in out:
                    continue
                try:
                    y = int(row['year'])
                except (ValueError, KeyError):
                    continue
                if not (YEAR_MIN <= y <= YEAR_MAX):
                    continue
                out[key] = {
                    'year': y,
                    'openalex_id': row.get('openalex_id', '') or '',
                    'tier': tier,
                }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0,
                    help='Cap API calls (default: no limit).')
    ap.add_argument('--sleep', type=float, default=0.1,
                    help='Sleep between API calls (seconds).')
    args = ap.parse_args()

    print_auth_banner()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / 'dblp_ai_country.csv'

    records = load_existing(out_path)
    print(f"Existing rows in {out_path.name}: {len(records):,}", file=sys.stderr)

    strong = load_strong_api_matches()
    print(f"Strong API matches (08a doi_api + 08b strong): {len(strong):,}",
          file=sys.stderr)

    todo = [(k, v) for k, v in strong.items() if k not in records]
    if args.limit:
        todo = todo[:args.limit]
    print(f"Need API country lookup: {len(todo):,}", file=sys.stderr)

    n_country = 0
    n_no_country = 0
    n_errors = 0
    t0 = time.time()
    last_flush = t0

    for i, (key, info) in enumerate(todo):
        oa_id = info['openalex_id']
        if not oa_id:
            n_no_country += 1
            continue
        try:
            work = query_by_id(oa_id)
        except Exception as e:
            n_errors += 1
            print(f"  ERROR {key}: {str(e)[:100]}", file=sys.stderr)
            time.sleep(1.0)
            continue
        time.sleep(args.sleep)

        if work is None:
            n_no_country += 1
            continue
        country = infer_country(work.get('authorships') or [])
        if country is None:
            n_no_country += 1
            continue

        records[key] = {
            'dblp_key': key,
            'year': info['year'],
            'openalex_id': oa_id,
            'country': country,
            'country_source': 'api_doi' if info['tier'] == 'doi_api' else 'api_search',
        }
        n_country += 1

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / max(elapsed, 1e-9)
            eta = (len(todo) - i - 1) / max(rate, 1e-9)
            print(f"  {i+1:,}/{len(todo):,} | country={n_country:,} "
                  f"none={n_no_country:,} err={n_errors} | "
                  f"{rate:.1f} req/s | eta {eta/60:.1f}m", file=sys.stderr)
            # Flush every ~10 min so kill mid-run loses < 10 min of API work.
            if time.time() - last_flush > 600:
                write_all(out_path, records)
                last_flush = time.time()

    elapsed = time.time() - t0
    write_all(out_path, records)
    print(f"\nDone in {elapsed:.0f}s.", file=sys.stderr)
    print(f"  added country: {n_country:,}", file=sys.stderr)
    print(f"  no country:    {n_no_country:,} (off-list / missing authorships)",
          file=sys.stderr)
    print(f"  errors:        {n_errors:,}", file=sys.stderr)
    print(f"  total rows:    {len(records):,}", file=sys.stderr)
    print(f"Saved: {out_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
