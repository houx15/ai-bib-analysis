# DBLP Bibliometric Analysis: AI Publications

Measures what fraction of DBLP AI papers can be recovered from OpenAlex, per year (2015–2025), using three cumulative match strategies.

## Goals

**Task 1 — DBLP composition** (no OpenAlex needed):
- Per year: what % of DBLP papers are AI?
- Of AI papers, what % are conference papers?
- Of AI papers, what % lack a DOI?

**Task 2 — Cumulative strong-only coverage of DBLP AI papers in OpenAlex**:
1. DOI exact match (bulk + live API DOI lookup)
2. + normalized-title exact match (bulk)
3. + OpenAlex Search API (Jaccard ≥ 0.90, "strong" tier only)

Buckets are nested: `doi_only` ⊆ `doi_title` ⊆ `doi_title_search`. The
weaker search tiers (`title_author`, `weak`) are kept in the raw stage
CSVs for inspection but **excluded** from the final report — only
strong-confidence matches count as "really matched".

**Task 3 — US vs. China AI publication trends** (line plots, PDF):

Country attribution mirrors `reference/openalex_method.md`: corresponding
author's `countries[0]` → first author's `countries[0]`; restricted to
{CN, HK, TW, US}. Raw codes are preserved end-to-end; the {CN,HK,TW} →
"China" grouping happens only at plot time (toggleable via `--cn-only`).
Two AI-identification methods are reported: (a) title keyword only,
(b) title keyword OR known AI venue.

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
| 9 | `09_final_report.py` | Per-year strong-only coverage (doi / +title / +search) | `final_report.txt`, `final_report.csv` |
| 10a | `10a_country_bulk.py` | Bulk OpenAlex .gz scan → country per matched DBLP key (no network) | `dblp_ai_country.csv` |
| 10b | `10b_country_api.py` | API top-up for 08a doi_api + 08b strong matches not in bulk | `dblp_ai_country.csv` (upsert) |
| 11 | `11_country_plots.py` | US vs. China yearly trend (two PDFs, line plot) | `fig_country_title.pdf`, `fig_country_title_venue.pdf`, `country_counts.csv` |

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

python 09_final_report.py                # final table (strong-only)

# Step 10 is split like step 08: 10a needs no network (HPC compute node);
# 10b needs outbound network (login node / submit host).
python 10a_country_bulk.py               # bulk gz scan, ~12h, no network
python 10b_country_api.py                # API top-up for 08a/08b strong, free tier
python 11_country_plots.py               # US vs. China line plots (PDF)
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

### Step 10 — country attribution, two stages

Mirrors the 08a/08b split because country lookup also has two halves
with different requirements (one I/O-heavy, no network; one network,
small).

**Stage 10a — bulk** (`10a_country_bulk.py`): re-walks the OpenAlex
`.gz` files using the same DOI/normalized-title indices as step 06, but
this time records `authorships` and infers country. **No network**, so
this runs cleanly on Princeton compute nodes. Heavy (~12 h). Resumable —
flushes `dblp_ai_country.csv` every ~30 minutes during the scan.

**Stage 10b — API top-up** (`10b_country_api.py`): for 08a `doi_api` and
08b `strong` matches that the bulk snapshot didn't contain (especially
2025 papers), fetches `/works/<openalex_id>` from the live API. This
endpoint is in the **free filter pool** (~10k/day, no search quota
charge). Run it on a host with outbound network — the same one you used
for 08a/08b.

Country logic mirrors `reference/openalex_method.md`: corresponding
author's `countries[0]` → first author's `countries[0]`; restricted to
{CN, HK, TW, US}. **Codes are stored raw** in `dblp_ai_country.csv`
(no HK/TW collapse at attribution time) so re-aggregation later is a
plotting question, not a re-run. Step 11 groups {CN,HK,TW} as "China"
by default; pass `--cn-only` to exclude HK and TW.

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
├── final_report.txt                # strong-only per-year coverage (text)
├── final_report.csv                # same, machine-readable
├── dblp_ai_country.csv             # per-DBLP-key country (step 10)
├── country_counts.csv              # raw US/CN counts behind the plots
├── fig_country_title.pdf           # US vs CN, AI = title keyword
└── fig_country_title_venue.pdf     # US vs CN, AI = title keyword OR AI venue
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
