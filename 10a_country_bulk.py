"""
Step 10a: Bulk scan OpenAlex .gz works to attribute country (CN/US) to
DBLP AI papers matched by exact DOI or normalized-title.

NO NETWORK — safe to run on a compute node. Mirrors step 06's matching
indices so the country we record corresponds to the same OpenAlex work
that step 06 counted as a match.

Country logic (per reference/openalex_method.md):
  1. corresponding author with non-empty `countries` → countries[0];
  2. else first author with non-empty `countries` → countries[0];
  3. restrict to {CN, HK, TW, US}; codes are preserved as-is.

HK/TW are NOT collapsed into CN at attribution time so we retain the
ability to re-aggregate later. Step 11 does the {CN,HK,TW} → "China"
grouping for plots.

Inputs:
  data/parsed/dblp_ai_papers.csv
  OPENALEX_DIR/**/*.gz

Output (resumable, upsert by dblp_key):
  data/output/dblp_ai_country.csv
    columns: dblp_key, year, openalex_id, country, country_source

  country_source ∈ {bulk_doi, bulk_title}.

Step 10b (separate, network-enabled) tops this up via the live API for
strong API matches not present in the bulk snapshot.

Usage:
  python 10a_country_bulk.py
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
import time
from pathlib import Path

from dblp_config import (
    PARSED_DIR, OUTPUT_DIR, OPENALEX_DIR, YEAR_MIN, YEAR_MAX,
)


_NON_ALNUM = re.compile(r'[^a-z0-9\s]')
_WS = re.compile(r'\s+')

ALLOWED_COUNTRIES = {'CN', 'HK', 'TW', 'US'}

FIELDNAMES = ['dblp_key', 'year', 'openalex_id', 'country', 'country_source']


def normalize_title(title: str) -> str:
    if not title:
        return ''
    t = title.lower()
    t = _NON_ALNUM.sub(' ', t)
    return _WS.sub(' ', t).strip()


def extract_doi_key(doi_str: str) -> str:
    if not doi_str:
        return ''
    s = doi_str.strip().lower()
    for prefix in ('https://doi.org/', 'http://doi.org/',
                   'http://dx.doi.org/', 'https://dx.doi.org/'):
        if s.startswith(prefix):
            return s[len(prefix):]
    if s.startswith('10.'):
        return s
    return ''


def infer_country(authorships: list) -> str | None:
    """Return raw country code in {CN, HK, TW, US}, or None.

    Per reference/openalex_method.md: corresponding-author's countries[0]
    is used if any corresponding author has a non-empty countries field;
    otherwise fall back to the first author. Codes outside the allow-list
    are treated as "no usable country" for this study (the work is
    excluded), and HK/TW are kept distinct from CN — collapsing happens
    at plot time."""
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


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / 'dblp_ai_country.csv'

    # Load DBLP AI papers and build lookup indices.
    print("Loading DBLP AI papers...", file=sys.stderr)
    ai_doi_to_key: dict[str, str] = {}
    ai_title_to_key: dict[str, str] = {}
    key_to_year: dict[str, int] = {}
    n_ai = 0
    with open(PARSED_DIR / 'dblp_ai_papers.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                year = int(row['year'])
            except (ValueError, KeyError):
                continue
            if not (YEAR_MIN <= year <= YEAR_MAX):
                continue
            key = row.get('dblp_key', '')
            if not key:
                continue
            n_ai += 1
            key_to_year[key] = year
            doi_key = extract_doi_key(row.get('doi', ''))
            if doi_key and doi_key not in ai_doi_to_key:
                ai_doi_to_key[doi_key] = key
            nt = normalize_title(row.get('title', ''))
            if nt and nt not in ai_title_to_key:
                ai_title_to_key[nt] = key
    print(f"  AI papers: {n_ai:,} | DOI idx: {len(ai_doi_to_key):,} "
          f"| Title idx: {len(ai_title_to_key):,}", file=sys.stderr)

    # Resume from existing CSV.
    records = load_existing(out_path)
    if records:
        print(f"Resuming from {out_path}: {len(records):,} rows already present",
              file=sys.stderr)

    # Skip keys that already have a bulk-source country attribution.
    bulk_sources = {'bulk_doi', 'bulk_title'}
    skip_bulk = {k for k, v in records.items()
                 if v.get('country_source', '') in bulk_sources}
    print(f"Will skip {len(skip_bulk):,} keys already attributed by bulk",
          file=sys.stderr)

    # Bulk scan.
    oa_dir = Path(OPENALEX_DIR)
    gz_files = sorted(oa_dir.glob('**/*.gz'))
    if not gz_files:
        sys.exit(f"No .gz files under OPENALEX_DIR={oa_dir}")
    print(f"Scanning {len(gz_files)} OpenAlex .gz files...", file=sys.stderr)

    n_oa = 0
    n_new = 0
    t0 = time.time()
    last_flush = t0

    for fi, gz_path in enumerate(gz_files):
        if (fi + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  file {fi+1}/{len(gz_files)} | OA={n_oa:,} "
                  f"| new countries={n_new:,} | total={len(records):,} "
                  f"| {elapsed:.0f}s", file=sys.stderr)
            # Flush every ~30 min so a kill mid-run loses < 30 min of work.
            if time.time() - last_flush > 1800:
                write_all(out_path, records)
                last_flush = time.time()

        with gzip.open(gz_path, 'rt', encoding='utf-8') as gf:
            for line in gf:
                try:
                    work = json.loads(line)
                except json.JSONDecodeError:
                    continue

                pub_year = work.get('publication_year')
                if pub_year is None or pub_year < YEAR_MIN or pub_year > YEAR_MAX:
                    continue
                n_oa += 1

                matched_key = None
                source = ''
                doi_key = extract_doi_key(work.get('doi') or '')
                if doi_key:
                    k = ai_doi_to_key.get(doi_key)
                    if k is not None:
                        matched_key = k
                        source = 'bulk_doi'
                if matched_key is None:
                    nt = normalize_title(work.get('title') or '')
                    if nt:
                        k = ai_title_to_key.get(nt)
                        if k is not None:
                            matched_key = k
                            source = 'bulk_title'
                if matched_key is None or matched_key in skip_bulk:
                    continue

                country = infer_country(work.get('authorships') or [])
                if country is None:
                    continue

                # bulk_doi wins over bulk_title; never overwrite existing
                # bulk attribution for the same key.
                existing = records.get(matched_key)
                if existing and existing.get('country_source') in bulk_sources:
                    continue
                records[matched_key] = {
                    'dblp_key': matched_key,
                    'year': key_to_year.get(matched_key, ''),
                    'openalex_id': work.get('id', '') or '',
                    'country': country,
                    'country_source': source,
                }
                skip_bulk.add(matched_key)
                n_new += 1

    elapsed = time.time() - t0
    write_all(out_path, records)
    print(f"\nDone in {elapsed:.0f}s. {n_oa:,} OA papers scanned, "
          f"{n_new:,} new bulk countries, {len(records):,} total rows",
          file=sys.stderr)
    print(f"Saved: {out_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
