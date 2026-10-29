"""Inspectable capabilities; no implicit fallback or stable-facade dispatch."""
from __future__ import annotations

from dataclasses import dataclass
from inspect import signature

from symq.backends import BACKENDS
from symq.phase import PhaseProgram

from .contracts import VerificationContract


@dataclass(frozen=True)
class CapabilityDiagnostic:
    category: str
    message: str
    resource: str | None = None
    observed: int | None = None
    limit: int | None = None


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
    grammar_supported: bool = False
    static_admissible: bool = False
    backend_available: bool = False
    contract_compatible: bool = False
    static_limits: tuple[tuple[str, int], ...] = ()
    runtime_limits: tuple[tuple[str, int | None], ...] = ()
    diagnostics: tuple[CapabilityDiagnostic, ...] = ()
    refusal_outcome: str = "unsupported"


def backend_capabilities():
    """Declared representation limits, independent of optional installation.

    An unavailable accelerator still has a known representation boundary;
    availability is a separate capability and must not erase that boundary.
    """
    from symq.backends.zdd import MAX_WIDTH
    limits = {"zdd": MAX_WIDTH, "zdd-native": 64, "zdd-native-wide": 128}
    return {name: {"pair_variables": getattr(BACKENDS.get(name), "max_width", limit),
                   "available": name in BACKENDS}
            for name, limit in limits.items()}


