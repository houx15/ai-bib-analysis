"""
Machine-specific paths. Copy this file to config.py and edit.

    cp config.example.py config.py

Example for adroit/della (Princeton HPC):
    DATA_DIR     = Path('/scratch/network/yh6580/ai-bib/dblp')
    OPENALEX_DIR = Path('/scratch/network/science-of-science/data/openalex-20250227/works')
"""

from pathlib import Path

# Where DBLP raw/parsed/output data lives (raw/, parsed/, output/ created under this)
DATA_DIR = Path('/path/to/dblp-analysis/data')

# OpenAlex bulk data (works/ directory containing .gz files)
OPENALEX_DIR = Path('/path/to/openalex/works')

# OpenAlex Search API authentication (used by step 08).
#
# Option A — API key (recommended): create a free account at openalex.org,
# copy your key from Settings, and set it here or via the OPENALEX_API_KEY
# env var. Free tier: 1,000 search calls / day (~1,000 papers/day).
# When OPENALEX_API_KEY is set, OPENALEX_MAILTO is ignored.
OPENALEX_API_KEY = ''

# Option B — mailto / polite pool (legacy): no daily call limit but lower
# throughput. May also be set via the OPENALEX_MAILTO env var.
OPENALEX_MAILTO = 'you@example.com'
