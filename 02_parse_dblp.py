"""
Step 2: Parse dblp.xml.gz into a flat CSV of papers.

Extracts: dblp_key, title, year, venue, venue_type, authors (semicolon-separated),
           affiliations (semicolon-separated, if available).

Uses iterative XML parsing (lxml.etree.iterparse) to handle the ~30 GB file
without loading it all into memory.

Usage:
    python 02_parse_dblp.py [--input data/raw/dblp.xml.gz] [--output data/parsed/dblp_papers.csv]
"""

import argparse
import csv
import gzip
import sys
import time
from lxml import etree
from dblp_config import YEAR_MIN, YEAR_MAX, RAW_DIR, PARSED_DIR

# DBLP entry types we care about
ENTRY_TAGS = {'article', 'inproceedings', 'proceedings', 'incollection', 'phdthesis', 'mastersthesis'}
# For our analysis we mainly want article + inproceedings
WANTED_TAGS = {'article', 'inproceedings'}


def parse_dblp(input_path, output_path):
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = ['dblp_key', 'title', 'year', 'venue', 'venue_type', 'authors', 'affiliations', 'doi', 'ee']

    t0 = time.time()
    n_total = 0
    n_kept = 0

    with open(output_path, 'w', newline='', encoding='utf-8') as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        # Open gzipped XML; use recover=True to handle minor XML issues
        # We need the DTD for entity resolution – copy it next to the XML
        context = etree.iterparse(
            gzip.open(input_path, 'rb'),
            events=('end',),
            tag=tuple(ENTRY_TAGS),
            dtd_validation=False,
            load_dtd=True,
            resolve_entities=True,
            recover=True,
        )

        for event, elem in context:
            n_total += 1
            if n_total % 1_000_000 == 0:
                elapsed = time.time() - t0
                print(f"  processed {n_total:,} entries, kept {n_kept:,} ({elapsed:.0f}s)", file=sys.stderr)

            tag = elem.tag
            if tag not in WANTED_TAGS:
                elem.clear()
                continue

            # Extract year
            year_elem = elem.find('year')
            if year_elem is None or year_elem.text is None:
                elem.clear()
                continue
            try:
                year = int(year_elem.text)
            except ValueError:
                elem.clear()
                continue
            if year < YEAR_MIN or year > YEAR_MAX:
                elem.clear()
                continue

            # Extract title (concatenate all text within <title> including sub-elements)
            title_elem = elem.find('title')
            title = ''.join(title_elem.itertext()).strip() if title_elem is not None else ''
            if not title:
                elem.clear()
                continue

            # dblp key
            dblp_key = elem.get('key', '')

            # Venue
            if tag == 'inproceedings':
                venue_elem = elem.find('booktitle')
                venue_type = 'conference'
            else:  # article
                venue_elem = elem.find('journal')
                venue_type = 'journal'
            venue = venue_elem.text.strip() if venue_elem is not None and venue_elem.text else ''

            # Authors
            authors = []
            for author_elem in elem.findall('author'):
                name = ''.join(author_elem.itertext()).strip()
                if name:
                    authors.append(name)

            # Affiliations (DBLP sometimes includes <note type="affiliation">)
            affiliations = []
            for note in elem.findall('note'):
                if note.get('type') == 'affiliation':
                    aff = ''.join(note.itertext()).strip()
                    if aff:
                        affiliations.append(aff)

            # DOI
            doi_elem = elem.find('ee')
            doi = ''
            ee = ''
            for ee_elem in elem.findall('ee'):
                url = ee_elem.text.strip() if ee_elem.text else ''
                if 'doi.org' in url:
                    doi = url
                if not ee:
                    ee = url

            row = {
                'dblp_key': dblp_key,
                'title': title,
                'year': year,
                'venue': venue,
                'venue_type': venue_type,
                'authors': '; '.join(authors),
                'affiliations': '; '.join(affiliations),
                'doi': doi,
                'ee': ee,
            }
            writer.writerow(row)
            n_kept += 1

            # Free memory
            elem.clear()
            # Also clear preceding siblings to prevent memory buildup
            while elem.getprevious() is not None:
                del elem.getparent()[0]

    elapsed = time.time() - t0
    print(f"Done. Total entries scanned: {n_total:,}. Kept (article+inproceedings, {YEAR_MIN}-{YEAR_MAX}): {n_kept:,}. Time: {elapsed:.0f}s",
          file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='Parse DBLP XML into CSV')
    parser.add_argument('--input', type=str, default=str(RAW_DIR / 'dblp.xml.gz'))
    parser.add_argument('--output', type=str, default=str(PARSED_DIR / 'dblp_papers.csv'))
    args = parser.parse_args()
    parse_dblp(args.input, args.output)


if __name__ == '__main__':
    main()
