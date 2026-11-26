"""Pinned per-session contract specifications for LedgerPulse (S2-S12)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PySymbolSpec:
    """Expected Python symbol signature and optional class ownership."""

    module_path: str
    symbol_name: str
    params: tuple[str, ...] = ()
    class_name: str | None = None


@dataclass(frozen=True)
class JsSymbolSpec:
    """Expected JS/ESM exported symbol and parameter list."""

    module_path: str
    symbol_name: str
    params: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionContractSpec:
    """Deterministic verification contract for a single benchmark session."""

    session_id: str
    required_files: tuple[str, ...] = ()
    forbidden_files: tuple[str, ...] = ()
    py_symbols: tuple[PySymbolSpec, ...] = ()
    forbidden_py_symbols: tuple[tuple[str, str], ...] = ()
    py_constants: dict[str, dict[str, object]] = field(default_factory=dict)
    js_symbols: tuple[JsSymbolSpec, ...] = ()
    js_constants: dict[str, dict[str, object]] = field(default_factory=dict)
    triage_mode: str = "code"  # "code" | "type_a" | "type_b"


SESSION_CONTRACTS: dict[str, SessionContractSpec] = {
    "S2": SessionContractSpec(
        session_id="S2",
        required_files=("src/ledgerpulse/pricing.py",),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/pricing.py",
                symbol_name="calculate_bulk_discount",
                params=("items",),
            ),
        ),
        py_constants={
            "src/ledgerpulse/pricing.py": {
                "TIERED_BULK_THRESHOLD": 10,
                "TIERED_BULK_DISCOUNT_BPS": 500,
            }
        },
    ),
    "S3": SessionContractSpec(
        session_id="S3",
        required_files=("src/ledgerpulse/ledger.py",),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/ledger.py",
                class_name="Ledger",
                symbol_name="void_invoice",
                params=("invoice_id", "reason"),
            ),
        ),
        py_constants={
            "src/ledgerpulse/ledger.py": {
                "VOID_REASON_MAX_LEN": 200,
            }
        },
    ),
    "S4": SessionContractSpec(
        session_id="S4",
        required_files=("src/ledgerpulse/tax.py",),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/tax.py",
                symbol_name="calculate_late_fee",
                params=("amount_cents", "days_overdue"),
            ),
        ),
        py_constants={
            "src/ledgerpulse/tax.py": {
                "LATE_FEE_BPS": 250,
                "LATE_FEE_GRACE_DAYS": 15,
            }
        },
    ),
    "S5": SessionContractSpec(
        session_id="S5",
        required_files=("src/ledgerpulse/pricing.py",),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/pricing.py",
                symbol_name="calculate_invoice_grand_total",
                params=("invoice", "include_tax"),
            ),
        ),
        forbidden_py_symbols=(("src/ledgerpulse/pricing.py", "compute_invoice_total"),),
    ),
    "S6": SessionContractSpec(
        session_id="S6",
        required_files=("src/reporter/schema.mjs", "src/reporter/index.mjs"),
        js_symbols=(
            JsSymbolSpec(
                module_path="src/reporter/schema.mjs",
                symbol_name="validateSummaryDocument",
                params=("payload", "options"),
            ),
            JsSymbolSpec(
                module_path="src/reporter/index.mjs",
                symbol_name="validateSummaryDocument",
            ),
        ),
    ),
    "S7": SessionContractSpec(
        session_id="S7",
        required_files=("src/ledgerpulse/tax.py",),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/tax.py",
                symbol_name="calculate_late_fee",
                params=("amount_cents", "days_overdue", "compound"),
            ),
        ),
        py_constants={
            "src/ledgerpulse/tax.py": {
                "LATE_FEE_BPS": 500,
                "LATE_FEE_GRACE_DAYS": 7,
            }
        },
    ),
    "S8": SessionContractSpec(
        session_id="S8",
        required_files=("src/ledgerpulse/export.py", "src/reporter/formatter.mjs"),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/export.py",
                symbol_name="export_audit_bundle",
                params=("ledger", "include_void"),
            ),
        ),
        py_constants={
            "src/ledgerpulse/export.py": {
                "SCHEMA_VERSION": "2.0",
            }
        },
        js_symbols=(
            JsSymbolSpec(
                module_path="src/reporter/formatter.mjs",
                symbol_name="formatAuditBanner",
                params=("bundle",),
            ),
        ),
    ),
    "S9": SessionContractSpec(
        session_id="S9",
        triage_mode="type_a",
    ),
    "S10": SessionContractSpec(
        session_id="S10",
        triage_mode="type_b",
    ),
    "S11": SessionContractSpec(
        session_id="S11",
        required_files=(
            "src/ledgerpulse/reconciliation/__init__.py",
            "src/ledgerpulse/reconciliation/matcher.py",
        ),
        forbidden_files=("src/ledgerpulse/reconcile.py",),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/reconciliation/matcher.py",
                symbol_name="reconcile_payments",
                params=("ledger", "external_txns"),
            ),
        ),
    ),
    "S12": SessionContractSpec(
        session_id="S12",
        required_files=("src/ledgerpulse/validation.py", "src/reporter/cli.mjs"),
        py_symbols=(
            PySymbolSpec(
                module_path="src/ledgerpulse/validation.py",
                symbol_name="verify_audit_readiness",
                params=("ledger",),
            ),
        ),
        py_constants={
            "src/ledgerpulse/validation.py": {
                "AUDIT_FREEZE_TAG": "v1-audit-ready",
            }
        },
        js_symbols=(
            JsSymbolSpec(
                module_path="src/reporter/cli.mjs",
                symbol_name="verifyBundleCli",
                params=("bundle",),
            ),
        ),
    ),
}
