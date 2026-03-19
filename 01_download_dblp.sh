#!/usr/bin/env bash
# Download DBLP XML dump + DTD.
# Run from the repo root.  Creates data/raw/ if needed.
set -euo pipefail

RAW_DIR="data/raw"
mkdir -p "$RAW_DIR"

DBLP_BASE="https://dblp.org/xml"

echo "=== Downloading dblp.xml.gz ==="
# ~4 GB compressed, ~30 GB uncompressed
wget -c -O "$RAW_DIR/dblp.xml.gz" "$DBLP_BASE/dblp.xml.gz"

echo "=== Downloading dblp.dtd ==="
wget -c -O "$RAW_DIR/dblp.dtd" "$DBLP_BASE/dblp.dtd"

echo "=== Verifying MD5 ==="
wget -q -O "$RAW_DIR/dblp.xml.gz.md5" "$DBLP_BASE/dblp.xml.gz.md5"
cd "$RAW_DIR"
if md5sum -c dblp.xml.gz.md5; then
    echo "MD5 OK"
else
    echo "WARNING: MD5 mismatch – file may be incomplete. Re-run with wget -c to resume."
fi

echo "=== Done. Files in $RAW_DIR/ ==="
ls -lh "$RAW_DIR"