def inspect_program(program, contract=None, *, other=None, theorem=None, backend=None):
    """Predict statically decidable preconditions, without executing an engine.

    ``other`` is the candidate: output mappings in the contract retain their
    reference/candidate order. Runtime limits are announced, not proven to fit.
    An admissible program can still exhaust those limits during verification.
    """
    from .hybrid import HybridIR, HybridProgram, coherence_image
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
    explanation = "unsupported experimental program type"
    grammar_supported = False
    available = engine in BACKENDS or engine == "hybrid-exact"
    static_ok = True
    contract_ok = True
    static_limits = ()
    runtime_limits = ()
    diagnostics = []

    def reject(category, message, resource=None, observed=None, maximum=None):
        diagnostics.append(CapabilityDiagnostic(category, message, resource, observed, maximum))

    programs = (program,) if other is None else (program, other)
    for value in programs:
        if type(value) in {PhaseProgram, HybridProgram}:
            value.validate()
    if type(program) is PhaseProgram:
        grammar = "sign_hmr"
        grammar_supported = (engine in {"zdd", "zdd-native", "zdd-native-wide"}
                             and contract.theorem != "instrument")
        explanation = "exact outcome-factored sign/HMR channel"
        if not grammar_supported:
            reject("grammar", "sign/HMR channels require a ZDD engine and forget classical records")
        from .channel import check_channel
        defaults = signature(check_channel).parameters
        static_limits = (("events", defaults["max_events"].default),
                         ("ops", defaults["max_ops"].default))
        runtime_limits = (("nodes", None), ("terms", None), ("seconds", None))
    elif type(program) is HybridProgram:
        grammar = "hybrid"
        grammar_supported = contract.backend == "hybrid-exact"
        explanation = "bounded exact hybrid Kraus oracle"
        if not grammar_supported:
            reject("grammar", "hybrid programs require the explicit hybrid-exact engine")
        if not isinstance(domain, FullCube):
            contract_ok = False
            reject("contract", "hybrid-exact requires a FullCube coherent domain")
        # Read the oracle defaults rather than duplicating its fixed limits.
        defaults = signature(coherence_image).parameters
        static_limits = (("width", defaults["max_width"].default),
                         ("events", defaults["max_events"].default))
        runtime_limits = (("branches", defaults["max_branches"].default),
                          ("terms", None), ("seconds", None))
    else:
        reject("grammar", explanation)

    if not available:
        reject("availability", "optional native backend is not installed")
    matching_types = all(type(value) is type(program) for value in programs)
    if not matching_types:
        grammar_supported = False
        reject("grammar", "both programs must use the same supported experimental grammar")
    if grammar != "unsupported" and matching_types:
        for value in programs:
            if domain is not None and value.data != domain.data:
                contract_ok = False
                reject("contract", "coherent domain data width differs from program")
            for resource, maximum in static_limits:
                observed = (value.width if resource == "width" else len(value.ops)
                            if resource == "ops" else value.measurements
                            if type(value) is PhaseProgram else
                            sum(op.kind in {"hmr", "measure_z"} for op in value.ops))
                if observed > maximum:
                    static_ok = False
                    reject("static_limit", f"{resource} limit exceeded: observed {observed}, limit {maximum}",
                           resource, observed, maximum)
        if pairs is not None and limit is not None and pairs > limit:
            static_ok = False
            reject("static_limit", "pair-variable width exceeds this explicit backend",
                   "pair_variables", pairs, limit)
        if contract.theorem == "reduced_channel":
            if len(contract.left_outputs) != len(contract.right_outputs):
                contract_ok = False
                reject("contract", "observed output dimensions differ")
            for outputs, value in ((contract.left_outputs, program),
                                   (contract.right_outputs, other)):
                if value is not None and any(q >= value.width for q in outputs):
                    contract_ok = False
                    reject("contract", "retained output mapping contains a wire outside the program")
        elif other is not None and (program.data, program.ancillas) != (other.data, other.ancillas):
            contract_ok = False
            reject("contract", "full quantum input/output frames differ")
        if contract.theorem == "instrument" and type(program) is HybridProgram:
            for value in programs:
                initialized = {op.slot for op in value.ops if op.kind in {"hmr", "measure_z", "store"}}
                if any(slot not in initialized for slot in contract.observed_slots):
                    contract_ok = False
                    reject("contract", "observed classical slot not initialized")
    blocks = ()
    widest = None
    monolithic = grammar_supported and available and static_ok and contract_ok
    block_support = False
    block_admissible = False
    if type(program) is PhaseProgram and type(other) is PhaseProgram:
        from .blocks import plan_blocks
        if (program.data, program.ancillas) == (other.data, other.ancillas):
            plan, _ = plan_blocks(program, other)
            blocks = tuple(block.wires for block in plan)
            widest = max(block.data for block in plan)
            native_limit = backend_capabilities().get("zdd-native", {}).get("pair_variables")
            block_admissible = (native_limit is not None and 2 * widest <= native_limit and
                                isinstance(domain, FullCube) and contract.theorem == "full_channel")
            block_support = "zdd-native" in BACKENDS and block_admissible and contract_ok
    if contract.backend == "zdd-native-blocks":
        # Monolithic width is diagnostic only for this explicitly selected engine.
        # The actual block theorem is restricted to FullCube/full_channel.
        static_ok = block_admissible
        diagnostics = [d for d in diagnostics if d.resource != "pair_variables"]
        if not block_admissible:
            reject("static_limit", "native blocks require two matching sign/HMR frames, FullCube and admissible blocks")
        explanation = "exact independent full-channel wire blocks"
    supported = grammar_supported and available and static_ok and contract_ok
    reason = explanation if supported else "; ".join(dict.fromkeys(d.message for d in diagnostics))
    # Hybrid oracle limits have historically produced resource exhaustion. Keep
    # that result category while refusing to advertise static admissibility.
    refusal_outcome = ("inconclusive" if grammar == "hybrid" and grammar_supported and
                       available and contract_ok and not static_ok else "unsupported")
    return Capabilities(supported, grammar, contract.theorem, contract.backend, reason,
                        data, ancillas, pairs, limit, contract.theorem == "instrument",
                        common_blocks=blocks, widest_data_component=widest,
                        monolithic_supported=monolithic, blocks_supported=block_support,
                        grammar_supported=grammar_supported, static_admissible=static_ok,
                        backend_available=available, contract_compatible=contract_ok,
                        static_limits=static_limits, runtime_limits=runtime_limits,
                        diagnostics=tuple(diagnostics), refusal_outcome=refusal_outcome)


inspect = inspect_program
