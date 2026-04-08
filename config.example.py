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

# Email for OpenAlex "polite pool" (higher rate limits on the REST API).
# See https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
OPENALEX_MAILTO = 'you@example.com'
