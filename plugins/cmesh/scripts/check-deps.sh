#!/bin/bash
# Check that Python dependencies for collab-sync are installed.
# Runs as a SessionStart hook — non-blocking, just warns if missing.

# pyrage requires Python 3.9+
if ! python3 -c "import sys; assert sys.version_info >= (3,9)" 2>/dev/null; then
  echo "[cmesh] Python 3.9+ required for encryption (pyrage). Found: $(python3 --version 2>&1)"
fi

MISSING=""

python3 -c "import yaml" 2>/dev/null || MISSING="$MISSING pyyaml"
python3 -c "import pyrage" 2>/dev/null || MISSING="$MISSING pyrage"
python3 -c "import httpx" 2>/dev/null || MISSING="$MISSING httpx"

if [ -n "$MISSING" ]; then
  echo "[cmesh] Missing Python packages:$MISSING"
  echo "[cmesh] Install with: pip3 install$MISSING"
  echo "[cmesh] Or run: /cmesh setup (handles everything)"
fi
