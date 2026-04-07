"""
Quick estimate of DBLP-only AI papers WITHOUT scanning OpenAlex.

Logic: DBLP AI papers with a DOI are almost certainly in OpenAlex
(OpenAlex ingests from Crossref/DOI). Papers without a DOI are
likely DBLP-only (workshops, some conference papers, etc.).

This gives a fast lower-bound estimate of the DBLP-OpenAlex gap.

Input:  data/parsed/dblp_ai_papers.csv (from step 03)
Output: prints table + saves data/output/quick_estimate.csv

Usage:
    python 07_quick_estimate.py
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from dblp_config import PARSED_DIR, OUTPUT_DIR, YEAR_MIN, YEAR_MAX


def main():
    ai_csv = PARSED_DIR / 'dblp_ai_papers.csv'
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # year -> {total, has_doi, no_doi, conf_total, conf_has_doi, conf_no_doi}
    stats = defaultdict(lambda: defaultdict(int))
    # Also track venue type breakdown
    venue_no_doi = defaultdict(int)  # venue -> count of no-DOI papers

    with open(ai_csv, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            year = int(row['year'])
            has_doi = bool(row.get('doi', '').strip())
            is_conf = row.get('venue_type', '') == 'conference'

            stats[year]['total'] += 1
            if has_doi:
                stats[year]['has_doi'] += 1
            else:
                stats[year]['no_doi'] += 1

            if is_conf:
                stats[year]['conf_total'] += 1
                if has_doi:
                    stats[year]['conf_has_doi'] += 1
                else:
                    stats[year]['conf_no_doi'] += 1

            if not has_doi:
                venue = row.get('venue', '(unknown)')
                venue_no_doi[venue] += 1

    years = list(range(YEAR_MIN, YEAR_MAX + 1))

    # Print table
    print("=" * 90)
    print("Quick Estimate: DBLP AI Papers — DOI coverage as proxy for OpenAlex overlap")
    print("=" * 90)
    print(f"{'Year':>6} {'Total':>8} {'w/ DOI':>8} {'no DOI':>8} {'no DOI%':>8} "
          f"{'Conf':>8} {'Conf noDOI':>10} {'Conf noDOI%':>11}")
    print("-" * 90)

    totals = defaultdict(int)
    for y in years:
        s = stats[y]
        t = s['total']
        d = s['has_doi']
        nd = s['no_doi']
        ct = s['conf_total']
        cnd = s['conf_no_doi']
        pct = 100 * nd / max(t, 1)
        cpct = 100 * cnd / max(ct, 1)
        print(f"{y:>6} {t:>8,} {d:>8,} {nd:>8,} {pct:>7.1f}% "
              f"{ct:>8,} {cnd:>10,} {cpct:>10.1f}%")
        for k in ['total', 'has_doi', 'no_doi', 'conf_total', 'conf_no_doi']:
            totals[k] += s[k]

    print("-" * 90)
    print(f"{'TOTAL':>6} {totals['total']:>8,} {totals['has_doi']:>8,} {totals['no_doi']:>8,} "
          f"{100*totals['no_doi']/max(totals['total'],1):>7.1f}% "
          f"{totals['conf_total']:>8,} {totals['conf_no_doi']:>10,} "
          f"{100*totals['conf_no_doi']/max(totals['conf_total'],1):>10.1f}%")

    print(f"\n  → ~{totals['no_doi']:,} DBLP AI papers likely NOT in OpenAlex")
    print(f"  → ~{totals['conf_no_doi']:,} of those are conference papers")

    # Top venues with no-DOI papers
    print(f"\n--- Top 20 venues with most no-DOI AI papers ---")
    for venue, count in sorted(venue_no_doi.items(), key=lambda x: -x[1])[:20]:
        print(f"  {count:>6,}  {venue}")

    # Save CSV
    out_path = OUTPUT_DIR / 'quick_estimate.csv'
    with open(out_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['year', 'ai_total', 'has_doi', 'no_doi', 'no_doi_pct',
                     'conf_total', 'conf_no_doi', 'conf_no_doi_pct'])
        for y in years:
            s = stats[y]
            w.writerow([y, s['total'], s['has_doi'], s['no_doi'],
                         f"{100*s['no_doi']/max(s['total'],1):.1f}",
                         s['conf_total'], s['conf_no_doi'],
                         f"{100*s['conf_no_doi']/max(s['conf_total'],1):.1f}"])
    print(f"\nSaved: {out_path}")


if __name__ == '__main__':
    main()
