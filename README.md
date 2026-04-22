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
| 8a | `08a_openalex_doi.py` | Algo3 stage 1 — DOI lookup (cheap, filter pool) | `dblp_ai_doi_matches.csv` |
| 8b | `08b_openalex_search.py` | Algo3 stage 2 — Search API on DOI residual (**paid**) | `dblp_ai_search_matches.csv` |
| 9 | `09_final_report.py` | Per-year percentages across all three algos | `final_report.txt`, `final_report.csv` |

## Quick Start

```bash
pip install lxml matplotlib numpy

cp config.example.py config.py
# Edit config.py: set DATA_DIR, OPENALEX_DIR, OPENALEX_API_KEY

bash 01_download_dblp.sh
python 02_parse_dblp.py
python 03_filter_ai_papers.py

python 07_quick_estimate.py              # Task 1 (fast)
python 06_compare_dblp_openalex.py       # Algo1 + Algo2 (~12h)

# Algo3 is split into two explicit stages — run 08a first, check the
# printed search residual, then run 08b after setting up billing if needed.
python 08a_openalex_doi.py               # cheap DOI lookup stage
python 08b_openalex_search.py            # paid search stage (post-billing)

python 09_final_report.py                # final table
```

On Princeton HPC, use the SLURM wrappers under `slurm/` instead.

## Configuration

### Machine-specific paths (`config.py`)

Copy `config.example.py` to `config.py` (gitignored) and set:

- **`DATA_DIR`** — where DBLP raw/parsed/output data lives
- **`OPENALEX_DIR`** — path to the OpenAlex `works/` directory with `.gz` files
- **`OPENALEX_API_KEY`** — API key for OpenAlex Search API (step 08); see section below
- **`OPENALEX_MAILTO`** — fallback email for the legacy polite pool (only used if no API key)

### OpenAlex Search API authentication (step 08)

OpenAlex now requires authentication for the Search API. Two options — **API key takes priority** if both are set.

**Option A — API key (recommended)**

1. Create a free account at [openalex.org](https://openalex.org) and copy your key from Settings.
2. Set it in `config.py`:
   ```python
   OPENALEX_API_KEY = 'your-key-here'
   ```
   Or via env var (overrides config):
   ```bash
   export OPENALEX_API_KEY=your-key-here
   ```
3. Free tier: **1,000 search calls/day** (~1,000 papers/day). The script is resumable, so large jobs just run over multiple days. Paid plans give higher daily limits.

**Option B — mailto / polite pool (legacy)**

Set `OPENALEX_MAILTO = 'you@example.com'` in `config.py` or the `OPENALEX_MAILTO` env var. No hard daily call limit, but lower throughput. Only used if `OPENALEX_API_KEY` is not set.

If neither is configured, the script warns and runs as anonymous — expect 429 errors immediately.

### Analysis parameters (`dblp_config.py`)

- **Year range**: `YEAR_MIN` / `YEAR_MAX` (default 2015–2025)
- **AI keywords**: `AI_KEYWORDS` (substring) and `AI_KEYWORDS_WHOLE_WORD` (word-boundary match for short acronyms like "AI", "LLM", "NLP")
- **AI venues**: `AI_VENUES` — conference/journal names matched against DBLP's `<booktitle>` / `<journal>` fields

### Step 08 — two explicit stages

Split into two scripts so you can see the paid search workload before committing to it.

**Stage 08a — DOI lookup** (`works/doi:<doi>`): filter pool on OpenAlex, ~10k/day free. Runs only on papers that have a DOI. A hit is accepted unconditionally — DOIs are globally unique — and recorded with `tier='doi_api'`. This is the stage that rescues 2025 DBLP papers that were published after your OpenAlex snapshot date.

```bash
python 08a_openalex_doi.py
```

At the end, 08a prints a summary like:
```
DOI stage totals (cumulative across all runs):
  matched by DOI:        12,345
  DOI lookup failed:     234    (404 + errors)
  papers with no DOI:    5,678
  → need search API (step 08b): 5,912
```

Use that last number to decide whether to set up billing before running 08b.

**Stage 08b — Search API** (`works?search=<title>&filter=publication_year:<y>`): **paid** — each call counts against the OpenAlex search quota ($1/1,000 calls; 1,000/day free). Runs on the residual from 08a (papers with no DOI + papers whose DOI returned 404/errored). Top-1 hit is accepted if year is within ±1 and any tier passes:

```bash
python 08b_openalex_search.py
```

| Tier | Title Jaccard | Author overlap | Relevance | Source |
|------|---------------|----------------|-----------|--------|
| doi_api | (exact via DOI) | — | — | 08a |
| strong | ≥ 0.90 | — | — | 08b |
| title_author | ≥ 0.60 | ≥ 1 surname | — | 08b |
| weak | ≥ 0.50 | ≥ 1 surname | ≥ 50 | 08b |

Every probe (matched or not) is logged so thresholds can be re-tuned without re-querying: 08a writes `dblp_ai_doi_matches.csv`, 08b writes `dblp_ai_search_matches.csv`. Both files are resumable — just re-run the script and it skips already-processed `dblp_key`s.

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
├── dblp_ai_doi_matches.csv         # one row per DOI lookup (step 08a)
├── dblp_ai_search_matches.csv      # one row per search probe (step 08b)
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
- OpenAlex API auth & rate limits: https://developers.openalex.org/api-reference/authentication
