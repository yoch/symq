"""Opt-in research semantics shipped with SymQ; stable defaults are unchanged."""
from .api import inspect, inspect_program, prepare_reference, program_hash, replay, verify
from .capabilities import Capabilities
from .contracts import VerificationContract, VerificationResult
from .domains import AffineDomain, FullCube, PredicateDomain, PreparedDomain
from .prepared import PreparedReference
from .profiling import ProfileReport, profile

__all__ = [
           "AffineDomain",
           "Capabilities",
           "FullCube",
           "PredicateDomain",
           "PreparedDomain",
           "PreparedReference",
           "ProfileReport",
           "VerificationContract",
           "VerificationResult",
           "inspect",
           "inspect_program",
           "prepare_reference",
           "profile",
           "program_hash",
           "replay",
           "verify",
]
