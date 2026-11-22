"""Shared delimited protocol block engine for native AI instruction harnesses (Phase 11: R-2.1)."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
import re

DELIMITED_START_REGEX = re.compile(
    r"<!--\s*brain79:start(?:\s+v?([0-9]+\.[0-9]+\.[0-9]+(?:[-.][0-9A-Za-z.]+)?))?\s*-->",
    re.IGNORECASE,
)
DELIMITED_END_REGEX = re.compile(r"<!--\s*brain79:end\s*-->", re.IGNORECASE)


def render_compact_harness_block(version: str | None = None) -> str:
    """Render the compact delimited protocol block from HARNESS_COMPACT.md."""
    from brain79 import __version__

    active_version = version or __version__
    pkg_templates = resources.files("brain79.templates")
    raw = (pkg_templates / "HARNESS_COMPACT.md").read_text(encoding="utf-8")
    return raw.replace("{{VERSION}}", active_version).strip()


def extract_delimited_block(rendered_template: str) -> str:
    """Extract the delimited block from a rendered template (or return as-is if already bounded)."""
    start_m = DELIMITED_START_REGEX.search(rendered_template)
    end_m = DELIMITED_END_REGEX.search(rendered_template)
    if start_m and end_m and start_m.start() < end_m.start():
        return rendered_template[start_m.start() : end_m.end()]
    return rendered_template.strip()


def sync_delimited_file(
    target: Path,
    rendered_block: str,
    *,
    full_initial_content: str | None = None,
    dry_run: bool = False,
    legacy_header: str | None = None,
    legacy_notes_header: str | None = None,
    version: str | None = None,
    error_code: str = "corrupted_harness_delimiters",
) -> tuple[bool, str]:
    """Create, update, or append a delimited brain79 protocol block non-destructively.

    Raises ValueError with `error_code` if existing markers are mismatched, duplicated, or inverted.
    """
    from brain79 import __version__

    active_version = version or __version__
    managed_block = extract_delimited_block(rendered_block)

    if not target.exists():
        initial = full_initial_content if full_initial_content is not None else (managed_block + "\n")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(initial, encoding="utf-8", newline="\n")
        return True, f"created {target.name} with delimited protocol block v{active_version}"

    content = target.read_text(encoding="utf-8")
    starts = list(DELIMITED_START_REGEX.finditer(content))
    ends = list(DELIMITED_END_REGEX.finditer(content))

    if (
        len(starts) > 1
        or len(ends) > 1
        or len(starts) != len(ends)
        or (starts and ends and starts[0].start() > ends[0].start())
    ):
        raise ValueError(
            f"{error_code}: {target.name} contains mismatched, multiple, or malformed brain79 delimiters. "
            "Restore markers or remove the damaged block."
        )

    if starts and ends:
        start_m = starts[0]
        end_m = ends[-1]
        prefix = content[: start_m.start()]
        suffix = content[end_m.end() :]
        new_content = prefix + managed_block + suffix
        if new_content == content:
            return False, f"{target.name} is already up-to-date"
        if not dry_run:
            target.write_text(new_content, encoding="utf-8", newline="\n")
        return True, f"updated {target.name} to v{active_version}"

    # Optional legacy unmarked header wrapping (used by AGENTS.md)
    if legacy_header:
        header_pos = content.find(legacy_header)
        if header_pos != -1:
            prefix = content[:header_pos]
            notes_pos = content.find(legacy_notes_header, header_pos) if legacy_notes_header else -1
            suffix = content[notes_pos:] if notes_pos != -1 else ""
            if prefix and not prefix.endswith("\n\n"):
                prefix = prefix.rstrip() + "\n\n"
            if suffix and not suffix.startswith("\n"):
                suffix = "\n\n" + suffix.lstrip("\n")
            new_content = prefix + managed_block + suffix
            if not dry_run:
                target.write_text(new_content, encoding="utf-8", newline="\n")
            return True, f"wrapped legacy {target.name} in delimited protocol block v{active_version}"

    # Markerless existing file: append delimited block to bottom without touching user content
    if content.strip():
        new_content = content.rstrip() + "\n\n" + managed_block + "\n"
    else:
        new_content = managed_block + "\n"
    if not dry_run:
        target.write_text(new_content, encoding="utf-8", newline="\n")
    return True, f"appended delimited protocol block v{active_version} to {target.name}"


def diagnose_delimited_file(
    target: Path,
    *,
    expected_version: str | None = None,
    rel_label: str | None = None,
    required: bool = True,
) -> list[str]:
    """Diagnose a delimited harness file for missing, corrupted, unmarked, or stale blocks."""
    from brain79 import __version__

    label = rel_label or target.name
    exp_ver = expected_version or __version__

    if not target.is_file():
        return [f"{label} is missing."] if required else []

    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Could not read {label}: {exc}"]

    starts = list(DELIMITED_START_REGEX.finditer(content))
    ends = list(DELIMITED_END_REGEX.finditer(content))

    if (
        len(starts) > 1
        or len(ends) > 1
        or len(starts) != len(ends)
        or (starts and ends and starts[0].start() > ends[0].start())
    ):
        return [f"corrupted_harness_delimiters: {label} contains corrupted delimiters."]

    if not starts or not ends:
        return [f"{label} lacks delimited brain79 protocol markers."]

    v_block = starts[0].group(1)
    if not v_block or v_block != exp_ver:
        return [f"{label} protocol (v{v_block or 'unknown'}) lags behind v{exp_ver}."]

    return []
