#!/usr/bin/env bash
# Regenerate the Truco Arena snapshot (run manually when wiki evolves)
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rsync -av --delete --exclude="*.lock" \
    /Users/xilax/Documents/GitHub/truco-arena/.brain-79/ \
    "$SCRIPT_DIR/truco_arena_snapshot/.brain-79/"
