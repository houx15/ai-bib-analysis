"""
Step 4: Cross-reference DBLP AI papers with OpenAlex to get country info.

DBLP affiliation data is sparse. This script matches DBLP papers to OpenAlex
works by DOI (primary) and by normalized title (fallback), then pulls the
country attribution from OpenAlex.

This step is OPTIONAL – only needed if step 3's report shows low affiliation
coverage from DBLP alone.

Approach:
  - Load DBLP AI papers (from step 3 output)
  - Scan OpenAlex bulk data (same approach as the original study)
  - Match by DOI first, then by normalized title
  - Write back the country for matched papers

Usage:
    python 04_crossref_openalex.py \
        --dblp-ai data/parsed/dblp_ai_papers.csv \
        --openalex-dir /path/to/openalex/works \
        --output data/parsed/dblp_ai_papers_with_country.csv

NOTE: You need access to OpenAlex bulk data on the server.
"""

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
from pathlib import Path
from dblp_config import PARSED_DIR, YEAR_MIN, YEAR_MAX, OPENALEX_DIR


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def extract_doi_key(doi_url: str) -> str:
    """Extract the DOI path from a URL, e.g. '10.1234/foo' from 'https://doi.org/10.1234/foo'."""
    if not doi_url:
        return ''
    doi_url = doi_url.strip()
    for prefix in ['https://doi.org/', 'http://doi.org/', 'http://dx.doi.org/', 'https://dx.doi.org/']:
        if doi_url.startswith(prefix):
            return doi_url[len(prefix):].lower()
    if doi_url.startswith('10.'):
        return doi_url.lower()
    return ''


def infer_country_from_openalex(authorships: list) -> str | None:
    """Replicate the original study's country logic on OpenAlex authorships."""
    # Try corresponding author first
    for a in authorships:
        if a.get('is_corresponding') and a.get('countries'):
            return a['countries'][0]
    # Fallback to first author
    for a in authorships:
        if a.get('author_position') == 'first' and a.get('countries'):
            return a['countries'][0]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dblp-ai', default=str(PARSED_DIR / 'dblp_ai_papers.csv'))
    parser.add_argument('--openalex-dir', default=str(OPENALEX_DIR),
                        help='Path to OpenAlex works/ directory with .gz files')
    parser.add_argument('--output', default=str(PARSED_DIR / 'dblp_ai_papers_with_country.csv'))
    args = parser.parse_args()

    # 1. Load DBLP AI papers, build lookup indices
    print("Loading DBLP AI papers...", file=sys.stderr)
    dblp_rows = []
    doi_to_idx = {}   # doi_key -> row index
    title_to_idx = {} # normalized_title -> row index (first match wins)

    with open(args.dblp_ai, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            dblp_rows.append(row)
            # DOI index
            doi_key = extract_doi_key(row.get('doi', ''))
            if doi_key and doi_key not in doi_to_idx:
                doi_to_idx[doi_key] = i
            # Title index
            nt = normalize_title(row.get('title', ''))
            if nt and nt not in title_to_idx:
                title_to_idx[nt] = i

    print(f"Loaded {len(dblp_rows):,} DBLP AI papers", file=sys.stderr)
    print(f"  DOI index: {len(doi_to_idx):,} entries", file=sys.stderr)
    print(f"  Title index: {len(title_to_idx):,} entries", file=sys.stderr)

    # Track which rows got a country from this cross-ref
    country_from_openalex = [None] * len(dblp_rows)
    n_matched_doi = 0
    n_matched_title = 0
    n_country_found = 0

    # 2. Scan OpenAlex works
    oa_dir = Path(args.openalex_dir)
    gz_files = sorted(oa_dir.glob('**/*.gz'))
    print(f"Scanning {len(gz_files)} OpenAlex .gz files...", file=sys.stderr)
    t0 = time.time()

    for fi, gz_path in enumerate(gz_files):
        if (fi + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  file {fi+1}/{len(gz_files)} ({elapsed:.0f}s, DOI matches={n_matched_doi}, title matches={n_matched_title})",
                  file=sys.stderr)

        with gzip.open(gz_path, 'rt', encoding='utf-8') as gf:
            for line in gf:
                try:
                    work = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Quick year filter
                pub_year = work.get('publication_year')
                if pub_year is None or pub_year < YEAR_MIN or pub_year > YEAR_MAX:
                    continue

                # Try DOI match
                matched_idx = None
                oa_doi = work.get('doi', '') or ''
                doi_key = extract_doi_key(oa_doi)
                if doi_key and doi_key in doi_to_idx:
                    matched_idx = doi_to_idx[doi_key]
                    n_matched_doi += 1

                # Try title match if no DOI match
                if matched_idx is None:
                    oa_title = work.get('title', '') or ''
                    nt = normalize_title(oa_title)
                    if nt and nt in title_to_idx:
                        matched_idx = title_to_idx[nt]
                        n_matched_title += 1

                if matched_idx is None:
                    continue

                # Already have country from DBLP? Skip
                if dblp_rows[matched_idx].get('country'):
                    continue
                # Already matched from OpenAlex? Skip
                if country_from_openalex[matched_idx]:
                    continue

                # Infer country
                authorships = work.get('authorships', [])
                country = infer_country_from_openalex(authorships)
                if country and country in ('CN', 'HK', 'TW', 'US'):
                    # Map HK/TW to CN like the original study
                    if country in ('HK', 'TW'):
                        country = 'CN'
                    country_from_openalex[matched_idx] = country
                    n_country_found += 1

    elapsed = time.time() - t0
    print(f"\nOpenAlex scan done in {elapsed:.0f}s", file=sys.stderr)
    print(f"  DOI matches:   {n_matched_doi:,}", file=sys.stderr)
    print(f"  Title matches: {n_matched_title:,}", file=sys.stderr)
    print(f"  Country found: {n_country_found:,}", file=sys.stderr)

    # 3. Merge and write output
    fieldnames = list(dblp_rows[0].keys()) + ['country_source']
    # Ensure 'country' is in fieldnames
    if 'country_source' not in fieldnames:
        fieldnames.append('country_source')

    with open(args.output, 'w', newline='', encoding='utf-8') as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        n_dblp_country = 0
        n_oa_country = 0
        n_no_country = 0

        for i, row in enumerate(dblp_rows):
            row = dict(row)
            if row.get('country'):
                row['country_source'] = 'dblp'
                n_dblp_country += 1
            elif country_from_openalex[i]:
                row['country'] = country_from_openalex[i]
                row['country_source'] = 'openalex'
                n_oa_country += 1
            else:
                row['country_source'] = ''
                n_no_country += 1
            writer.writerow(row)

    print(f"\nOutput: {args.output}", file=sys.stderr)
    print(f"  Country from DBLP:     {n_dblp_country:,}", file=sys.stderr)
    print(f"  Country from OpenAlex: {n_oa_country:,}", file=sys.stderr)
    print(f"  No country:            {n_no_country:,}", file=sys.stderr)


if __name__ == '__main__':
    main()
