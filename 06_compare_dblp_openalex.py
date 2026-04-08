"""
Step 6: For each DBLP AI paper, find its match in OpenAlex.

This is DBLP-AI-centric: we walk through DBLP AI papers and ask
"does OpenAlex have this paper?" using two match strategies:

  (a) DOI exact match
  (b) Normalized-title exact match (lowercase, [a-z0-9 ] only, collapsed ws)

Per-year output:
  - DBLP AI total
  - matched_by_doi               (DOI path alone)
  - matched_by_doi_or_title      (either path)
  - unmatched                    (neither path — candidates for Search API in step 08)

Tracking is keyed on DBLP key (unique per DBLP paper) so the same DBLP
paper cannot be double-counted even if multiple OpenAlex records hit it
through different paths.

Also tracks all-papers coverage (DBLP vs OpenAlex totals per year) as a
secondary sanity metric.

Outputs:
  data/output/coverage_ai_papers.csv      (per-year AI match breakdown)
  data/output/coverage_all_papers.csv     (per-year totals)
  data/output/coverage_report.txt         (human-readable)
  data/output/coverage_live.txt           (written every 20 files during run)
  data/output/dblp_ai_unmatched.csv       (unmatched DBLP AI papers — input for step 08)

Usage:
    python 06_compare_dblp_openalex.py
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from dblp_config import YEAR_MIN, YEAR_MAX, PARSED_DIR, OUTPUT_DIR, OPENALEX_DIR


# ── Helpers ──────────────────────────────────────────────────────────────────

_NON_ALNUM = re.compile(r'[^a-z0-9\s]')
_WS = re.compile(r'\s+')


def normalize_title(title: str) -> str:
    """Lowercase, keep only [a-z0-9 ], collapse whitespace."""
    if not title:
        return ''
    t = title.lower()
    t = _NON_ALNUM.sub(' ', t)
    t = _WS.sub(' ', t).strip()
    return t


def extract_doi_key(doi_str: str) -> str:
    """Extract bare DOI (e.g. '10.1234/foo') from a URL or raw DOI string."""
    if not doi_str:
        return ''
    s = doi_str.strip().lower()
    for prefix in ('https://doi.org/', 'http://doi.org/',
                   'http://dx.doi.org/', 'https://dx.doi.org/'):
        if s.startswith(prefix):
            return s[len(prefix):]
    if s.startswith('10.'):
        return s
    return ''


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    years = list(range(YEAR_MIN, YEAR_MAX + 1))

    dblp_csv = PARSED_DIR / 'dblp_papers.csv'
    dblp_ai_csv = PARSED_DIR / 'dblp_ai_papers.csv'

    # ── 1. Load DBLP (all papers) — for per-year totals + title/DOI → year map
    print("Loading DBLP (all papers)...", file=sys.stderr)
    dblp_all_by_year: dict[int, int] = defaultdict(int)
    # For all-papers overlap, track which DBLP keys matched.
    all_doi_to_dblp_key: dict[str, str] = {}
    all_title_to_dblp_key: dict[str, str] = {}
    all_dblp_key_to_year: dict[str, int] = {}

    with open(dblp_csv, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            year = int(row['year'])
            if year < YEAR_MIN or year > YEAR_MAX:
                continue
            dblp_all_by_year[year] += 1
            dblp_key = row.get('dblp_key', '')
            if not dblp_key:
                continue
            all_dblp_key_to_year[dblp_key] = year

            doi_key = extract_doi_key(row.get('doi', ''))
            if doi_key and doi_key not in all_doi_to_dblp_key:
                all_doi_to_dblp_key[doi_key] = dblp_key
            nt = normalize_title(row.get('title', ''))
            if nt and nt not in all_title_to_dblp_key:
                all_title_to_dblp_key[nt] = dblp_key

    print(f"  DBLP total: {sum(dblp_all_by_year.values()):,}", file=sys.stderr)
    print(f"  DOI index : {len(all_doi_to_dblp_key):,}", file=sys.stderr)
    print(f"  Title idx : {len(all_title_to_dblp_key):,}", file=sys.stderr)

    # ── 2. Load DBLP AI papers ────────────────────────────────────────────
    print("Loading DBLP AI papers...", file=sys.stderr)
    dblp_ai_by_year: dict[int, int] = defaultdict(int)
    ai_doi_to_dblp_key: dict[str, str] = {}
    ai_title_to_dblp_key: dict[str, str] = {}
    ai_dblp_key_to_year: dict[str, int] = {}
    ai_rows_by_key: dict[str, dict] = {}

    with open(dblp_ai_csv, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            year = int(row['year'])
            if year < YEAR_MIN or year > YEAR_MAX:
                continue
            dblp_ai_by_year[year] += 1
            dblp_key = row.get('dblp_key', '')
            if not dblp_key:
                continue
            ai_dblp_key_to_year[dblp_key] = year
            ai_rows_by_key[dblp_key] = row

            doi_key = extract_doi_key(row.get('doi', ''))
            if doi_key and doi_key not in ai_doi_to_dblp_key:
                ai_doi_to_dblp_key[doi_key] = dblp_key
            nt = normalize_title(row.get('title', ''))
            if nt and nt not in ai_title_to_dblp_key:
                ai_title_to_dblp_key[nt] = dblp_key

    print(f"  DBLP AI total: {sum(dblp_ai_by_year.values()):,}", file=sys.stderr)

    # ── 3. Scan OpenAlex ─────────────────────────────────────────────────
    oa_dir = Path(OPENALEX_DIR)
    gz_files = sorted(oa_dir.glob('**/*.gz'))
    print(f"\nScanning {len(gz_files)} OpenAlex .gz files...", file=sys.stderr)

    oa_all_by_year: dict[int, int] = defaultdict(int)

    # All-papers overlap: sets of DBLP keys matched
    all_matched_by_doi: set[str] = set()
    all_matched_by_title: set[str] = set()

    # AI overlap: sets of DBLP AI keys matched
    ai_matched_by_doi: set[str] = set()
    ai_matched_by_title: set[str] = set()

    live_path = OUTPUT_DIR / 'coverage_live.txt'

    def write_live(fi_done: int, n_files: int, n_oa: int, elapsed: float) -> None:
        # Build per-year counts from matched DBLP keys
        ai_doi_year: dict[int, int] = defaultdict(int)
        ai_either_year: dict[int, int] = defaultdict(int)
        ai_either_keys = ai_matched_by_doi | ai_matched_by_title
        for k in ai_matched_by_doi:
            ai_doi_year[ai_dblp_key_to_year[k]] += 1
        for k in ai_either_keys:
            ai_either_year[ai_dblp_key_to_year[k]] += 1

        all_either_year: dict[int, int] = defaultdict(int)
        for k in (all_matched_by_doi | all_matched_by_title):
            all_either_year[all_dblp_key_to_year[k]] += 1

        lines = []
        lines.append(f"=== LIVE: {fi_done}/{n_files} files | {n_oa:,} OA papers | {elapsed:.0f}s ===")
        lines.append("(counts grow monotonically as more files are scanned)\n")
        lines.append("--- DBLP AI papers matched to OpenAlex ---")
        lines.append(f"{'Year':>6} {'DBLP-AI':>9} {'DOI-match':>10} {'DOI%':>7} "
                     f"{'DOI|Title':>10} {'Either%':>8} {'Unmatched':>10}")
        lines.append("-" * 70)
        for y in years:
            d = dblp_ai_by_year[y]
            md = ai_doi_year[y]
            me = ai_either_year[y]
            lines.append(f"{y:>6} {d:>9,} {md:>10,} {100*md/max(d,1):>6.1f}% "
                         f"{me:>10,} {100*me/max(d,1):>7.1f}% {d-me:>10,}")
        lines.append("")
        lines.append("--- ALL papers: DBLP matched to OpenAlex ---")
        lines.append(f"{'Year':>6} {'DBLP':>10} {'OA':>12} {'Both':>10} {'DBLP%':>7}")
        lines.append("-" * 55)
        for y in years:
            d = dblp_all_by_year[y]
            o = oa_all_by_year[y]
            b = all_either_year[y]
            lines.append(f"{y:>6} {d:>10,} {o:>12,} {b:>10,} {100*b/max(d,1):>6.1f}%")
        with open(live_path, 'w') as f:
            f.write('\n'.join(lines) + '\n')

    t0 = time.time()
    n_oa_total = 0

    for fi, gz_path in enumerate(gz_files):
        if (fi + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  file {fi+1}/{len(gz_files)} | OA={n_oa_total:,} | "
                  f"AI matched doi={len(ai_matched_by_doi):,} "
                  f"title={len(ai_matched_by_title):,} | {elapsed:.0f}s",
                  file=sys.stderr)
            write_live(fi + 1, len(gz_files), n_oa_total, elapsed)

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

                oa_doi = work.get('doi', '') or ''
                doi_key = extract_doi_key(oa_doi)
                oa_title = work.get('title', '') or ''
                nt = normalize_title(oa_title)

                # --- All-papers matching ---
                if doi_key:
                    k = all_doi_to_dblp_key.get(doi_key)
                    if k is not None:
                        all_matched_by_doi.add(k)
                if nt:
                    k = all_title_to_dblp_key.get(nt)
                    if k is not None:
                        all_matched_by_title.add(k)

                # --- DBLP AI matching ---
                if doi_key:
                    k = ai_doi_to_dblp_key.get(doi_key)
                    if k is not None:
                        ai_matched_by_doi.add(k)
                if nt:
                    k = ai_title_to_dblp_key.get(nt)
                    if k is not None:
                        ai_matched_by_title.add(k)

    elapsed = time.time() - t0
    print(f"\nDone: {n_oa_total:,} OA papers in {elapsed:.0f}s", file=sys.stderr)

    # ── 4. Build per-year tables ─────────────────────────────────────────
    ai_doi_year: dict[int, int] = defaultdict(int)
    for k in ai_matched_by_doi:
        ai_doi_year[ai_dblp_key_to_year[k]] += 1

    ai_either_keys = ai_matched_by_doi | ai_matched_by_title
    ai_either_year: dict[int, int] = defaultdict(int)
    for k in ai_either_keys:
        ai_either_year[ai_dblp_key_to_year[k]] += 1

    all_either_keys = all_matched_by_doi | all_matched_by_title
    all_either_year: dict[int, int] = defaultdict(int)
    for k in all_either_keys:
        all_either_year[all_dblp_key_to_year[k]] += 1

    # AI CSV
    rows_ai = []
    for y in years:
        d = dblp_ai_by_year[y]
        md = ai_doi_year[y]
        me = ai_either_year[y]
        rows_ai.append({
            'year': y,
            'dblp_ai_total': d,
            'matched_by_doi': md,
            'matched_by_doi_pct': f"{100*md/max(d,1):.1f}",
            'matched_by_doi_or_title': me,
            'matched_either_pct': f"{100*me/max(d,1):.1f}",
            'unmatched': d - me,
            'unmatched_pct': f"{100*(d-me)/max(d,1):.1f}",
        })

    csv_ai = OUTPUT_DIR / 'coverage_ai_papers.csv'
    with open(csv_ai, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows_ai[0].keys())
        w.writeheader()
        w.writerows(rows_ai)
    print(f"Saved: {csv_ai}")

    # ALL CSV
    rows_all = []
    for y in years:
        d = dblp_all_by_year[y]
        o = oa_all_by_year[y]
        b = all_either_year[y]
        rows_all.append({
            'year': y,
            'dblp_total': d,
            'openalex_total': o,
            'in_both': b,
            'dblp_only': d - b,
            'dblp_in_oa_pct': f"{100*b/max(d,1):.1f}",
        })
    csv_all = OUTPUT_DIR / 'coverage_all_papers.csv'
    with open(csv_all, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=rows_all[0].keys())
        w.writeheader()
        w.writerows(rows_all)
    print(f"Saved: {csv_all}")

    # ── 5. Text report ───────────────────────────────────────────────────
    lines = []
    lines.append("=" * 78)
    lines.append("DBLP AI papers → OpenAlex match (by DBLP key, no double-counting)")
    lines.append("=" * 78)
    lines.append(f"{'Year':>6} {'DBLP-AI':>9} {'DOI':>9} {'DOI%':>7} "
                 f"{'DOI|Title':>10} {'Either%':>8} {'Unmatched':>10} {'Unm%':>7}")
    lines.append("-" * 78)
    for r in rows_ai:
        lines.append(f"{r['year']:>6} {r['dblp_ai_total']:>9,} "
                     f"{r['matched_by_doi']:>9,} {r['matched_by_doi_pct']:>6}% "
                     f"{r['matched_by_doi_or_title']:>10,} "
                     f"{r['matched_either_pct']:>7}% "
                     f"{r['unmatched']:>10,} {r['unmatched_pct']:>6}%")

    lines.append("")
    lines.append("--- All DBLP papers → OpenAlex (sanity) ---")
    lines.append(f"{'Year':>6} {'DBLP':>10} {'OA':>12} {'Both':>10} {'DBLP%':>7}")
    lines.append("-" * 55)
    for r in rows_all:
        lines.append(f"{r['year']:>6} {r['dblp_total']:>10,} "
                     f"{r['openalex_total']:>12,} {r['in_both']:>10,} "
                     f"{r['dblp_in_oa_pct']:>6}%")

    lines.append("")
    lines.append("Legend:")
    lines.append("  DOI            = DBLP AI papers matched to OA via DOI")
    lines.append("  DOI|Title      = matched via DOI OR normalized-title exact")
    lines.append("  Unmatched      = neither path matched (candidates for step 08 Search API)")

    report = '\n'.join(lines)
    print('\n' + report)
    (OUTPUT_DIR / 'coverage_report.txt').write_text(report + '\n')

    # ── 6. Dump unmatched DBLP AI papers for step 08 (Search API) ────────
    unmatched_keys = set(ai_dblp_key_to_year.keys()) - ai_either_keys
    unmatched_path = OUTPUT_DIR / 'dblp_ai_unmatched.csv'
    if ai_rows_by_key:
        sample_row = next(iter(ai_rows_by_key.values()))
        fieldnames = list(sample_row.keys())
        with open(unmatched_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for k in unmatched_keys:
                w.writerow(ai_rows_by_key[k])
        print(f"Saved: {unmatched_path} ({len(unmatched_keys):,} unmatched)")


if __name__ == '__main__':
    main()
