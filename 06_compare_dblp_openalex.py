"""
Step 6: Compare DBLP vs OpenAlex coverage, year by year.

Builds DOI and normalized-title indices from DBLP parsed CSV, then scans
OpenAlex bulk data to find matches.  Reports per-year:

  - DBLP total / OpenAlex total (all papers, not just AI)
  - Overlap (in both)
  - DBLP-only / OpenAlex-only
  - Same breakdown restricted to AI papers

Produces:
  data/output/coverage_all_papers.csv
  data/output/coverage_ai_papers.csv
  data/output/coverage_report.txt
  data/output/fig_coverage_comparison.png
  data/output/dblp_only_ai_sample.csv      (sample of DBLP-only AI papers for inspection)

Usage:
    python 06_compare_dblp_openalex.py \
        --dblp-csv data/parsed/dblp_papers.csv \
        --openalex-dir /tigerdata/ccc/data/2018-science/data-openalex-20250227/works \
        [--dblp-ai-csv data/parsed/dblp_ai_papers.csv]

NOTE: This scans the full OpenAlex dump. Expect ~30-60 min depending on I/O.
"""

import argparse
import csv
import gzip
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from dblp_config import YEAR_MIN, YEAR_MAX, PARSED_DIR, OUTPUT_DIR, OPENALEX_DIR, is_ai_title, is_ai_venue


# ── Helpers ──────────────────────────────────────────────────────────────────

