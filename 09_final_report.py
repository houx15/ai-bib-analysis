"""
Step 9: Final per-year percentages combining three cumulative match strategies.

  Algo 1: DOI exact match                       (from step 06)
  Algo 2: + normalized-title exact match        (from step 06)
  Algo 3: + OpenAlex Search API (fuzzy)         (from step 08)

Inputs:
  data/parsed/dblp_papers.csv
  data/parsed/dblp_ai_papers.csv
  data/output/coverage_ai_papers.csv
  data/output/dblp_ai_api_matches.csv
  data/output/dblp_ai_unmatched.csv

Outputs:
  data/output/final_report.txt
  data/output/final_report.csv
"""

from __future__ import annotations

import csv
from collections import defaultdict

from dblp_config import PARSED_DIR, OUTPUT_DIR, YEAR_MIN, YEAR_MAX


def main():
    years = list(range(YEAR_MIN, YEAR_MAX + 1))

    # ── DBLP totals per year ──────────────────────────────────────────────
    dblp_total: dict[int, int] = defaultdict(int)
    with open(PARSED_DIR / 'dblp_papers.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                y = int(row['year'])
            except (ValueError, KeyError):
                continue
            if YEAR_MIN <= y <= YEAR_MAX:
                dblp_total[y] += 1

    # ── DBLP AI breakdown per year ────────────────────────────────────────
    ai_total: dict[int, int] = defaultdict(int)
    ai_conf: dict[int, int] = defaultdict(int)
    ai_nodoi: dict[int, int] = defaultdict(int)
    with open(PARSED_DIR / 'dblp_ai_papers.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                y = int(row['year'])
            except (ValueError, KeyError):
                continue
            if not (YEAR_MIN <= y <= YEAR_MAX):
                continue
            ai_total[y] += 1
            if row.get('venue_type', '') == 'conference':
                ai_conf[y] += 1
            if not (row.get('doi', '') or '').strip():
                ai_nodoi[y] += 1

    # ── Bulk match counts from step 06 ────────────────────────────────────
    algo1: dict[int, int] = defaultdict(int)  # DOI only
    algo2: dict[int, int] = defaultdict(int)  # DOI | Title
    cov_path = OUTPUT_DIR / 'coverage_ai_papers.csv'
    if cov_path.exists():
        with open(cov_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                y = int(row['year'])
                algo1[y] = int(row['matched_by_doi'])
                algo2[y] = int(row['matched_by_doi_or_title'])
    else:
        print(f"WARNING: {cov_path} not found")

    # ── API matches from step 08 (with tier breakdown) ────────────────────
    api_by_tier: dict[str, dict[int, int]] = {
        'strong': defaultdict(int),
        'title_author': defaultdict(int),
        'weak': defaultdict(int),
    }
    api_any: dict[int, int] = defaultdict(int)  # any tier
    api_path = OUTPUT_DIR / 'dblp_ai_api_matches.csv'
    if api_path.exists():
        with open(api_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('matched', '0') != '1':
                    continue
                try:
                    y = int(row['year'])
                except (ValueError, KeyError):
                    continue
                if not (YEAR_MIN <= y <= YEAR_MAX):
                    continue
                tier = row.get('tier', '') or 'weak'
                if tier in api_by_tier:
                    api_by_tier[tier][y] += 1
                api_any[y] += 1
    else:
        print(f"NOTE: {api_path} not found — step 08 not yet run")

    # ── Assemble rows ─────────────────────────────────────────────────────
    def pct(n, d): return f"{100*n/max(d,1):.1f}"

    rows = []
    for y in years:
        t = dblp_total[y]
        ai = ai_total[y]
        cf = ai_conf[y]
        nd = ai_nodoi[y]
        a1 = algo1[y]
        a2 = algo2[y]
        api = api_any[y]
        a3 = a2 + api          # cumulative — API is additive on top of DOI|Title
        unm = ai - a3
        rows.append({
            'year': y,
            'dblp_total': t,
            'ai': ai,
            'ai_pct': pct(ai, t),
            'conf': cf,
            'conf_of_ai_pct': pct(cf, ai),
            'ai_no_doi': nd,
            'ai_no_doi_pct': pct(nd, ai),
            'algo1_doi': a1,
            'algo1_pct': pct(a1, ai),
            'algo2_doi_title': a2,
            'algo2_pct': pct(a2, ai),
            'algo3_doi_title_api': a3,
            'algo3_pct': pct(a3, ai),
            'api_strong': api_by_tier['strong'][y],
            'api_title_author': api_by_tier['title_author'][y],
            'api_weak': api_by_tier['weak'][y],
            'unmatched': unm,
            'unmatched_pct': pct(unm, ai),
        })

    # ── CSV ───────────────────────────────────────────────────────────────
    csv_path = OUTPUT_DIR / 'final_report.csv'
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    # ── Text report ───────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 110)
    lines.append("FINAL REPORT — DBLP AI papers, per year")
    lines.append("=" * 110)

    lines.append("\n[1] DBLP composition (no OpenAlex)")
    lines.append(f"{'Year':>6} {'DBLP':>10} {'AI':>9} {'AI%':>6} "
                 f"{'Conf':>9} {'Conf/AI%':>9} {'AI noDOI':>10} {'noDOI%':>7}")
    lines.append("-" * 75)
    for r in rows:
        lines.append(f"{r['year']:>6} {r['dblp_total']:>10,} {r['ai']:>9,} "
                     f"{r['ai_pct']:>5}% {r['conf']:>9,} {r['conf_of_ai_pct']:>8}% "
                     f"{r['ai_no_doi']:>10,} {r['ai_no_doi_pct']:>6}%")

    lines.append("\n[2] Cumulative match coverage (DBLP AI → OpenAlex)")
    lines.append(f"{'Year':>6} {'DBLP-AI':>9} "
                 f"{'Algo1:DOI':>11} {'A1%':>6} "
                 f"{'Algo2:+Title':>13} {'A2%':>6} "
                 f"{'Algo3:+API':>12} {'A3%':>6} "
                 f"{'Unmatched':>10} {'Unm%':>7}")
    lines.append("-" * 100)
    for r in rows:
        lines.append(
            f"{r['year']:>6} {r['ai']:>9,} "
            f"{r['algo1_doi']:>11,} {r['algo1_pct']:>5}% "
            f"{r['algo2_doi_title']:>13,} {r['algo2_pct']:>5}% "
            f"{r['algo3_doi_title_api']:>12,} {r['algo3_pct']:>5}% "
            f"{r['unmatched']:>10,} {r['unmatched_pct']:>6}%"
        )

    lines.append("\n[3] API match confidence breakdown (Algo3 only)")
    lines.append(f"{'Year':>6} {'strong':>9} {'title+auth':>12} {'weak':>9} {'total':>9}")
    lines.append("-" * 50)
    for r in rows:
        tot = r['api_strong'] + r['api_title_author'] + r['api_weak']
        lines.append(f"{r['year']:>6} {r['api_strong']:>9,} "
                     f"{r['api_title_author']:>12,} {r['api_weak']:>9,} {tot:>9,}")

    lines.append("")
    lines.append("Notes:")
    lines.append("  Algo1 ⊆ Algo2 ⊆ Algo3 (nested, each strategy only runs on residuals)")
    lines.append("  strong       = Jaccard ≥ 0.90")
    lines.append("  title+author = Jaccard ≥ 0.60 AND ≥1 author surname overlap")
    lines.append("  weak         = Jaccard ≥ 0.50 AND author overlap AND relevance ≥ 50")
    lines.append("  (all API matches also require |dblp_year − oa_year| ≤ 1)")

    report = '\n'.join(lines)
    print(report)
    (OUTPUT_DIR / 'final_report.txt').write_text(report + '\n')
    print(f"\nSaved: {csv_path}")
    print(f"Saved: {OUTPUT_DIR / 'final_report.txt'}")


if __name__ == '__main__':
    main()
