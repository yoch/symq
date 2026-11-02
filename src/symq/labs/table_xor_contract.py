"""Compatibility imports for the maintained opt-in finite-table XOR API.

The audited implementation now lives in ``symq.experimental.table_xor``.
Historical imports remain identical objects; no backend or theorem changes.
"""
from symq.experimental.table_xor import (
    ReceiptMismatch,
    TableXorContract,
    TableXorResult,
    check_table_xor,
    replay_table_xor,
)

__all__ = [
    "ReceiptMismatch",
    "TableXorContract",
    "TableXorResult",
    "check_table_xor",
    "replay_table_xor",
]
