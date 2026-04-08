"""
Quick DBLP-only statistics (no OpenAlex scan).

For each year reports:
  - total DBLP papers
  - DBLP AI papers (count + % of total)
  - of AI: how many conference papers (count + %)
  - of AI: how many lack a DOI (count + %)
  - of AI conference papers: how many lack a DOI (count + %)

The "no DOI" count is a fast lower-bound proxy for "not in OpenAlex":
OpenAlex ingests primarily from Crossref/DOI, so a paper without a DOI
is very likely absent from OA.

Inputs:
  data/parsed/dblp_papers.csv     (from step 02)
  data/parsed/dblp_ai_papers.csv  (from step 03)

Outputs:
  data/output/quick_estimate.csv
  data/output/quick_estimate.txt
"""

from __future__ import annotations

import csv
from collections import defaultdict

from dblp_config import PARSED_DIR, OUTPUT_DIR, YEAR_MIN, YEAR_MAX


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    years = list(range(YEAR_MIN, YEAR_MAX + 1))

    # Total DBLP papers per year (from step 02)
    total_by_year: dict[int, int] = defaultdict(int)
    with open(PARSED_DIR / 'dblp_papers.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                y = int(row['year'])
            except (ValueError, KeyError):
                continue
            if YEAR_MIN <= y <= YEAR_MAX:
                total_by_year[y] += 1

    # AI paper breakdown per year (from step 03)
    stats = defaultdict(lambda: defaultdict(int))
    venue_no_doi: dict[str, int] = defaultdict(int)

    with open(PARSED_DIR / 'dblp_ai_papers.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                y = int(row['year'])
            except (ValueError, KeyError):
                continue
            if not (YEAR_MIN <= y <= YEAR_MAX):
                continue

            has_doi = bool(row.get('doi', '').strip())
            is_conf = row.get('venue_type', '') == 'conference'

            s = stats[y]
            s['ai'] += 1
            if has_doi:
                s['ai_doi'] += 1
            else:
                s['ai_nodoi'] += 1
            if is_conf:
                s['conf'] += 1
                if has_doi:
                    s['conf_doi'] += 1
                else:
                    s['conf_nodoi'] += 1
            if not has_doi:
                venue_no_doi[row.get('venue', '(unknown)')] += 1

    # ── Print table ──────────────────────────────────────────────────────
    header = (f"{'Year':>6} {'DBLP':>10} {'AI':>9} {'AI%':>6} "
              f"{'Conf':>9} {'Conf/AI%':>9} "
              f"{'AI-noDOI':>10} {'noDOI%':>7} "
              f"{'Conf-noDOI':>12} {'cnoDOI%':>8}")
    sep = "-" * len(header)

    lines = []
    lines.append("=" * len(header))
    lines.append("DBLP AI papers — per-year breakdown (no OpenAlex needed)")
    lines.append("=" * len(header))
    lines.append(header)
    lines.append(sep)

    totals = defaultdict(int)
    for y in years:
        s = stats[y]
        t = total_by_year[y]
        ai = s['ai']
        cf = s['conf']
        ai_nd = s['ai_nodoi']
        cf_nd = s['conf_nodoi']
        lines.append(
            f"{y:>6} {t:>10,} {ai:>9,} {100*ai/max(t,1):>5.1f}% "
            f"{cf:>9,} {100*cf/max(ai,1):>8.1f}% "
            f"{ai_nd:>10,} {100*ai_nd/max(ai,1):>6.1f}% "
            f"{cf_nd:>12,} {100*cf_nd/max(cf,1):>7.1f}%"
        )
        totals['dblp'] += t
        totals['ai'] += ai
        totals['conf'] += cf
        totals['ai_nd'] += ai_nd
        totals['conf_nd'] += cf_nd

    lines.append(sep)
    lines.append(
        f"{'TOTAL':>6} {totals['dblp']:>10,} {totals['ai']:>9,} "
        f"{100*totals['ai']/max(totals['dblp'],1):>5.1f}% "
        f"{totals['conf']:>9,} {100*totals['conf']/max(totals['ai'],1):>8.1f}% "
        f"{totals['ai_nd']:>10,} {100*totals['ai_nd']/max(totals['ai'],1):>6.1f}% "
        f"{totals['conf_nd']:>12,} {100*totals['conf_nd']/max(totals['conf'],1):>7.1f}%"
    )
    lines.append("")
    lines.append(f"~{totals['ai_nd']:,} DBLP AI papers have no DOI (likely NOT in OpenAlex)")
    lines.append(f"~{totals['conf_nd']:,} of those are conference papers")

    lines.append("")
    lines.append("--- Top 20 venues among no-DOI AI papers ---")
    for venue, cnt in sorted(venue_no_doi.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {cnt:>6,}  {venue}")

    report = '\n'.join(lines)
    print(report)

    (OUTPUT_DIR / 'quick_estimate.txt').write_text(report + '\n')

    # CSV
    out = OUTPUT_DIR / 'quick_estimate.csv'
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['year', 'dblp_total', 'ai', 'ai_pct',
                    'conf', 'conf_of_ai_pct',
                    'ai_no_doi', 'ai_no_doi_pct',
                    'conf_no_doi', 'conf_no_doi_pct'])
        for y in years:
            s = stats[y]
            t = total_by_year[y]
            ai = s['ai']
            cf = s['conf']
            w.writerow([y, t, ai, f"{100*ai/max(t,1):.1f}",
                        cf, f"{100*cf/max(ai,1):.1f}",
                        s['ai_nodoi'], f"{100*s['ai_nodoi']/max(ai,1):.1f}",
                        s['conf_nodoi'], f"{100*s['conf_nodoi']/max(cf,1):.1f}"])
    print(f"\nSaved: {out}")
    print(f"Saved: {OUTPUT_DIR / 'quick_estimate.txt'}")


if __name__ == '__main__':
    main()
