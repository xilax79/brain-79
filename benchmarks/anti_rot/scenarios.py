"""12-session longitudinal benchmark scenario definitions (SPEC-016 R-2.2, R-2.3)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

FORBIDDEN_PROMPT_TERMS: tuple[str, ...] = ("brain79", ".brain-79", "docs/", "mcp")


@dataclass(frozen=True)
class SessionScenario:
    """Definition of a single cold-start benchmark session."""

    session_id: str
    title: str
    triage_type: str  # "bootstrap" | "code" | "type_a" | "type_b"
    prompt: str


def prompt_sha256(value: str | SessionScenario) -> str:
    """Return the SHA-256 hex digest of a session prompt for parity verification."""
    text = value.prompt if isinstance(value, SessionScenario) else value
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


SCENARIOS: tuple[SessionScenario, ...] = (
    SessionScenario(
        session_id="S1",
        title="Initial documentation bootstrap",
        triage_type="bootstrap",
        prompt=(
            "Perform an initial documentation bootstrap for the LedgerPulse repository "
            "(Python core under src/ledgerpulse/ and JavaScript reporter under src/reporter/). "
            "Document the architecture, modules, public entrypoints, and testing conventions "
            "according to the repository's documentation protocol. Do not modify source code."
        ),
    ),
    SessionScenario(
        session_id="S2",
        title="Add tiered bulk discount pricing",
        triage_type="code",
        prompt=(
            "In src/ledgerpulse/pricing.py, add constants TIERED_BULK_THRESHOLD = 10 and "
            "TIERED_BULK_DISCOUNT_BPS = 500, and implement calculate_bulk_discount(items) "
            "returning 500 basis points when total item quantity is at least 10 and 0 otherwise. "
            "Add unit tests in tests/test_ledgerpulse.py and update project documentation."
        ),
    ),
    SessionScenario(
        session_id="S3",
        title="Add invoice voiding to Ledger",
        triage_type="code",
        prompt=(
            "In src/ledgerpulse/ledger.py, add constant VOID_REASON_MAX_LEN = 200 and implement "
            "method Ledger.void_invoice(self, invoice_id, reason) that validates non-empty reason "
            "length <= 200, sets the invoice status to InvoiceStatus.VOID, and records a note. "
            "Add unit tests in tests/test_ledgerpulse.py and update project documentation."
        ),
    ),
    SessionScenario(
        session_id="S4",
        title="Fix late fee calculation and record decision",
        triage_type="code",
        prompt=(
            "In src/ledgerpulse/tax.py, fix overdue billing by adding constants "
            "LATE_FEE_BPS = 250 and LATE_FEE_GRACE_DAYS = 15, and implementing "
            "calculate_late_fee(amount_cents, days_overdue) returning 0 within the grace period "
            "and round_half_even((amount_cents * LATE_FEE_BPS) / 10_000) otherwise. "
            "Record this architectural decision and update project documentation and unit tests."
        ),
    ),
    SessionScenario(
        session_id="S5",
        title="Refactor compute_invoice_total to calculate_invoice_grand_total",
        triage_type="code",
        prompt=(
            "In src/ledgerpulse/pricing.py, rename compute_invoice_total to "
            "calculate_invoice_grand_total(invoice, include_tax=True) so callers can toggle tax "
            "inclusion, and remove compute_invoice_total completely. Update all callers in "
            "src/ledgerpulse/ledger.py, src/ledgerpulse/export.py, src/ledgerpulse/__init__.py, "
            "and tests/test_ledgerpulse.py, and update project documentation."
        ),
    ),
    SessionScenario(
        session_id="S6",
        title="Refactor JS summary validator to validateSummaryDocument",
        triage_type="code",
        prompt=(
            "In src/reporter/schema.mjs, add and export validateSummaryDocument(payload, options) "
            "(supporting options such as strict) and re-export validateSummaryDocument from "
            "src/reporter/index.mjs. Update tests/reporter.test.mjs and project documentation."
        ),
    ),
    SessionScenario(
        session_id="S7",
        title="Supersede late fee policy with compounding option",
        triage_type="code",
        prompt=(
            "Supersede the previous late-fee policy in src/ledgerpulse/tax.py: update "
            "LATE_FEE_BPS = 500 and LATE_FEE_GRACE_DAYS = 7, and update "
            "calculate_late_fee(amount_cents, days_overdue, compound=False) to support "
            "compounding. Record the superseding decision and update project documentation and tests."
        ),
    ),
    SessionScenario(
        session_id="S8",
        title="Add polyglot audit bundle export and banner formatter",
        triage_type="code",
        prompt=(
            "Implement a polyglot audit bundle feature: in src/ledgerpulse/export.py, set "
            'SCHEMA_VERSION = "2.0" and add export_audit_bundle(ledger, include_void=False); '
            "in src/reporter/formatter.mjs, add formatAuditBanner(bundle). "
            "Keep existing summary tests green, add new tests, and update project documentation."
        ),
    ),
    SessionScenario(
        session_id="S9",
        title="Read-only architecture consultation",
        triage_type="type_a",
        prompt=(
            "Read-only consultation: explain how Ledger.post_invoice and calculate_invoice_tax "
            "handle tax-exempt SKUs and discounts, and list which modules are involved. "
            "Do not edit any source files and do not make permanent documentation edits."
        ),
    ),
    SessionScenario(
        session_id="S10",
        title="Zero-code research on multi-currency rounding drift",
        triage_type="type_b",
        prompt=(
            "Zero-code research task: analyze potential multi-currency rounding drift across "
            "src/ledgerpulse/currency.py and src/ledgerpulse/pricing.py when applying discounts "
            "and taxes across USD, EUR, and GBP. Do not modify any files under src/. "
            "Persist a non-empty research document per the repository's documentation protocol."
        ),
    ),
    SessionScenario(
        session_id="S11",
        title="Move reconciliation module into reconciliation package",
        triage_type="code",
        prompt=(
            "Restructure payment reconciliation: move src/ledgerpulse/reconcile.py into the "
            "package src/ledgerpulse/reconciliation/__init__.py and "
            "src/ledgerpulse/reconciliation/matcher.py containing reconcile_payments(ledger, external_txns), "
            "and delete src/ledgerpulse/reconcile.py. Update imports in src/ledgerpulse/__init__.py "
            "and tests, and update project documentation."
        ),
    ),
    SessionScenario(
        session_id="S12",
        title="Add pre-audit readiness verification and freeze tag",
        triage_type="code",
        prompt=(
            "Implement final pre-audit freeze checks: in src/ledgerpulse/validation.py, define "
            'AUDIT_FREEZE_TAG = "v1-audit-ready" and verify_audit_readiness(ledger); in '
            "src/reporter/cli.mjs, export verifyBundleCli(bundle). "
            "Add unit tests in both Python and JS suites and update project documentation."
        ),
    ),
)

__all__ = [
    "FORBIDDEN_PROMPT_TERMS",
    "SCENARIOS",
    "SessionScenario",
    "prompt_sha256",
]
