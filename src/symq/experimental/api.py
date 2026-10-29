"""Explicit installed experimental API, with exact outcomes and checked witnesses."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram
from symq.resources import ResourceLimitExceeded, VerificationSession

from .capabilities import inspect_program
from .channel import EmptyDomain, check_channel, coherence_signature
from .contracts import VerificationContract, VerificationResult


def program_hash(program):
    from .serialization import program_to_dict
    return hashlib.sha256(json.dumps(program_to_dict(program), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _program(program):
    from .hybrid import HybridIR, HybridProgram
    if type(program) is HybridIR:
        return program.to_program()
    if type(program) is PhaseProgram:
        program.validate()
        return PhaseProgram(program.data, program.ancillas, list(program.ops))
    if type(program) is HybridProgram:
        program.validate()
        return HybridProgram(program.data, program.ancillas, list(program.ops))
    return program


def _contract(contract, theorem, backend, kwargs, engine=None):
    if engine is not None:
        if backend is not None:
            raise ValueError("engine and backend aliases cannot be supplied together")
        backend = engine
    if contract is not None:
        if type(contract) is not VerificationContract:
            raise TypeError("VerificationContract required")
        if ((theorem is not None and theorem != contract.theorem) or
                (backend is not None and backend != contract.backend) or kwargs):
            raise ValueError("explicit theorem/backend conflicts with the contract")
        return contract
    return VerificationContract(theorem=theorem or "full_channel", backend=backend or "zdd",
                                **kwargs)


def _project(matrix, outputs, width):
    """Exact partial trace followed by the declared output-wire ordering."""
    discarded = tuple(q for q in range(width) if q not in outputs)
    result = {}
    for (row, col), value in matrix.items():
        if any((row >> q & 1) != (col >> q & 1) for q in discarded):
            continue
        r = sum((row >> q & 1) << j for j, q in enumerate(outputs))
        c = sum((col >> q & 1) << j for j, q in enumerate(outputs))
        result[r, c] = result.get((r, c), 0) + value
        if result[r, c] == 0:
            del result[r, c]
    return result


def _hybrid_image(program, x, y, contract, side, guard):
    from .hybrid import coherence_image, coherence_instrument
    if contract.theorem == "instrument":
        return coherence_instrument(program, x, y, observed_slots=contract.observed_slots,
                                    _guard=guard)
    image = coherence_image(program, x, y, _guard=guard)
    if contract.theorem == "reduced_channel":
        outputs = contract.left_outputs if side == "left" else contract.right_outputs
        return _project(image, outputs, program.width)
    return image


def _hybrid_compare(left, right, contract, guard):
    from .channel import _validate_programs
    from .hybrid import HybridProgram
    if type(left) is not HybridProgram or type(right) is not HybridProgram:
        raise UnsupportedOperation("hybrid-exact requires two HybridPrograms")
    if contract.theorem == "instrument":
        if (left.data, left.ancillas) != (right.data, right.ancillas):
            raise ValueError("instrument quantum input/output frames differ")
    else:
        # Validation is common; the helper deliberately accepts only PhaseProgram.
        a = PhaseProgram(left.data, left.ancillas)
        b = PhaseProgram(right.data, right.ancillas)
        _validate_programs(a, b, contract.theorem, contract.left_outputs, contract.right_outputs)
    checked = 0
    for x in range(1 << left.data):
        for y in range(1 << left.data):
            guard.check_time()
            a = _hybrid_image(left, x, y, contract, "left", guard)
            b = _hybrid_image(right, x, y, contract, "right", guard)
            checked += 1
            if a != b:
                return False, (x, y), checked
    return True, None, checked


def verify(left, right, contract=None, *, theorem=None, backend=None, engine=None,
           budget=None, **kwargs):
    """Establish exactly the requested theorem, with no automatic engine selection.

    Resource exhaustion is inconclusive, never a partial PASS. Experimental
    results record exact computations; they are not independently checkable
    UNSAT certificates. Full/reduced channel theorems forget classical records.
    """
    contract = _contract(contract, theorem, backend, kwargs, engine)
    lhash = rhash = ""

    def result(outcome, reason, **fields):
        return VerificationResult(outcome, contract.theorem, contract.backend, reason,
                                  lhash, rhash, contract.sha256, **fields)
    try:
        with VerificationSession(budget) as session:
            left, right = _program(left), _program(right)
            lhash, rhash = program_hash(left), program_hash(right)
            caps = (inspect_program(left, contract, other=right),
                    inspect_program(right, contract, other=left))
            if any(not c.supported for c in caps):
                return result("unsupported", "; ".join(c.reason for c in caps if not c.supported))
            if contract.backend == "hybrid-exact":
                equivalent, witness, checked = _hybrid_compare(left, right, contract, session)
                if (program_hash(left), program_hash(right)) != (lhash, rhash):
                    raise RuntimeError("input programs changed during verification")
                return result("equivalent" if equivalent else "different",
                              "all basis coherences match" if equivalent else
                              "exact hybrid channel/instrument images differ",
                              witness=witness, witness_checked=witness is not None,
                              witness_kind=None if witness is None else
                              ("input" if witness[0] == witness[1] else "coherence"),
                              statistics=(("checked_pairs", checked),))
            if contract.backend == "zdd-native-blocks":
                from .blocks import decompose_decision
                decision, block_stats = decompose_decision(left, right, budget=budget)
                decision = replace(decision, statistics=(
                    ("components", block_stats.components),
                    ("widest_data_component", block_stats.widest_data_component)))
            else:
                decision = check_channel(left, right, backend=contract.backend,
                                         theorem=contract.theorem, domain=contract.domain,
                                         left_outputs=contract.left_outputs,
                                         right_outputs=contract.right_outputs, budget=budget)
            if (program_hash(left), program_hash(right)) != (lhash, rhash):
                raise RuntimeError("input programs changed during verification")
            return result("equivalent" if decision.equivalent else "different", decision.reason,
                          witness=decision.witness, witness_kind=decision.witness_kind,
                          witness_checked=decision.witness is not None,
                          statistics=(("coefficients_before", decision.coefficients_before),
                                      ("coefficients_after", decision.coefficients_after)) +
                                     decision.statistics,
                          coefficient_reductions=decision.coefficient_reductions)
    except ResourceLimitExceeded as exc:
        return result("inconclusive", str(exc))
    except EmptyDomain as exc:
        return result("precondition_failed", str(exc))
    except UnsupportedOperation as exc:
        return result("unsupported", str(exc))


def replay(result, left, right, contract=None, *, budget=None):
    """Recheck a counterexample, binding sources and the entire theorem contract.

    An equality result cannot be authenticated by replaying its JSON record.
    """
    if type(result) is not VerificationResult:
        raise TypeError("VerificationResult required; result JSON is not proof authority")
    if type(contract) is not VerificationContract:
        raise TypeError("the original VerificationContract is required")
    with VerificationSession(budget) as session:
        left, right = _program(left), _program(right)
        if result.outcome != "different" or result.witness is None:
            raise ValueError("only a concrete difference has witness replay semantics")
        if (result.left_sha256, result.right_sha256, result.contract_sha256) != (
                program_hash(left), program_hash(right), contract.sha256):
            raise ValueError("replay source or contract hash mismatch")
        if (result.theorem, result.backend, result.schema_version) != (
                contract.theorem, contract.backend, contract.schema_version):
            raise ValueError("replay theorem/backend metadata conflicts with the contract")
        if contract.domain is not None and contract.domain.data != left.data:
            raise ValueError("replay domain data width differs from program")
        if type(left) is PhaseProgram and type(right) is PhaseProgram:
            from .channel import _validate_programs
            if contract.theorem == "instrument":
                raise ValueError("sign/HMR channel witnesses do not certify an instrument")
            _validate_programs(left, right, contract.theorem, contract.left_outputs,
                               contract.right_outputs)
        x, y = result.witness
        if contract.domain is not None and not (contract.domain.contains(x) and
                                                contract.domain.contains(y)):
            raise ValueError("witness outside coherent domain")
        if contract.backend == "hybrid-exact":
            different = (_hybrid_image(left, x, y, contract, "left", session) !=
                         _hybrid_image(right, x, y, contract, "right", session))
        else:
            different = coherence_signature(left, x, y, contract.left_outputs) != (
                coherence_signature(right, x, y, contract.right_outputs))
        if not different:
            raise ValueError("claimed counterexample fails concrete replay")
        return replace(result, witness_checked=True, proof_kind="witness_replayed")


def prepare_reference(reference, contract=None, *, theorem=None, backend=None,
                      engine=None, budget=None, max_cache_entries=64, **kwargs):
    from .prepared import PreparedReference
    return PreparedReference(reference, _contract(contract, theorem, backend, kwargs, engine),
                             budget=budget, max_cache_entries=max_cache_entries)


def inspect(program, other=None, *, contract=None, theorem=None, backend=None, engine=None):
    contract = _contract(contract, theorem, backend, {}, engine)
    return inspect_program(program, contract, other=other)
