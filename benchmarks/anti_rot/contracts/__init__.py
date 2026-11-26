"""Hidden per-session contract specifications and runner for SPEC-016."""

from __future__ import annotations

from benchmarks.anti_rot.contracts.runner import ContractResult, run_session_contract
from benchmarks.anti_rot.contracts.specs import (
    SESSION_CONTRACTS,
    JsSymbolSpec,
    PySymbolSpec,
    SessionContractSpec,
)

__all__ = [
    "ContractResult",
    "JsSymbolSpec",
    "PySymbolSpec",
    "SESSION_CONTRACTS",
    "SessionContractSpec",
    "run_session_contract",
]
