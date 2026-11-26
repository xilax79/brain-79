"""Core domain models for LedgerPulse."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InvoiceStatus(str, Enum):
    """Lifecycle status of an invoice."""

    DRAFT = "draft"
    POSTED = "posted"
    PAID = "paid"
    VOID = "void"


@dataclass(frozen=True)
class Money:
    """Monetary value represented in integer minor units (cents)."""

    amount_cents: int
    currency: str = "USD"


@dataclass(frozen=True)
class LineItem:
    """Single billable line item on an invoice."""

    sku: str
    description: str
    quantity: int
    unit_price_cents: int
    tax_rate_bps: int = 0


@dataclass
class Invoice:
    """Customer invoice containing line items and billing metadata."""

    invoice_id: str
    customer_id: str
    items: list[LineItem] = field(default_factory=list)
    status: InvoiceStatus = InvoiceStatus.DRAFT
    discount_bps: int = 0
    currency: str = "USD"
    notes: str = ""
