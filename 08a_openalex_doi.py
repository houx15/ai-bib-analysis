"""
Step 8a: DOI-lookup stage (cheap, free on OpenAlex's filter pool).

For each DBLP AI paper in the step-06 residual that has a DOI, look it up
via /works/doi:<doi>. DOIs are globally unique, so a hit is recorded as an
exact match (tier='doi_api'). Papers without a DOI are NOT written here —
they automatically belong to the search-stage residual.

At the end, prints the count of papers that still need the paid search API
(step 08b): (papers with no DOI) + (papers whose DOI returned 404/errored).

Input:  data/output/dblp_ai_unmatched.csv   (from step 06)
Output: data/output/dblp_ai_doi_matches.csv (resumable; one row per DOI lookup)

Usage:
    python 08a_openalex_doi.py              # run/resume
    python 08a_openalex_doi.py --limit 5000
    python 08a_openalex_doi.py --sleep 0.15
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from dblp_config import OUTPUT_DIR
from openalex_utils import (
    print_auth_banner,
    query_doi,
    jaccard, title_tokens, dblp_surnames, oa_surnames,
)


FIELDNAMES = [
    'dblp_key', 'year', 'title', 'dblp_doi',
    'matched', 'tier',
    'title_sim', 'author_overlap',
    'openalex_id', 'openalex_doi', 'openalex_title', 'openalex_year',
    'error',
]


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
    ap.add_argument('--output', default=str(OUTPUT_DIR / 'dblp_ai_doi_matches.csv'))
    ap.add_argument('--sleep', type=float, default=0.15)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    print_auth_banner()

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        sys.exit(f"Missing input: {in_path}. Run step 06 first.")

    done = load_checkpoint(out_path)

    # Read residual; partition into "has DOI" (this stage) vs "no DOI"
    # (counted and skipped — they belong to the search stage).
    with_doi: list[dict] = []
    no_doi_count = 0
    with open(in_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if (row.get('doi', '') or '').strip():
                if row.get('dblp_key') in done:
                    continue
                with_doi.append(row)
            else:
                no_doi_count += 1

    print(f"Checkpoint: {len(done):,} DOI lookups already done", file=sys.stderr)
    print(f"To process: {len(with_doi):,} papers with DOI", file=sys.stderr)
    print(f"No DOI: {no_doi_count:,} (go directly to search stage)", file=sys.stderr)

    todo = with_doi[:args.limit] if args.limit else with_doi
    if args.limit:
        print(f"Limiting to first {len(todo):,}", file=sys.stderr)

    write_header = not out_path.exists()
    fout = open(out_path, 'a', newline='', encoding='utf-8')
    writer = csv.DictWriter(fout, fieldnames=FIELDNAMES)
    if write_header:
        writer.writeheader()
        fout.flush()

    n_matched = 0
    n_404 = 0
    n_errors = 0
    t0 = time.time()

    for i, row in enumerate(todo):
        dblp_key = row.get('dblp_key', '')
        title = row.get('title', '') or ''
        authors = row.get('authors', '') or ''
        dblp_doi = row.get('doi', '') or ''
        try:
            year = int(row['year'])
        except (KeyError, ValueError):
            continue

        out_row = {k: '' for k in FIELDNAMES}
        out_row.update({
            'dblp_key': dblp_key, 'year': year, 'title': title,
            'dblp_doi': dblp_doi, 'matched': '0', 'tier': '',
        })

        try:
            oa = query_doi(dblp_doi)
        except Exception as e:
            oa = None
            out_row['error'] = str(e)[:200]
            n_errors += 1
            time.sleep(1.0)

        if oa is not None:
            out_row['openalex_id'] = oa.get('id', '')
            out_row['openalex_doi'] = oa.get('doi', '') or ''
            out_row['openalex_title'] = oa.get('title') or oa.get('display_name') or ''
            out_row['openalex_year'] = oa.get('publication_year', '')
            out_row['matched'] = '1'
            out_row['tier'] = 'doi_api'
            sim = jaccard(title_tokens(title), title_tokens(
                oa.get('title') or oa.get('display_name') or ''))
            overlap = len(dblp_surnames(authors) & oa_surnames(oa))
            out_row['title_sim'] = f"{sim:.3f}"
            out_row['author_overlap'] = overlap
            n_matched += 1
        elif not out_row['error']:
            # 404 — DOI not in OpenAlex.
            n_404 += 1

        writer.writerow(out_row)

        if (i + 1) % 200 == 0:
            fout.flush()
            elapsed = time.time() - t0
            rate = (i + 1) / max(elapsed, 1e-9)
            eta = (len(todo) - i - 1) / max(rate, 1e-9)
            print(f"  {i+1:,}/{len(todo):,} | matched={n_matched:,} "
                  f"404={n_404:,} err={n_errors:,} | "
                  f"{rate:.1f} req/s | eta {eta/60:.1f}m", file=sys.stderr)

        time.sleep(args.sleep)

    fout.close()
    elapsed = time.time() - t0

    # Recompute totals across the whole output file (including prior runs)
    # so the "remaining" count is accurate on resume too.
    total_matched = 0
    total_not_matched = 0
    with open(out_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('matched') == '1':
                total_matched += 1
            else:
                total_not_matched += 1

    search_residual = no_doi_count + total_not_matched

    print(f"\nDone in {elapsed:.0f}s", file=sys.stderr)
    print(f"  processed this run: {len(todo):,}", file=sys.stderr)
    print(f"  matched this run:   {n_matched:,} (404={n_404:,}, errors={n_errors:,})",
          file=sys.stderr)
    print(f"Output: {out_path}", file=sys.stderr)
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"DOI stage totals (cumulative across all runs):", file=sys.stderr)
    print(f"  matched by DOI:        {total_matched:,}", file=sys.stderr)
    print(f"  DOI lookup failed:     {total_not_matched:,} "
          f"(404 + errors)", file=sys.stderr)
    print(f"  papers with no DOI:    {no_doi_count:,}", file=sys.stderr)
    print(f"  → need search API (step 08b): {search_residual:,}",
          file=sys.stderr)
    print("=" * 60, file=sys.stderr)


if __name__ == '__main__':
    main()
