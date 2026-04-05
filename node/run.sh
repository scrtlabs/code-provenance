#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Install deps if needed
if [ ! -d "$SCRIPT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm --prefix "$SCRIPT_DIR" install
fi

# Build if needed
if [ ! -d "$SCRIPT_DIR/dist" ]; then
    echo "Building..."
    npm --prefix "$SCRIPT_DIR" run build
fi

# Auto-detect GitHub token from gh CLI if not already set
if [ -z "${GITHUB_TOKEN:-}" ] && command -v gh &>/dev/null; then
    GITHUB_TOKEN=$(gh auth token 2>/dev/null) || true
    export GITHUB_TOKEN
fi

# Run the tool, passing all arguments through
node "$SCRIPT_DIR/dist/cli.js" "$@"
