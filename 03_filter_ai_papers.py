"""
Step 3: Filter AI-related papers from parsed DBLP data.

Two criteria (OR):
  1. Title contains an AI keyword  (title_is_ai)
  2. Venue is a known AI venue       (venue_is_ai)

Also attempts country inference from DBLP affiliation notes.

Input:  data/parsed/dblp_papers.csv   (from step 2)
Output: data/parsed/dblp_ai_papers.csv
        data/parsed/affiliation_coverage_report.txt

Usage:
    python 03_filter_ai_papers.py
"""

import argparse
import csv
import sys
from collections import Counter
from dblp_config import (
    PARSED_DIR, is_ai_title, is_ai_venue, infer_country,
    YEAR_MIN, YEAR_MAX,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default=str(PARSED_DIR / 'dblp_papers.csv'))
    parser.add_argument('--output', default=str(PARSED_DIR / 'dblp_ai_papers.csv'))
    args = parser.parse_args()

    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames_out = [
        'dblp_key', 'title', 'year', 'venue', 'venue_type',
        'authors', 'affiliations', 'doi', 'ee',
        'title_is_ai', 'venue_is_ai', 'country',
    ]

    n_total = 0
    n_ai = 0
    n_title_ai = 0
    n_venue_ai = 0
    n_both = 0
    n_has_affiliation = 0
    n_country_inferred = 0
    country_counts = Counter()
    venue_counts = Counter()

    with open(args.input, 'r', encoding='utf-8') as fin, \
         open(args.output, 'w', newline='', encoding='utf-8') as fout:

        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=fieldnames_out)
        writer.writeheader()

        for row in reader:
            n_total += 1
            title = row['title']
            venue = row['venue']

            t_ai = is_ai_title(title)
            v_ai = is_ai_venue(venue)

            if not t_ai and not v_ai:
                continue

            n_ai += 1
            if t_ai:
                n_title_ai += 1
            if v_ai:
                n_venue_ai += 1
            if t_ai and v_ai:
                n_both += 1

            # Country inference from affiliation
            affiliations = row.get('affiliations', '')
            country = None
            if affiliations:
                n_has_affiliation += 1
                country = infer_country(affiliations)
                if country:
                    n_country_inferred += 1
                    country_counts[country] += 1

            if v_ai:
                venue_counts[venue] += 1

            out_row = {
                'dblp_key': row['dblp_key'],
                'title': title,
                'year': row['year'],
                'venue': venue,
                'venue_type': row['venue_type'],
                'authors': row['authors'],
                'affiliations': affiliations,
                'doi': row.get('doi', ''),
                'ee': row.get('ee', ''),
                'title_is_ai': int(t_ai),
                'venue_is_ai': int(v_ai),
                'country': country or '',
            }
            writer.writerow(out_row)

    # Report
    report_lines = [
        f"=== AI Paper Filtering Report ===",
        f"Total papers scanned ({YEAR_MIN}-{YEAR_MAX}): {n_total:,}",
        f"AI papers found: {n_ai:,}",
        f"  - by title keyword: {n_title_ai:,}",
        f"  - by venue:         {n_venue_ai:,}",
        f"  - both:             {n_both:,}",
        f"",
        f"=== Country Attribution from DBLP Affiliations ===",
        f"Papers with any affiliation note: {n_has_affiliation:,} / {n_ai:,} ({100*n_has_affiliation/max(n_ai,1):.1f}%)",
        f"Country inferred (CN or US):      {n_country_inferred:,} / {n_has_affiliation:,}",
        f"  CN: {country_counts.get('CN', 0):,}",
        f"  US: {country_counts.get('US', 0):,}",
        f"",
        f"*** If affiliation coverage is low (<30%), you should run step 04 ***",
        f"*** to cross-reference with OpenAlex by DOI for country data.     ***",
        f"",
        f"=== Top 30 AI venues by paper count ===",
    ]
    for venue, count in venue_counts.most_common(30):
        report_lines.append(f"  {count:>6,}  {venue}")

    report = '\n'.join(report_lines)
    print(report)

    report_path = PARSED_DIR / 'affiliation_coverage_report.txt'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")


if __name__ == '__main__':
    main()
