"""
Step 5: Aggregate AI paper counts by year × country and produce summary tables + plot.

Input: either dblp_ai_papers.csv (DBLP-only country) or
       dblp_ai_papers_with_country.csv (after OpenAlex cross-ref)

Output:
  - data/output/yearly_counts.csv
  - data/output/yearly_counts_by_method.csv  (title-only vs venue-only vs both)
  - data/output/summary_stats.txt
  - data/output/fig_cn_vs_us.png

Usage:
    python 05_aggregate_counts.py [--input data/parsed/dblp_ai_papers_with_country.csv]
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from dblp_config import OUTPUT_DIR, YEAR_MIN, YEAR_MAX


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default=None,
                        help='AI papers CSV (with country column)')
    args = parser.parse_args()

    # Auto-detect input
    from dblp_config import PARSED_DIR
    if args.input:
        input_path = Path(args.input)
    else:
        # Prefer cross-referenced version
        crossref = PARSED_DIR / 'dblp_ai_papers_with_country.csv'
        plain = PARSED_DIR / 'dblp_ai_papers.csv'
        input_path = crossref if crossref.exists() else plain
    print(f"Reading from: {input_path}", file=sys.stderr)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # year -> country -> count
    counts = defaultdict(lambda: defaultdict(int))
    # year -> country -> {title_only, venue_only, both}
    method_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    total_ai = 0
    total_cn = 0
    total_us = 0
    total_no_country = 0

    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_ai += 1
            year = int(row['year'])
            country = row.get('country', '').strip()

            if country not in ('CN', 'US'):
                total_no_country += 1
                continue

            if country == 'CN':
                total_cn += 1
            else:
                total_us += 1

            counts[year][country] += 1

            # Method breakdown
            t_ai = row.get('title_is_ai', '0') == '1'
            v_ai = row.get('venue_is_ai', '0') == '1'
            if t_ai and v_ai:
                method_counts[year][country]['both'] += 1
            elif t_ai:
                method_counts[year][country]['title_only'] += 1
            elif v_ai:
                method_counts[year][country]['venue_only'] += 1

    years = list(range(YEAR_MIN, YEAR_MAX + 1))

    # ── Yearly counts CSV ────────────────────────────────────────────────
    csv_path = OUTPUT_DIR / 'yearly_counts.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['year', 'CN', 'US'])
        for y in years:
            writer.writerow([y, counts[y].get('CN', 0), counts[y].get('US', 0)])
    print(f"Saved: {csv_path}")

    # ── Method breakdown CSV ─────────────────────────────────────────────
    csv_path2 = OUTPUT_DIR / 'yearly_counts_by_method.csv'
    with open(csv_path2, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['year', 'country', 'title_only', 'venue_only', 'both', 'total'])
        for y in years:
            for c in ('CN', 'US'):
                mc = method_counts[y][c]
                total = mc['title_only'] + mc['venue_only'] + mc['both']
                writer.writerow([y, c, mc['title_only'], mc['venue_only'], mc['both'], total])
    print(f"Saved: {csv_path2}")

    # ── Summary stats ────────────────────────────────────────────────────
    summary = [
        f"=== DBLP AI Paper Counts Summary ===",
        f"Input: {input_path}",
        f"Total AI papers: {total_ai:,}",
        f"  CN (with country): {total_cn:,}",
        f"  US (with country): {total_us:,}",
        f"  No country / other: {total_no_country:,}",
        f"  Country coverage: {100*(total_cn+total_us)/max(total_ai,1):.1f}%",
        f"",
        f"Year   CN        US",
        f"{'─'*30}",
    ]
    for y in years:
        cn = counts[y].get('CN', 0)
        us = counts[y].get('US', 0)
        summary.append(f"{y}   {cn:>7,}   {us:>7,}")

    summary_text = '\n'.join(summary)
    print(summary_text)
    with open(OUTPUT_DIR / 'summary_stats.txt', 'w') as f:
        f.write(summary_text)

    # ── Plot ─────────────────────────────────────────────────────────────
    cn_vals = [counts[y].get('CN', 0) for y in years]
    us_vals = [counts[y].get('US', 0) for y in years]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(years, cn_vals, 'o-', color='#fd8d3c', linewidth=2, markersize=6, label='China')
    ax.plot(years, us_vals, 's-', color='#6baed6', linewidth=2, markersize=6, label='United States')
    ax.set_xlabel('Year')
    ax.set_ylabel('Number of AI-related publications')
    ax.set_title('DBLP: AI Publications by Country')
    ax.legend()
    ax.set_xticks(years)
    ax.set_xticklabels(years, rotation=45)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    fig_path = OUTPUT_DIR / 'fig_cn_vs_us.png'
    fig.savefig(fig_path, dpi=150)
    print(f"Saved: {fig_path}")
    plt.close(fig)


if __name__ == '__main__':
    main()
