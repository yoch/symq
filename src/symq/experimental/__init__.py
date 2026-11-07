"""Opt-in research semantics shipped with SymQ; stable defaults are unchanged."""
from .api import inspect, inspect_program, prepare_reference, program_hash, replay, verify
from .capabilities import Capabilities
from .contracts import VerificationContract, VerificationResult
from .domains import AffineDomain, FullCube, PredicateDomain, PreparedDomain
from .prepared import PreparedReference
from .profiling import ProfileReport, profile
from .table_xor import (
    PredicateValues,
    ReceiptMismatch,
    TableXorContract,
    TableXorResult,
    check_table_xor,
    replay_table_xor,
)

__all__ = [
           "AffineDomain",
           "Capabilities",
           "FullCube",
           "PredicateDomain",
           "PredicateValues",
           "PreparedDomain",
           "PreparedReference",
           "ProfileReport",
           "ReceiptMismatch",
           "TableXorContract",
           "TableXorResult",
           "VerificationContract",
           "VerificationResult",
           "check_table_xor",
           "inspect",
           "inspect_program",
           "prepare_reference",
           "profile",
           "program_hash",
           "replay",
           "replay_table_xor",
           "verify",
]
