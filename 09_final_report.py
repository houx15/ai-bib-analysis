"""
Step 9: Final per-year coverage report — strong-only matches.

"Really matched" is restricted to high-confidence matches:
  - bulk DOI exact match               (step 06)
  - bulk normalized-title exact match  (step 06)
  - live API DOI lookup → tier doi_api (step 08a)
  - live API search top-1 → tier strong (step 08b, Jaccard ≥ 0.90)

Search-tier matches title_author and weak are EXCLUDED — they are kept in
the raw CSVs for inspection but do not count as matched here.

Three cumulative buckets:

  doi_only           = bulk DOI ∪ 08a doi_api
  doi_title          = + bulk normalized title
  doi_title_search   = + 08b strong

Inputs:
  data/parsed/dblp_papers.csv
  data/parsed/dblp_ai_papers.csv
  data/output/coverage_ai_papers.csv
  data/output/dblp_ai_doi_matches.csv          (from step 08a)
  data/output/dblp_ai_search_matches.csv       (from step 08b)

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
    bulk_doi: dict[int, int] = defaultdict(int)         # DOI only (bulk)
    bulk_doi_title: dict[int, int] = defaultdict(int)   # DOI ∪ Title (bulk)
    cov_path = OUTPUT_DIR / 'coverage_ai_papers.csv'
    if cov_path.exists():
        with open(cov_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                y = int(row['year'])
                bulk_doi[y] = int(row['matched_by_doi'])
                bulk_doi_title[y] = int(row['matched_by_doi_or_title'])
    else:
        print(f"WARNING: {cov_path} not found")

    # ── API matches from steps 08a + 08b (tier breakdown, de-duped) ───────
    # 08a contributes only doi_api; 08b contributes strong / title_author / weak.
    # 08b only runs on rows not matched by 08a, so they are disjoint by
    # construction — but we still de-dupe on dblp_key defensively.
    api_by_tier: dict[str, dict[int, int]] = {
        'doi_api': defaultdict(int),
        'strong': defaultdict(int),
        'title_author': defaultdict(int),
        'weak': defaultdict(int),
    }
    seen_keys: set[str] = set()

    def ingest_matches(path, label: str):
        if not path.exists():
            print(f"NOTE: {path} not found — {label} not yet run")
            return
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('matched', '0') != '1':
                    continue
                key = row.get('dblp_key', '')
                if key in seen_keys:
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
                seen_keys.add(key)

    # 08a (DOI lookup) wins on conflict — DOI is more authoritative than search.
    ingest_matches(OUTPUT_DIR / 'dblp_ai_doi_matches.csv', 'step 08a')
    ingest_matches(OUTPUT_DIR / 'dblp_ai_search_matches.csv', 'step 08b')

    # ── Assemble rows ─────────────────────────────────────────────────────
    def pct(n, d): return f"{100*n/max(d,1):.1f}"

    rows = []
    for y in years:
        t = dblp_total[y]
        ai = ai_total[y]
        cf = ai_conf[y]
        nd = ai_nodoi[y]

        doi_api = api_by_tier['doi_api'][y]
        strong = api_by_tier['strong'][y]
        title_author = api_by_tier['title_author'][y]
        weak = api_by_tier['weak'][y]

        # Strong-only cumulative buckets.
        doi_only = bulk_doi[y] + doi_api
        doi_title = bulk_doi_title[y] + doi_api
        doi_title_search = doi_title + strong

        unm = ai - doi_title_search

        rows.append({
            'year': y,
            'dblp_total': t,
            'ai': ai,
            'ai_pct': pct(ai, t),
            'conf': cf,
            'conf_of_ai_pct': pct(cf, ai),
            'ai_no_doi': nd,
            'ai_no_doi_pct': pct(nd, ai),
            # Strong-only cumulative coverage.
            'doi_only': doi_only,
            'doi_only_pct': pct(doi_only, ai),
            'doi_title': doi_title,
            'doi_title_pct': pct(doi_title, ai),
            'doi_title_search': doi_title_search,
            'doi_title_search_pct': pct(doi_title_search, ai),
            # Provenance breakdown.
            'bulk_doi': bulk_doi[y],
            'bulk_doi_title': bulk_doi_title[y],
            'api_doi_api': doi_api,
            'api_strong': strong,
            'api_title_author_excluded': title_author,
            'api_weak_excluded': weak,
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
    lines.append("FINAL REPORT — DBLP AI papers, per year (strong-only matches)")
    lines.append("=" * 110)

    lines.append("\n[1] DBLP composition (no OpenAlex)")
    lines.append(f"{'Year':>6} {'DBLP':>10} {'AI':>9} {'AI%':>6} "
                 f"{'Conf':>9} {'Conf/AI%':>9} {'AI noDOI':>10} {'noDOI%':>7}")
    lines.append("-" * 75)
    for r in rows:
        lines.append(f"{r['year']:>6} {r['dblp_total']:>10,} {r['ai']:>9,} "
                     f"{r['ai_pct']:>5}% {r['conf']:>9,} {r['conf_of_ai_pct']:>8}% "
                     f"{r['ai_no_doi']:>10,} {r['ai_no_doi_pct']:>6}%")

    lines.append("\n[2] Cumulative strong-only coverage (DBLP AI → OpenAlex)")
    lines.append(f"{'Year':>6} {'DBLP-AI':>9} "
                 f"{'DOI':>9} {'DOI%':>7} "
                 f"{'+Title':>9} {'D+T%':>7} "
                 f"{'+Search':>9} {'D+T+S%':>8} "
                 f"{'Unmatched':>10} {'Unm%':>7}")
    lines.append("-" * 100)
    for r in rows:
        lines.append(
            f"{r['year']:>6} {r['ai']:>9,} "
            f"{r['doi_only']:>9,} {r['doi_only_pct']:>6}% "
            f"{r['doi_title']:>9,} {r['doi_title_pct']:>6}% "
            f"{r['doi_title_search']:>9,} {r['doi_title_search_pct']:>7}% "
            f"{r['unmatched']:>10,} {r['unmatched_pct']:>6}%"
        )

    lines.append("\n[3] Provenance (which source contributed each strong match)")
    lines.append(f"{'Year':>6} {'bulk DOI':>10} {'bulk Title':>11} "
                 f"{'API doi_api':>12} {'API strong':>11}  "
                 f"({'TA-excl':>8} {'weak-excl':>10})")
    lines.append("-" * 80)
    for r in rows:
        bulk_title_only = r['bulk_doi_title'] - r['bulk_doi']
        lines.append(f"{r['year']:>6} {r['bulk_doi']:>10,} {bulk_title_only:>11,} "
                     f"{r['api_doi_api']:>12,} {r['api_strong']:>11,}  "
                     f"({r['api_title_author_excluded']:>8,} "
                     f"{r['api_weak_excluded']:>10,})")

    lines.append("")
    lines.append("Notes:")
    lines.append("  Strong-only = bulk DOI ∪ bulk Title ∪ API doi_api ∪ API strong (Jaccard ≥ 0.90).")
    lines.append("  API title_author and weak tiers are kept in the raw CSVs but EXCLUDED here.")
    lines.append("  doi_only ⊆ doi_title ⊆ doi_title_search (cumulative).")

    report = '\n'.join(lines)
    print(report)
    (OUTPUT_DIR / 'final_report.txt').write_text(report + '\n')
    print(f"\nSaved: {csv_path}")
    print(f"Saved: {OUTPUT_DIR / 'final_report.txt'}")


if __name__ == '__main__':
    main()
