"""Payment reconciliation against external bank/gateway transactions."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ledger import Ledger


@dataclass(frozen=True)
class ReconciliationReport:
    """Result of reconciling ledger credit entries against external transactions."""

    matched_ids: list[str] = field(default_factory=list)
    unmatched_ledger_ids: list[str] = field(default_factory=list)
    unmatched_external_ids: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Return True when all ledger and external transactions match."""
        return not self.unmatched_ledger_ids and not self.unmatched_external_ids


def reconcile_payments(
    ledger: Ledger,
    external_txns: list[dict[str, object]],
) -> ReconciliationReport:
    """Match ledger credit entries with external transactions by invoice_id and amount."""
    credits = [e for e in ledger.entries if e.kind == "credit"]
    remaining_ext = list(external_txns)
    matched: list[str] = []
    unmatched_ledger: list[str] = []

    for entry in credits:
        match_idx: int | None = None
        for idx, ext in enumerate(remaining_ext):
            if ext.get("invoice_id") == entry.invoice_id and ext.get("amount_cents") == entry.amount_cents:
                match_idx = idx
                break
        if match_idx is not None:
            matched.append(entry.entry_id)
            remaining_ext.pop(match_idx)
        else:
            unmatched_ledger.append(entry.entry_id)

    unmatched_ext = [str(ext.get("txn_id", "")) for ext in remaining_ext]
    return ReconciliationReport(
        matched_ids=matched,
        unmatched_ledger_ids=unmatched_ledger,
        unmatched_external_ids=unmatched_ext,
    )
