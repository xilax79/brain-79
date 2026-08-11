#!/usr/bin/env -S python3 -u
"""Backwards-compatible shim for the migration script.

The real implementation lives in `brain79.core.migration` (installed with the
package). This file is kept so that `python scripts/migrate_frontmatter.py`
keeps working for users who invoke it directly from a checkout.

When invoked as a script, accepts:
    --dry-run    Preview only (default for the standalone form too)
"""
from __future__ import annotations

import sys

from brain79.config import get_wiki_root
from brain79.core.migration import migrate_wiki


def main() -> None:
    root = get_wiki_root()
    is_dry = "--dry-run" in sys.argv or "--apply" not in sys.argv
    print(migrate_wiki(root, dry_run=is_dry))


if __name__ == "__main__":
    main()
