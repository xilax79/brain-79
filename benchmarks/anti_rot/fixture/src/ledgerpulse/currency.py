"""Currency formatting, rounding, and conversion utilities."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN

from .models import Money

SUPPORTED_CURRENCIES: frozenset[str] = frozenset({"USD", "EUR", "GBP"})
DEFAULT_CURRENCY: str = "USD"


def round_half_even(value: float) -> int:
    """Round a floating-point cent value using banker's rounding (half-to-even)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def format_money(money: Money) -> str:
    """Format a Money instance as '<CUR> <dollars>.<cents>'."""
    sign = "-" if money.amount_cents < 0 else ""
    abs_cents = abs(money.amount_cents)
    dollars, cents = divmod(abs_cents, 100)
    return f"{money.currency} {sign}{dollars}.{cents:02d}"


def convert_cents(amount_cents: int, rate_bps: int) -> int:
    """Scale an integer cent amount by a basis-point rate (10000 bps = 1.0x)."""
    return round_half_even((amount_cents * rate_bps) / 10_000)
