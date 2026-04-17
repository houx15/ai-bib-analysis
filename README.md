# DBLP Bibliometric Analysis: AI Publications

Measures what fraction of DBLP AI papers can be recovered from OpenAlex, per year (2015–2025), using three cumulative match strategies.

## Goals

**Task 1 — DBLP composition** (no OpenAlex needed):
- Per year: what % of DBLP papers are AI?
- Of AI papers, what % are conference papers?
- Of AI papers, what % lack a DOI?

**Task 2 — Cumulative coverage of DBLP AI papers in OpenAlex**:
1. DOI exact match
2. + normalized-title exact match on the DOI residual
3. + OpenAlex Search API (fuzzy top-1) on the DOI|Title residual

Algo1 ⊆ Algo2 ⊆ Algo3 — each strategy only runs on what the previous one missed.

## Pipeline

| Step | Script | Description | Output |
|------|--------|-------------|--------|
| 1 | `01_download_dblp.sh` | Download DBLP XML dump (~4 GB) | `data/raw/dblp.xml.gz` |
| 2 | `02_parse_dblp.py` | Parse XML → flat CSV (articles + conference papers) | `data/parsed/dblp_papers.csv` |
| 3 | `03_filter_ai_papers.py` | Filter AI papers by title keywords OR venue | `data/parsed/dblp_ai_papers.csv` |
| 7 | `07_quick_estimate.py` | Task 1 percentages (fast, no OpenAlex) | `data/output/quick_estimate.txt` |
| 6 | `06_compare_dblp_openalex.py` | Algo1 + Algo2 via OpenAlex bulk scan (~12 h) | `coverage_ai_papers.csv`, `dblp_ai_unmatched.csv` |
| 8 | `08_openalex_search_api.py` | Algo3 via Search API on residual (resumable) | `dblp_ai_api_matches.csv` |
| 9 | `09_final_report.py` | Per-year percentages across all three algos | `final_report.txt`, `final_report.csv` |

## Quick Start

```bash
pip install lxml matplotlib numpy

cp config.example.py config.py
# Edit config.py: set DATA_DIR, OPENALEX_DIR, OPENALEX_MAILTO

bash 01_download_dblp.sh
python 02_parse_dblp.py
python 03_filter_ai_papers.py

python 07_quick_estimate.py              # Task 1 (fast)
python 06_compare_dblp_openalex.py       # Algo1 + Algo2 (~12h)
python 08_openalex_search_api.py         # Algo3 (resumable)
python 09_final_report.py                # final table
```

On Princeton HPC, use the SLURM wrappers under `slurm/` instead.

## Configuration

### Machine-specific paths (`config.py`)

Copy `config.example.py` to `config.py` (gitignored) and set:

- **`DATA_DIR`** — where DBLP raw/parsed/output data lives
- **`OPENALEX_DIR`** — path to the OpenAlex `works/` directory with `.gz` files
- **`OPENALEX_MAILTO`** — your email, for OpenAlex's polite pool

### OpenAlex `mailto`

OpenAlex asks API clients to identify themselves with an email so they can contact you before rate-limiting. Clients that do land in the ["polite pool"](https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication) with higher throughput. Step 08 uses this — without it, long runs are much slower.

Two ways to set it (env var wins if both are present):

1. **In `config.py`** — edit `OPENALEX_MAILTO = 'you@example.com'`. Best for the usual case: set it once per machine.
2. **Env var `OPENALEX_MAILTO`** — overrides `config.py` at runtime. Useful when you share a `config.py` across users, or want to set it per-job:
   ```bash
   export OPENALEX_MAILTO=you@princeton.edu
   python 08_openalex_search_api.py
   ```
   In a SLURM script, add `export OPENALEX_MAILTO=...` before the `python` line.

If neither is set, the script warns and falls back to the slow (anonymous) pool.

### Analysis parameters (`dblp_config.py`)

- **Year range**: `YEAR_MIN` / `YEAR_MAX` (default 2015–2025)
- **AI keywords**: `AI_KEYWORDS` (substring) and `AI_KEYWORDS_WHOLE_WORD` (word-boundary match for short acronyms like "AI", "LLM", "NLP")
- **AI venues**: `AI_VENUES` — conference/journal names matched against DBLP's `<booktitle>` / `<journal>` fields

### Step 08 fuzzy-match thresholds

Top-1 Search API hit is accepted if year is within ±1 and any tier passes:

| Tier | Title Jaccard | Author overlap | Relevance |
|------|---------------|----------------|-----------|
| strong | ≥ 0.90 | — | — |
| title_author | ≥ 0.60 | ≥ 1 surname | — |
| weak | ≥ 0.50 | ≥ 1 surname | ≥ 50 |

Every probe (matched or not) is logged to `dblp_ai_api_matches.csv` with all signals, so thresholds can be re-tuned after the fact without re-querying.

## AI Paper Identification

A DBLP paper is classified AI if **either**:
1. Title matches a keyword from `AI_KEYWORDS` (or a whole-word acronym in `AI_KEYWORDS_WHOLE_WORD`).
2. Venue matches an entry in `AI_VENUES`.

The OR logic is intentional: venue match catches AI papers with generic titles, keyword match catches AI papers in non-AI venues.

## Output Files

```
data/output/
├── quick_estimate.txt              # Task 1 percentages
├── coverage_ai_papers.csv          # Algo1 + Algo2 per-year counts
├── coverage_live.txt               # live progress while step 06 runs
├── dblp_ai_unmatched.csv           # DBLP AI keys missed by Algo1+2 → input to step 08
├── dblp_ai_api_matches.csv         # every Search API probe, with signals
├── final_report.txt                # human-readable per-year table
└── final_report.csv                # same data, machine-readable
```

## Dependencies

- Python 3.10+
- `lxml`, `matplotlib`, `numpy`
- `wget` (for `01_download_dblp.sh`)

## Key References

- `paper.md` — original study methodology description
- DBLP data: https://dblp.org/xml/
- OpenAlex data: https://docs.openalex.org/download-all-data
- OpenAlex polite pool: https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
