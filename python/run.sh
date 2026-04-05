#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install/update deps
"$VENV_DIR/bin/pip" install -q -e "$SCRIPT_DIR"

# Auto-detect GitHub token from gh CLI if not already set
if [ -z "${GITHUB_TOKEN:-}" ] && command -v gh &>/dev/null; then
    GITHUB_TOKEN=$(gh auth token 2>/dev/null) || true
    export GITHUB_TOKEN
fi

# Run the tool, passing all arguments through
"$VENV_DIR/bin/code-provenance" "$@"
