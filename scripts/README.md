# brain-79 Scripts Policy

This directory contains standalone utility scripts for `brain-79`.

## Validation & Bypass Policy

1. **`scripts/migrate_frontmatter.py`** is the **ONLY** script authorized to bypass organizational validation. Its explicit purpose is to perform progressive migration on legacy wikis by adding frontmatter and initializing navigation registries.

2. **All other scripts** that modify wiki articles **MUST** delegate writes through `brain79_write` or `write_article` in `brain79.core.wiki`:

```python
from brain79.core.wiki import write_article

# Correct way to modify wiki files from scripts:
write_article("features/example.md", new_content)
```

3. Direct raw file writes (`Path.write_text`) to `.brain-79/*.md` are **PROHIBITED** outside of unit test fixtures and `migrate_frontmatter.py`. Any direct write that bypasses validation will be rejected by the git pre-commit hook during `git commit`.