def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def extract_doi_key(doi_str: str) -> str:
    """Extract bare DOI (e.g. '10.1234/foo') from a URL or raw DOI string."""
    if not doi_str:
        return ''
    doi_str = doi_str.strip()
    for prefix in ['https://doi.org/', 'http://doi.org/',
                    'http://dx.doi.org/', 'https://dx.doi.org/']:
        if doi_str.lower().startswith(prefix):
            return doi_str[len(prefix):].lower()
    if doi_str.startswith('10.'):
        return doi_str.lower()
    return ''


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Compare DBLP vs OpenAlex coverage')
    parser.add_argument('--dblp-csv', default=str(PARSED_DIR / 'dblp_papers.csv'),
                        help='Parsed DBLP CSV from step 02 (all papers, not just AI)')
    parser.add_argument('--dblp-ai-csv', default=str(PARSED_DIR / 'dblp_ai_papers.csv'),
                        help='Filtered DBLP AI papers from step 03')
    parser.add_argument('--openalex-dir', default=str(OPENALEX_DIR),
                        help='Path to OpenAlex works/ directory with .gz files')
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Load DBLP papers ──────────────────────────────────────────────
    print("Loading DBLP papers...", file=sys.stderr)

    # For ALL papers: build year-indexed DOI and title sets
    # doi_key -> year
    dblp_doi_to_year = {}
    # normalized_title -> year (first occurrence wins if duplicates)
    dblp_title_to_year = {}
    # year -> count of all DBLP papers
    dblp_all_by_year = defaultdict(int)

    with open(args.dblp_csv, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            year = int(row['year'])
            dblp_all_by_year[year] += 1

            doi_key = extract_doi_key(row.get('doi', ''))
            if doi_key:
                dblp_doi_to_year[doi_key] = year

            nt = normalize_title(row.get('title', ''))
            if nt and nt not in dblp_title_to_year:
                dblp_title_to_year[nt] = year

    print(f"  DBLP all papers: {sum(dblp_all_by_year.values()):,}", file=sys.stderr)
    print(f"  DBLP DOI index:  {len(dblp_doi_to_year):,}", file=sys.stderr)
    print(f"  DBLP title index: {len(dblp_title_to_year):,}", file=sys.stderr)

    # For AI papers: separate sets + year lookup
    dblp_ai_dois = set()
    dblp_ai_titles = set()
    dblp_ai_doi_to_year = {}
    dblp_ai_title_to_year = {}
    dblp_ai_by_year = defaultdict(int)
    dblp_ai_rows_by_key = {}  # dblp_key -> row (for sampling DBLP-only later)

    ai_csv_path = Path(args.dblp_ai_csv)
    if ai_csv_path.exists():
        with open(ai_csv_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                year = int(row['year'])
                dblp_ai_by_year[year] += 1
                doi_key = extract_doi_key(row.get('doi', ''))
                if doi_key:
                    dblp_ai_dois.add(doi_key)
                    if doi_key not in dblp_ai_doi_to_year:
                        dblp_ai_doi_to_year[doi_key] = year
                nt = normalize_title(row.get('title', ''))
                if nt:
                    dblp_ai_titles.add(nt)
                    if nt not in dblp_ai_title_to_year:
                        dblp_ai_title_to_year[nt] = year
                dblp_ai_rows_by_key[row.get('dblp_key', '')] = row
        print(f"  DBLP AI papers:  {sum(dblp_ai_by_year.values()):,}", file=sys.stderr)
    else:
        print(f"  WARNING: {ai_csv_path} not found, AI-level comparison will be skipped", file=sys.stderr)

    # ── 2. Scan OpenAlex ─────────────────────────────────────────────────
    print("\nScanning OpenAlex...", file=sys.stderr)
    oa_dir = Path(args.openalex_dir)
    gz_files = sorted(oa_dir.glob('**/*.gz'))
    print(f"  Found {len(gz_files)} .gz files", file=sys.stderr)

    # Per-year counters
    oa_all_by_year = defaultdict(int)          # total OA papers
    oa_ai_by_year = defaultdict(int)           # OA AI papers (title match)

    # Track which DBLP papers have been matched (to avoid double-counting)
    # Use the match key (doi or title) as identifier
    matched_dblp_all = set()    # set of (doi_key or norm_title) for all papers
    matched_dblp_ai = set()     # set of (doi_key or norm_title) for AI papers

    # Track which DBLP AI papers were found in OA (for sampling DBLP-only)
    dblp_ai_matched_dois = set()
    dblp_ai_matched_titles = set()

    years = list(range(YEAR_MIN, YEAR_MAX + 1))
    live_path = OUTPUT_DIR / 'coverage_live.txt'

    def write_live_progress(fi_done, n_files, n_scanned, elapsed):
        """Write a live progress file you can cat anytime during the run."""
        # Reconstruct per-year overlap from matched sets so far
        ov_all = defaultdict(int)
        for kind, key in matched_dblp_all:
            y = dblp_doi_to_year[key] if kind == 'doi' else dblp_title_to_year[key]
            ov_all[y] += 1
        ov_ai = defaultdict(int)
        for kind, key in matched_dblp_ai:
            y = dblp_ai_doi_to_year[key] if kind == 'doi' else dblp_ai_title_to_year[key]
            ov_ai[y] += 1

        lines = []
        lines.append(f"=== LIVE PROGRESS: {fi_done}/{n_files} files | {n_scanned:,} OA papers | {elapsed:.0f}s ===")
        lines.append(f"(numbers will increase as more files are scanned)\n")

        lines.append(f"{'Year':>6} {'DBLP-AI':>9} {'OA-AI':>9} {'Both':>9} {'DBLP-only':>10} {'OA-only':>10} {'DBLP⊂OA':>8}")
        lines.append("-" * 70)
        for y in years:
            d = dblp_ai_by_year[y]
            o = oa_ai_by_year[y]
            b = ov_ai[y]
            lines.append(f"{y:>6} {d:>9,} {o:>9,} {b:>9,} {d-b:>10,} {o-b:>10,} "
                          f"{100*b/max(d,1):>7.1f}%")
        lines.append("")
        lines.append(f"{'Year':>6} {'DBLP':>9} {'OA':>9} {'Both':>9} {'DBLP-only':>10} {'OA-only':>10} {'DBLP⊂OA':>8}")
        lines.append("-" * 70)
        for y in years:
            d = dblp_all_by_year[y]
            o = oa_all_by_year[y]
            b = ov_all[y]
            lines.append(f"{y:>6} {d:>9,} {o:>9,} {b:>9,} {d-b:>10,} {o-b:>10,} "
                          f"{100*b/max(d,1):>7.1f}%")

        with open(live_path, 'w') as f:
            f.write('\n'.join(lines) + '\n')

    t0 = time.time()
    n_oa_total = 0

    for fi, gz_path in enumerate(gz_files):
        if (fi + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  file {fi+1}/{len(gz_files)} | OA scanned: {n_oa_total:,} | "
                  f"overlap(all): {len(matched_dblp_all):,} | "
                  f"overlap(ai): {len(matched_dblp_ai):,} | "
                  f"{elapsed:.0f}s",
                  file=sys.stderr)
            write_live_progress(fi + 1, len(gz_files), n_oa_total, elapsed)

        with gzip.open(gz_path, 'rt', encoding='utf-8') as gf:
            for line in gf:
                try:
                    work = json.loads(line)
                except json.JSONDecodeError:
                    continue

                pub_year = work.get('publication_year')
                if pub_year is None or pub_year < YEAR_MIN or pub_year > YEAR_MAX:
                    continue

                n_oa_total += 1
                oa_all_by_year[pub_year] += 1

                # Check if this OA paper is AI-related (by title, same logic as original study)
                oa_title = work.get('title', '') or ''
                oa_is_ai = is_ai_title(oa_title)
                if oa_is_ai:
                    oa_ai_by_year[pub_year] += 1

                # Match against DBLP (all papers)
                oa_doi = work.get('doi', '') or ''
                doi_key = extract_doi_key(oa_doi)
                match_key = None  # the key used to identify this DBLP paper

                if doi_key and doi_key in dblp_doi_to_year:
                    match_key = ('doi', doi_key)
                else:
                    nt = normalize_title(oa_title)
                    if nt and nt in dblp_title_to_year:
                        match_key = ('title', nt)

                if match_key is not None and match_key not in matched_dblp_all:
                    matched_dblp_all.add(match_key)

                # Match against DBLP AI papers specifically
                if dblp_ai_dois or dblp_ai_titles:
                    ai_match_key = None
                    if doi_key and doi_key in dblp_ai_dois:
                        ai_match_key = ('doi', doi_key)
                        dblp_ai_matched_dois.add(doi_key)
                    else:
                        nt = normalize_title(oa_title) if oa_title else ''
                        if nt and nt in dblp_ai_titles:
                            ai_match_key = ('title', nt)
                            dblp_ai_matched_titles.add(nt)
                    if ai_match_key is not None and ai_match_key not in matched_dblp_ai:
                        matched_dblp_ai.add(ai_match_key)

    elapsed = time.time() - t0
    print(f"\nOpenAlex scan done: {n_oa_total:,} papers in {elapsed:.0f}s", file=sys.stderr)

    # ── 3. Compute per-year stats ────────────────────────────────────────
    years = list(range(YEAR_MIN, YEAR_MAX + 1))

    # Reconstruct per-year overlap counts from matched sets
    overlap_all_by_year = defaultdict(int)
    for kind, key in matched_dblp_all:
        if kind == 'doi':
            y = dblp_doi_to_year[key]
        else:
            y = dblp_title_to_year[key]
        overlap_all_by_year[y] += 1

    overlap_ai_by_year = defaultdict(int)
    for kind, key in matched_dblp_ai:
        if kind == 'doi':
            y = dblp_ai_doi_to_year[key]
        else:
            y = dblp_ai_title_to_year[key]
        overlap_ai_by_year[y] += 1

    # All papers
    rows_all = []
    for y in years:
        dblp = dblp_all_by_year[y]
        oa = oa_all_by_year[y]
        both = overlap_all_by_year[y]
        dblp_only = dblp - both
        oa_only = oa - both
        rows_all.append({
            'year': y,
            'dblp_total': dblp,
            'openalex_total': oa,
            'in_both': both,
            'dblp_only': dblp_only,
            'openalex_only': oa_only,
            'dblp_coverage_of_oa': f"{100*both/max(oa,1):.1f}%",
            'oa_coverage_of_dblp': f"{100*both/max(dblp,1):.1f}%",
        })

    csv_all = OUTPUT_DIR / 'coverage_all_papers.csv'
    with open(csv_all, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows_all[0].keys())
        w.writeheader()
        w.writerows(rows_all)
    print(f"Saved: {csv_all}")

    # AI papers
    rows_ai = []
    for y in years:
        dblp = dblp_ai_by_year[y]
        oa = oa_ai_by_year[y]
        both = overlap_ai_by_year[y]
        dblp_only = dblp - both
        oa_only = oa - both
        rows_ai.append({
            'year': y,
            'dblp_ai_total': dblp,
            'openalex_ai_total': oa,
            'in_both': both,
            'dblp_only': dblp_only,
            'openalex_only': oa_only,
            'dblp_coverage_of_oa': f"{100*both/max(oa,1):.1f}%",
            'oa_coverage_of_dblp': f"{100*both/max(dblp,1):.1f}%",
        })

    csv_ai = OUTPUT_DIR / 'coverage_ai_papers.csv'
    with open(csv_ai, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows_ai[0].keys())
        w.writeheader()
        w.writerows(rows_ai)
    print(f"Saved: {csv_ai}")

    # ── 4. Text report ───────────────────────────────────────────────────
    lines = []
    lines.append("=" * 70)
    lines.append("DBLP vs OpenAlex Coverage Comparison")
    lines.append("=" * 70)

    lines.append("\n--- ALL PAPERS (2015-2025) ---")
    lines.append(f"{'Year':>6} {'DBLP':>10} {'OpenAlex':>10} {'Both':>10} {'DBLP-only':>10} {'OA-only':>10} {'OA⊂DBLP':>8} {'DBLP⊂OA':>8}")
    lines.append("-" * 78)
    for r in rows_all:
        lines.append(f"{r['year']:>6} {r['dblp_total']:>10,} {r['openalex_total']:>10,} "
                      f"{r['in_both']:>10,} {r['dblp_only']:>10,} {r['openalex_only']:>10,} "
                      f"{r['dblp_coverage_of_oa']:>8} {r['oa_coverage_of_dblp']:>8}")

    lines.append("\n--- AI PAPERS (2015-2025) ---")
    lines.append(f"{'Year':>6} {'DBLP-AI':>10} {'OA-AI':>10} {'Both':>10} {'DBLP-only':>10} {'OA-only':>10} {'OA⊂DBLP':>8} {'DBLP⊂OA':>8}")
    lines.append("-" * 78)
    for r in rows_ai:
        lines.append(f"{r['year']:>6} {r['dblp_ai_total']:>10,} {r['openalex_ai_total']:>10,} "
                      f"{r['in_both']:>10,} {r['dblp_only']:>10,} {r['openalex_only']:>10,} "
                      f"{r['dblp_coverage_of_oa']:>8} {r['oa_coverage_of_dblp']:>8}")

    lines.append("\nColumn legend:")
    lines.append("  OA⊂DBLP = % of OpenAlex papers also found in DBLP")
    lines.append("  DBLP⊂OA = % of DBLP papers also found in OpenAlex")

    report = '\n'.join(lines)
    print('\n' + report)
    report_path = OUTPUT_DIR / 'coverage_report.txt'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nSaved: {report_path}")

    # ── 5. Sample of DBLP-only AI papers (for manual inspection) ─────────
    if dblp_ai_rows_by_key:
        matched_all = dblp_ai_matched_dois | dblp_ai_matched_titles
        sample_rows = []
        for key, row in dblp_ai_rows_by_key.items():
            doi_key = extract_doi_key(row.get('doi', ''))
            nt = normalize_title(row.get('title', ''))
            if doi_key not in dblp_ai_matched_dois and nt not in dblp_ai_matched_titles:
                sample_rows.append(row)
            if len(sample_rows) >= 500:
                break

        if sample_rows:
            sample_path = OUTPUT_DIR / 'dblp_only_ai_sample.csv'
            with open(sample_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=sample_rows[0].keys())
                w.writeheader()
                w.writerows(sample_rows)
            print(f"Saved: {sample_path} ({len(sample_rows)} sample DBLP-only AI papers)")

    # ── 6. Plot ──────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel A: All papers
    ax = axes[0]
    dblp_vals = [dblp_all_by_year[y] for y in years]
    oa_vals = [oa_all_by_year[y] for y in years]
    both_vals = [overlap_all_by_year[y] for y in years]
    ax.plot(years, dblp_vals, 'o-', color='#e6550d', label='DBLP total')
    ax.plot(years, oa_vals, 's-', color='#3182bd', label='OpenAlex total')
    ax.plot(years, both_vals, '^--', color='#31a354', label='In both')
    ax.set_title('A. All Papers')
    ax.set_xlabel('Year')
    ax.set_ylabel('Number of papers')
    ax.legend()
    ax.set_xticks(years)
    ax.set_xticklabels(years, rotation=45)
    ax.grid(True, alpha=0.3)

    # Panel B: AI papers
    ax = axes[1]
    dblp_ai_vals = [dblp_ai_by_year[y] for y in years]
    oa_ai_vals = [oa_ai_by_year[y] for y in years]
    both_ai_vals = [overlap_ai_by_year[y] for y in years]
    ax.plot(years, dblp_ai_vals, 'o-', color='#e6550d', label='DBLP AI')
    ax.plot(years, oa_ai_vals, 's-', color='#3182bd', label='OpenAlex AI')
    ax.plot(years, both_ai_vals, '^--', color='#31a354', label='In both')
    ax.set_title('B. AI Papers')
    ax.set_xlabel('Year')
    ax.set_ylabel('Number of AI papers')
    ax.legend()
    ax.set_xticks(years)
    ax.set_xticklabels(years, rotation=45)
    ax.grid(True, alpha=0.3)

    fig.suptitle('DBLP vs OpenAlex Coverage (2015–2025)', fontsize=13, y=1.02)
    fig.tight_layout()
    fig_path = OUTPUT_DIR / 'fig_coverage_comparison.png'
    fig.savefig(fig_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {fig_path}")
    plt.close(fig)


if __name__ == '__main__':
    main()
