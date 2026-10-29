"""Inspectable capabilities; no implicit fallback or stable-facade dispatch."""
from __future__ import annotations

from dataclasses import dataclass

from symq.backends import BACKENDS
from symq.phase import PhaseProgram

from .contracts import VerificationContract


@dataclass(frozen=True)
class Capabilities:
    supported: bool
    grammar: str
    theorem: str
    backend: str
    reason: str
    data: int | None
    ancillas: int | None
    pair_variables: int | None
    max_pair_variables: int | None
    classical_observations: bool = False
    independent_certificate: bool = False
    schema_version: int = 1
    common_blocks: tuple[tuple[int, ...], ...] = ()
    widest_data_component: int | None = None
    monolithic_supported: bool = False
    blocks_supported: bool = False


def backend_capabilities():
    """Current registry, including optional installed native width limits."""
    from symq.backends.zdd import MAX_WIDTH
    return {name: {"pair_variables": (MAX_WIDTH if name == "zdd" else
                                      getattr(cls, "max_width", None))}
            for name, cls in BACKENDS.items() if name in {"zdd", "zdd-native", "zdd-native-wide"}}


def inspect_program(program, contract=None, *, other=None, theorem=None, backend=None):
    from .hybrid import HybridIR
    if type(program) is HybridIR:
        program = program.to_program()
    if type(other) is HybridIR:
        other = other.to_program()
    from .domains import FullCube
    contract = contract or VerificationContract(theorem=theorem or "full_channel",
                                                 backend=backend or "zdd")
    if not isinstance(contract, VerificationContract):
        raise TypeError("VerificationContract required")
    data = getattr(program, "data", None)
    ancillas = getattr(program, "ancillas", None)
    domain = contract.domain or (FullCube(data) if type(data) is int and data > 0 else None)
    pairs = None if domain is None else 2 * domain.parameters
    engine = "zdd-native" if contract.backend == "zdd-native-blocks" else contract.backend
    limit = backend_capabilities().get(engine, {}).get("pair_variables")
    grammar = "unsupported"
    reason = "unsupported experimental program type"
    supported = False
    if type(program) is PhaseProgram:
        grammar = "sign_hmr"
        program.validate()
        supported = engine in {"zdd", "zdd-native", "zdd-native-wide"}
        reason = "exact outcome-factored sign/HMR channel"
        if contract.theorem == "instrument":
            supported, reason = False, "sign/HMR engine forgets classical records"
        if engine.startswith("zdd-native") and engine not in BACKENDS:
            supported, reason = False, "optional native backend is not installed"
        if supported and limit is not None and pairs > limit:
            supported, reason = False, "pair-variable width exceeds this explicit backend"
    else:
        from .hybrid import HybridProgram
        if type(program) is HybridProgram:
            grammar = "hybrid"
            program.validate()
            supported = contract.backend == "hybrid-exact" and isinstance(domain, FullCube)
            reason = ("bounded exact hybrid Kraus oracle" if supported else
                      "hybrid programs require hybrid-exact and a FullCube domain")
    blocks = ()
    widest = None
    monolithic = supported
    block_support = False
    if type(program) is PhaseProgram and type(other) is PhaseProgram:
        from .blocks import plan_blocks
        if (program.data, program.ancillas) == (other.data, other.ancillas):
            plan, _ = plan_blocks(program, other)
            blocks = tuple(block.wires for block in plan)
            widest = max(block.data for block in plan)
            native_limit = backend_capabilities().get("zdd-native", {}).get("pair_variables")
            block_support = (native_limit is not None and 2 * widest <= native_limit and
                             isinstance(domain, FullCube) and contract.theorem == "full_channel")
    if contract.backend == "zdd-native-blocks":
        supported = block_support
        reason = ("exact independent full-channel wire blocks" if supported else
                  "native blocks require two matching sign/HMR frames, FullCube and admissible blocks")
    if domain is not None and data != domain.data:
        supported, reason = False, "coherent domain data width differs from program"
    return Capabilities(supported, grammar, contract.theorem, contract.backend, reason,
                        data, ancillas, pairs, limit, contract.theorem == "instrument",
                        common_blocks=blocks, widest_data_component=widest,
                        monolithic_supported=monolithic, blocks_supported=block_support)


inspect = inspect_program
