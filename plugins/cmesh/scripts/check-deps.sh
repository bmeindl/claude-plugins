#!/bin/bash
# Check that Python dependencies for collab-sync are installed.
# Runs as a SessionStart hook — non-blocking, just warns if missing.

# pyrage requires Python 3.9+
if ! python3 -c "import sys; assert sys.version_info >= (3,9)" 2>/dev/null; then
  echo "[collab] Python 3.9+ required for encryption (pyrage). Found: $(python3 --version 2>&1)"
fi

MISSING=""

python3 -c "import yaml" 2>/dev/null || MISSING="$MISSING pyyaml"
python3 -c "import pyrage" 2>/dev/null || MISSING="$MISSING pyrage"
python3 -c "import httpx" 2>/dev/null || MISSING="$MISSING httpx"

if [ -n "$MISSING" ]; then
  echo "[collab] Missing Python packages:$MISSING"
  echo "[collab] Install with: pip3 install$MISSING"
  echo "[collab] Or run: /collab setup (handles everything)"
fi
