# DBLP Bibliometric Analysis: AI Publications by Country

Replicates the OpenAlex-based analysis of AI publication volumes (China vs United States, 2015–2025) using DBLP as an alternative data source, and compares coverage between the two databases.

## Motivation

The original study uses OpenAlex to track AI-related scientific publications by country. However, OpenAlex may undercount conference papers — the primary venue for AI research. DBLP, as a CS-focused bibliography, should have stronger conference coverage. This pipeline:

1. Processes the DBLP XML dump to identify AI papers
2. Compares DBLP vs OpenAlex coverage to quantify the gap
3. (Optionally) cross-references with OpenAlex for country attribution

## Pipeline

Run scripts in order. Steps 01–03 and 06 are the core workflow. Steps 04–05 are for country-level analysis if needed later.

| Step | Script | Description | Input | Output |
|------|--------|-------------|-------|--------|
| 1 | `01_download_dblp.sh` | Download DBLP XML dump (~4 GB) | — | `data/raw/dblp.xml.gz` |
| 2 | `02_parse_dblp.py` | Parse XML into flat CSV (articles + conference papers, 2015–2025) | `dblp.xml.gz` | `data/parsed/dblp_papers.csv` |
| 3 | `03_filter_ai_papers.py` | Filter AI papers by title keywords OR venue name | `dblp_papers.csv` | `data/parsed/dblp_ai_papers.csv` |
| **6** | **`06_compare_dblp_openalex.py`** | **Compare DBLP vs OpenAlex coverage per year** | `dblp_papers.csv` + OpenAlex bulk data | `data/output/coverage_*.csv`, report, plot |
| 4 | `04_crossref_openalex.py` | Cross-reference DBLP AI papers with OpenAlex for country data | `dblp_ai_papers.csv` + OpenAlex bulk data | `dblp_ai_papers_with_country.csv` |
| 5 | `05_aggregate_counts.py` | Aggregate yearly CN vs US counts + plot | `dblp_ai_papers_with_country.csv` | `data/output/yearly_counts.csv`, plot |

## Quick Start

```bash
# Install dependencies
pip install lxml matplotlib numpy

# 1. Download DBLP
bash 01_download_dblp.sh

# 2. Parse (takes ~20-40 min on the full XML)
python 02_parse_dblp.py

# 3. Filter AI papers
python 03_filter_ai_papers.py
# → Read the printed report: check keyword/venue match counts and affiliation coverage

# 6. Compare against OpenAlex (takes ~30-60 min)
python 06_compare_dblp_openalex.py \
    --openalex-dir /tigerdata/ccc/data/2018-science/data-openalex-20250227/works
# → Check data/output/coverage_report.txt and dblp_only_ai_sample.csv
```

## Configuration

Edit `dblp_config.py` to adjust:

- **Machine paths**: add your server hostname and set `ROOT` (line 14)
- **Year range**: `YEAR_MIN` / `YEAR_MAX` (default 2015–2025)
- **AI keywords**: `AI_KEYWORDS` (substring match) and `AI_KEYWORDS_WHOLE_WORD` (exact word match for short acronyms like "AI", "LLM", "NLP")
- **AI venues**: `AI_VENUES` — conference and journal names matched against DBLP's `<booktitle>` / `<journal>` fields
- **Country patterns**: regex patterns for inferring CN/US from DBLP affiliation text

## AI Paper Identification

A DBLP paper is classified as AI-related if **either**:

1. **Title keyword match** — title contains any keyword from the curated list (same list as the OpenAlex study, plus additional CS-specific terms like "graph neural network", "prompt tuning", etc.)
2. **Venue match** — published in a known AI conference (NeurIPS, ICML, AAAI, ACL, CVPR, ...) or journal (JMLR, TPAMI, ...)

This OR logic is intentional: venue matching captures AI papers with generic titles, while keyword matching captures AI papers in non-AI venues.

## Country Attribution (DBLP Limitation)

DBLP has sparse affiliation/country metadata compared to OpenAlex. The pipeline handles this in two stages:

1. **Step 03** attempts country inference from DBLP `<note type="affiliation">` fields and reports coverage rate
2. **Step 04** (optional) cross-references unmatched papers with OpenAlex by DOI/title to fill in country data

Run step 03 first and check the affiliation coverage report before deciding whether step 04 is needed.

## Output Files

After running the full pipeline:

```
data/output/
├── coverage_all_papers.csv          # DBLP vs OA overlap, all papers, by year
├── coverage_ai_papers.csv           # DBLP vs OA overlap, AI papers, by year
├── coverage_report.txt              # Formatted comparison table
├── fig_coverage_comparison.png      # Two-panel coverage plot
├── dblp_only_ai_sample.csv          # Sample of AI papers in DBLP but not OA
├── yearly_counts.csv                # CN vs US counts by year (after step 05)
├── yearly_counts_by_method.csv      # Breakdown by title/venue match method
├── summary_stats.txt                # Summary statistics
└── fig_cn_vs_us.png                 # CN vs US trend plot
```

## Dependencies

- Python 3.10+
- `lxml` — XML parsing
- `matplotlib` — plotting
- `numpy`
- `wget` — for downloading DBLP dump (shell)

## Key References

- `paper.md` — original study methodology description
- `utils.py` — OpenAlex analysis script with AI keyword list
- DBLP data: https://dblp.org/xml/
- OpenAlex data: https://docs.openalex.org/download-all-data
