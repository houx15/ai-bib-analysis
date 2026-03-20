"""
Machine-specific paths. Copy this file to config.py and edit.

    cp config.example.py config.py
"""

from pathlib import Path

# Where DBLP raw/parsed/output data lives
DATA_DIR = Path('/path/to/dblp-analysis/data')

# OpenAlex bulk data (works/ directory containing .gz files)
OPENALEX_DIR = Path('/path/to/openalex/works')
