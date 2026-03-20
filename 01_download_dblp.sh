#!/usr/bin/env bash
# Download DBLP XML dump + DTD.
# Pass RAW_DIR as first arg, or defaults to data/raw.
# Skips files that already exist.
set -euo pipefail

RAW_DIR="${1:-data/raw}"
mkdir -p "$RAW_DIR"

DBLP_BASE="https://dblp.org/xml"

if [ -f "$RAW_DIR/dblp.xml.gz" ]; then
    echo "=== dblp.xml.gz already exists, skipping ==="
else
    echo "=== Downloading dblp.xml.gz ==="
    wget -c -O "$RAW_DIR/dblp.xml.gz" "$DBLP_BASE/dblp.xml.gz"
fi

if [ -f "$RAW_DIR/dblp.dtd" ]; then
    echo "=== dblp.dtd already exists, skipping ==="
else
    echo "=== Downloading dblp.dtd ==="
    wget -c -O "$RAW_DIR/dblp.dtd" "$DBLP_BASE/dblp.dtd"
fi

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
