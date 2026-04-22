"""
Step 8b: Search API stage (paid — each call counts against the OpenAlex
search quota: 1,000/day free, or more on paid plans).

Run this AFTER step 08a has finished (at least one pass), and AFTER you've
set up your OpenAlex billing if the search residual is large.

Residual = papers in step-06 unmatched that are not already matched via
the DOI stage (i.e. no DOI, or DOI returned 404 / errored in 08a).

For each residual paper, hit the search API and apply fuzzy classify:

  title_sim   = token-set Jaccard(dblp_title, oa_title)
  author_hit  = |dblp_surnames ∩ oa_surnames| ≥ 1
  year_ok     = |dblp_year - oa_year| ≤ 1

  ACCEPT (year_ok required) if any of:
    - title_sim ≥ 0.9                              → tier "strong"
    - title_sim ≥ 0.6 AND author_hit               → tier "title_author"
    - title_sim ≥ 0.5 AND author_hit AND rel ≥ 50  → tier "weak"

Input:  data/output/dblp_ai_unmatched.csv        (from step 06)
        data/output/dblp_ai_doi_matches.csv      (from step 08a)
Output: data/output/dblp_ai_search_matches.csv   (resumable)

Usage:
    python 08b_openalex_search.py              # run/resume
    python 08b_openalex_search.py --limit 500  # stop after N calls
    python 08b_openalex_search.py --sleep 0.15
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from dblp_config import OUTPUT_DIR
from openalex_utils import print_auth_banner, query_top1, classify


FIELDNAMES = [
    'dblp_key', 'year', 'title', 'dblp_doi',
    'matched', 'tier',
    'title_sim', 'author_overlap', 'relevance_score',
    'openalex_id', 'openalex_doi', 'openalex_title', 'openalex_year',
    'error',
]


def load_dblp_keys(path: Path, only_matched: bool = False) -> set[str]:
    if not path.exists():
        return set()
    keys = set()
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if only_matched and row.get('matched') != '1':
                continue
            keys.add(row.get('dblp_key', ''))
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default=str(OUTPUT_DIR / 'dblp_ai_unmatched.csv'))
    ap.add_argument('--doi-matches', default=str(OUTPUT_DIR / 'dblp_ai_doi_matches.csv'))
    ap.add_argument('--output', default=str(OUTPUT_DIR / 'dblp_ai_search_matches.csv'))
    ap.add_argument('--sleep', type=float, default=0.15)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    print_auth_banner()

    in_path = Path(args.input)
    doi_path = Path(args.doi_matches)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        sys.exit(f"Missing input: {in_path}. Run step 06 first.")
    if not doi_path.exists():
        print(f"NOTE: {doi_path} not found — step 08a has not run yet. "
              f"Proceeding as if no papers were matched by DOI (all residual "
              f"goes to search).", file=sys.stderr)

    matched_by_doi = load_dblp_keys(doi_path, only_matched=True)
    already_searched = load_dblp_keys(out_path)
    print(f"Already matched by DOI (08a): {len(matched_by_doi):,} (skipped)",
          file=sys.stderr)
    print(f"Checkpoint (08b): {len(already_searched):,} search rows already written",
          file=sys.stderr)

    todo: list[dict] = []
    with open(in_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            key = row.get('dblp_key', '')
            if key in matched_by_doi or key in already_searched:
                continue
            todo.append(row)
    print(f"To process via search: {len(todo):,}", file=sys.stderr)
    if args.limit:
        todo = todo[:args.limit]
        print(f"Limiting to first {len(todo):,}", file=sys.stderr)

    write_header = not out_path.exists()
    fout = open(out_path, 'a', newline='', encoding='utf-8')
    writer = csv.DictWriter(fout, fieldnames=FIELDNAMES)
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
            oa = query_top1(title, year)
            if oa is not None:
                tier, sim, overlap, rel = classify(title, year, authors, oa)
                out_row['title_sim'] = f"{sim:.3f}"
                out_row['author_overlap'] = overlap
                out_row['relevance_score'] = f"{rel:.1f}"
                out_row['openalex_id'] = oa.get('id', '')
                out_row['openalex_doi'] = oa.get('doi', '') or ''
                out_row['openalex_title'] = oa.get('title') or oa.get('display_name') or ''
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
