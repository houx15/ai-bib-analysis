"""
Step 11: US vs. China DBLP-AI publications per year (line plots, PDF).

Restricted to strong-matched papers — i.e. papers that appear in
data/output/dblp_ai_country.csv (steps 10a + 10b), which only attributes
country to bulk DOI/title matches and API doi_api / strong matches.

Two figures, mirroring two AI-identification methods:

  fig_country_title.pdf       — AI = title contains an AI keyword
  fig_country_title_venue.pdf — AI = title keyword OR known AI venue

Color: blue = US, orange = China.

The country CSV stores raw OpenAlex country codes ({CN, HK, TW, US}) so
the {CN,HK,TW} → "China" grouping is applied here, at plot time. To use
mainland CN only (excluding HK and TW), pass `--cn-only`.

Inputs:
  data/parsed/dblp_ai_papers.csv         (has title_is_ai, venue_is_ai flags)
  data/output/dblp_ai_country.csv        (from step 10a + 10b)

Outputs:
  data/output/fig_country_title.pdf
  data/output/fig_country_title_venue.pdf
  data/output/country_counts.csv         (raw per-code counts behind both plots)
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from dblp_config import PARSED_DIR, OUTPUT_DIR, YEAR_MIN, YEAR_MAX


US_COLOR = '#1f77b4'   # blue
CN_COLOR = '#ff7f0e'   # orange

RAW_CODES = ('US', 'CN', 'HK', 'TW')


def truthy(v: str) -> bool:
    return (v or '').strip().lower() in ('1', 'true', 't', 'yes', 'y')


def load_country_map() -> dict[str, str]:
    """Return {dblp_key: raw_country_code}. Codes are kept raw — no HK/TW
    collapsing at this layer."""
    path = OUTPUT_DIR / 'dblp_ai_country.csv'
    if not path.exists():
        sys.exit(f"Missing: {path}. Run steps 10a (and 10b) first.")
    out: dict[str, str] = {}
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            key = row.get('dblp_key', '')
            country = row.get('country', '')
            if key and country in RAW_CODES:
                out[key] = country
    return out


def count_by_year(country_map: dict[str, str],
                  ai_filter) -> dict[str, dict[int, int]]:
    """Return {raw_code: {year: count}} for DBLP AI papers passing
    ai_filter(row) AND with a strong country attribution."""
    counts: dict[str, dict[int, int]] = {c: defaultdict(int) for c in RAW_CODES}
    with open(PARSED_DIR / 'dblp_ai_papers.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                y = int(row['year'])
            except (ValueError, KeyError):
                continue
            if not (YEAR_MIN <= y <= YEAR_MAX):
                continue
            if not ai_filter(row):
                continue
            key = row.get('dblp_key', '')
            country = country_map.get(key)
            if country in counts:
                counts[country][y] += 1
    return counts


def aggregate_china(counts: dict[str, dict[int, int]],
                    cn_only: bool) -> dict[int, int]:
    """Return {year: china_count}. By default = CN ∪ HK ∪ TW; if
    cn_only=True, only mainland CN."""
    codes = ('CN',) if cn_only else ('CN', 'HK', 'TW')
    out: dict[int, int] = defaultdict(int)
    for code in codes:
        for y, n in counts[code].items():
            out[y] += n
    return out


def plot_lines(counts: dict[str, dict[int, int]],
               cn_only: bool,
               title: str, out_pdf) -> None:
    years = list(range(YEAR_MIN, YEAR_MAX + 1))
    us = [counts['US'].get(y, 0) for y in years]
    cn_agg = aggregate_china(counts, cn_only)
    cn = [cn_agg.get(y, 0) for y in years]

    cn_label = 'China (mainland)' if cn_only else 'China (CN+HK+TW)'

    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    ax.plot(years, us, marker='o', color=US_COLOR, label='United States',
            linewidth=2.0)
    ax.plot(years, cn, marker='o', color=CN_COLOR, label=cn_label,
            linewidth=2.0)

    ax.set_xlabel('Year')
    ax.set_ylabel('AI publications (DBLP, strong-matched in OpenAlex)')
    ax.set_title(title)
    ax.set_xticks(years)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='upper left', frameon=False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    fig.tight_layout()
    fig.savefig(out_pdf)
    plt.close(fig)
    print(f"Saved: {out_pdf}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cn-only', action='store_true',
                    help='Plot mainland CN only (exclude HK and TW). '
                         'Default: China = CN+HK+TW.')
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    country_map = load_country_map()
    print(f"Loaded country attributions for {len(country_map):,} DBLP AI papers "
          f"(US/CN/HK/TW only)")

    title_only = count_by_year(
        country_map,
        lambda r: truthy(r.get('title_is_ai', '')),
    )
    title_or_venue = count_by_year(
        country_map,
        lambda r: truthy(r.get('title_is_ai', '')) or truthy(r.get('venue_is_ai', '')),
    )

    plot_lines(title_only, args.cn_only,
               'DBLP AI publications by country (AI = title keyword)',
               OUTPUT_DIR / 'fig_country_title.pdf')
    plot_lines(title_or_venue, args.cn_only,
               'DBLP AI publications by country (AI = title keyword OR AI venue)',
               OUTPUT_DIR / 'fig_country_title_venue.pdf')

    # Raw per-code counts so re-aggregation never needs a re-run.
    csv_path = OUTPUT_DIR / 'country_counts.csv'
    years = list(range(YEAR_MIN, YEAR_MAX + 1))
    fieldnames = ['year']
    for ai_def in ('title', 'title_or_venue'):
        for code in ('us', 'cn', 'hk', 'tw'):
            fieldnames.append(f'{code}_{ai_def}')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(fieldnames)
        for y in years:
            row = [y]
            for src in (title_only, title_or_venue):
                for code in ('US', 'CN', 'HK', 'TW'):
                    row.append(src[code].get(y, 0))
            w.writerow(row)
    print(f"Saved: {csv_path}")


if __name__ == '__main__':
    main()
