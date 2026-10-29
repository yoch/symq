"""Native C/ZDD outcome-factored full-channel theorem for the narrow HMR grammar.

Experimental and opt-in. All symbolic variables are *data input bits*, never
measurement indices. Both input-coherence halves share one exact algebra owner.
No general reset, conditional value gate, H, S/T, or general hybrid program.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from symq.backends import BACKENDS, make_algebra
from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram
from symq.resources import Guard, ResourceLimitExceeded, session_scoped

from .profiling import observe, stage


@dataclass(frozen=True)
class ChannelDecision:
    equivalent: bool
    backend: str
    theorem: str
    reason: str
    left_sha256: str
    right_sha256: str
    checked_events: int
    witness_kind: str | None = None
    witness: tuple[int, int] | None = None
    coefficients_before: int = 0
    coefficients_after: int = 0
    statistics: tuple[tuple[str, int | float], ...] = ()
    coefficient_reductions: tuple[CoefficientReductionRecord, ...] = ()


@dataclass(frozen=True)
class CoefficientReductionRecord:
    """Reconstruction metadata, not an independent UNSAT certificate.

    Each original g_i = constants[i] XOR XOR(basis[j] for j in
    reconstruction[i]). Each basis row is the XOR of original coefficients
    named by basis_combinations, plus its corresponding basis_constant.
    """
    basis_combinations: tuple[int, ...]
    basis_constants: tuple[int, ...]
    reconstruction: tuple[int, ...]
    constants: tuple[int, ...]

    @property
    def rank(self):
        return len(self.basis_combinations)


@dataclass(frozen=True)
class _State:
    outputs: tuple[Any, ...]
    phase0: Any
    outcome_coefficients: tuple[Any, ...]


@dataclass(frozen=True)
class _CoefficientReduction:
    basis: tuple[tuple[Any, Any], ...]
    reconstruction: tuple[int, ...]
    constants: tuple[int, ...]
    record: CoefficientReductionRecord


def _sha(program: PhaseProgram) -> str:
    program.validate()
    body = {
        "grammar": "sign-hmr/affine-outcomes/full-channel/v1",
        "data": program.data,
        "ancillas": program.ancillas,
        "ops": [[op.kind, list(op.qubits), op.outcome] for op in program.ops],
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _symbolic(
    program: PhaseProgram, algebra: Any, offset: int, guard: Guard,
    inputs: tuple[Any, ...] | None = None,
) -> _State:
    """One coherent symbolic branch family, with zero-initialized ancillas.

    The strict PhaseProgram grammar guarantees output values do not depend on
    outcomes and its phase is affine in distinct measurement-event symbols.
    This is NOT a semantics for classically conditioned X or arbitrary reset.
    """
    native = getattr(algebra, "simulate_hmr", None)
    if inputs is None and native is not None:
        outputs, phase0, coefficients = native(program, offset=offset)
        guard.check_time()
        return _State(tuple(outputs), phase0, tuple(coefficients))
    data = program.data
    state = [(inputs[q] if inputs is not None else algebra.variable(offset + q))
             if q < data else algebra.zero()
             for q in range(program.width)]
    phi0 = algebra.zero()
    coefficients: list[Any] = []
    for op in program.ops:
        guard.check_time()
        if op.kind == "mcx":
            *controls, target = op.qubits
            product = algebra.product([state[q] for q in controls])
            state[target] = algebra.xor(state[target], product)
        elif op.kind == "mcz":
            sign = algebra.product([state[q] for q in op.qubits])
            phi0 = algebra.xor(phi0, sign)
        elif op.kind == "hmr":
            if op.outcome != len(coefficients):
                raise UnsupportedOperation("non-fresh HMR event")
            coefficients.append(state[op.qubits[0]])
            state[op.qubits[0]] = algebra.zero()
        elif op.kind == "mcz_if":
            if op.outcome is None or op.outcome >= len(coefficients):
                raise UnsupportedOperation("uninitialized HMR feedback")
            sign = algebra.product([state[q] for q in op.qubits])
            coefficients[op.outcome] = algebra.xor(coefficients[op.outcome], sign)
        else:
            raise UnsupportedOperation(f"outside sign/HMR grammar: {op.kind!r}")
        guard.check_time()
    return _State(tuple(state), phi0, tuple(coefficients))


def _kernel(algebra: Any, x: _State, y: _State, guard: Guard, pairs=None) -> Any:
    """Exact coherences retained by an outcome-forgotten Kraus channel."""
    if len(x.outcome_coefficients) != len(y.outcome_coefficients):
        raise RuntimeError("the two input-coherence halves lost event identity")
    kernel = algebra.one()
    if pairs is None:
        pairs = _reduce_coefficients(algebra, x.outcome_coefficients,
                                     y.outcome_coefficients, guard)
    for g_x, g_y in pairs:
        guard.check_time()
        delta = algebra.xor(g_x, g_y)
        equality = algebra.xor(algebra.one(), delta)
        kernel = algebra.product((kernel, equality))
    return kernel


def _reduce_coefficients(algebra: Any, xs: tuple[Any, ...], ys: tuple[Any, ...],
                         guard: Guard) -> tuple[tuple[Any, Any], ...]:
    """GF(2) row reduction modulo constants, without exporting an ANF.

    Elementary row operations preserve equality of the coefficient vectors.
    The same operation is applied to both coherence halves; constants disappear
    because their value is the same on x and y. Roots never leave their owner.
    """
    return _reduction(algebra, xs, ys, guard).basis


def _reduction(algebra, xs, ys, guard):
    if len(xs) != len(ys):
        raise ValueError("coefficient frames differ")
    pivots = {}
    basis = []
    basis_combinations = []
    basis_constants = []
    reconstruction = []
    constants = []
    for row, (x, y) in enumerate(zip(xs, ys)):
        guard.check_time()
        constant = int(algebra.min_monomial(x) == 0)
        constants.append(constant)
        relation = 0
        source = 1 << row
        source_constant = constant
        if constant:
            x, y = algebra.xor(x, algebra.one()), algebra.xor(y, algebra.one())
        while not algebra.is_zero(x):
            guard.check_time()
            pivot = algebra.min_monomial(x)
            if pivot is None:
                raise RuntimeError("nonzero coefficient lost its monomial")
            if pivot not in pivots:
                index = len(basis)
                pivots[pivot] = (x, y, index)
                basis.append((x, y))
                basis_combinations.append(source)
                basis_constants.append(source_constant)
                relation ^= 1 << index
                break
            old_x, old_y, index = pivots[pivot]
            relation ^= 1 << index
            source ^= basis_combinations[index]
            source_constant ^= basis_constants[index]
            x, y = algebra.xor(x, old_x), algebra.xor(y, old_y)
        if algebra.is_zero(x) and not algebra.is_zero(y):
            raise RuntimeError("coherence halves disagree under exact row operations")
        reconstruction.append(relation)
    record = CoefficientReductionRecord(tuple(basis_combinations), tuple(basis_constants),
                                         tuple(reconstruction), tuple(constants))
    return _CoefficientReduction(tuple(basis), tuple(reconstruction), tuple(constants), record)


def _scalar(program: PhaseProgram, assignment: int) -> tuple[int, int, tuple[int, ...]]:
    """Independent integer basis-state/event-coefficient interpreter for witnesses.

    Crucially, it computes sign debt coefficients without constructing ANFs or
    consulting the C/ZDD engine. It never enumerates measurement outcomes.
    """
    program.validate()
    if type(assignment) is not int or not 0 <= assignment < (1 << program.data):
        raise ValueError("data assignment outside declared width")
    bits = assignment  # ancillas are |0>
    phase = 0
    coefficients: list[int] = []
    for op in program.ops:
        if op.kind == "mcx":
            *controls, target = op.qubits
            if all(bits >> q & 1 for q in controls):
                bits ^= 1 << target
        elif op.kind == "mcz":
            phase ^= int(all(bits >> q & 1 for q in op.qubits))
        elif op.kind == "hmr":
            q = op.qubits[0]
            coefficients.append(bits >> q & 1)
            bits &= ~(1 << q)
        elif op.kind == "mcz_if":
            coefficients[op.outcome] ^= int(all(bits >> q & 1 for q in op.qubits))
        else:
            raise UnsupportedOperation(op.kind)
    return bits, phase, tuple(coefficients)


def _scalar_kernel(program: PhaseProgram, x: int, y: int) -> bool:
    gx = _scalar(program, x)[2]
    gy = _scalar(program, y)[2]
    return gx == gy


def _validate_programs(left, right, theorem, left_outputs, right_outputs):
    if type(left) is not PhaseProgram or type(right) is not PhaseProgram:
        raise TypeError("two PhaseProgram instances required")
    left.validate()
    right.validate()
    if left.data != right.data:
        raise ValueError("data widths must match")
    if theorem not in {"full_channel", "reduced_channel"}:
        raise ValueError("explicit full_channel or reduced_channel theorem required")
    if theorem == "full_channel":
        if left.ancillas != right.ancillas:
            raise ValueError("data and ancilla widths must match for full-channel equality")
        if left_outputs is not None or right_outputs is not None:
            raise ValueError("full_channel retains every output; mappings require reduced_channel")
        return tuple(range(left.width)), tuple(range(right.width))
    if left_outputs is None or right_outputs is None:
        raise ValueError("reduced_channel requires explicit left_outputs and right_outputs")
    for outputs, program in ((left_outputs, left), (right_outputs, right)):
        if type(outputs) is not tuple or any(type(q) is not int or not 0 <= q < program.width
                                            for q in outputs):
            raise ValueError("output mappings must be tuples of valid wires")
        if len(set(outputs)) != len(outputs):
            raise ValueError("output mappings must be injective")
    if len(left_outputs) != len(right_outputs):
        raise ValueError("observed output dimensions differ")
    return left_outputs, right_outputs


def _compile(program, algebra, domain, offset, guard):
    from .domains import FullCube
    with stage("outputs_x" if offset == 0 else "outputs_y"):
        inputs, legal = domain.symbolic(algebra, offset, guard)
        # The fused native loop accepts the ordinary input frame only.
        state = _symbolic(program, algebra, offset, guard,
                          None if isinstance(domain, FullCube) else inputs)
    return state, legal


def _other_half(program, algebra, domain, state, offset, guard):
    manager = getattr(algebra, "manager", None)
    rename_many = getattr(manager, "rename_many", None)
    if rename_many is not None:
        mapping = list(range(offset, 2 * offset)) + list(range(offset))
        # Zero-dimensional domains allocate one unused variable.
        if not offset:
            mapping = list(range(algebra.width))
        roots = state.outputs + (state.phase0,) + state.outcome_coefficients
        with stage("rename"):
            renamed = tuple(rename_many(roots, mapping))
        count = len(state.outputs)
        _, legal = domain.symbolic(algebra, offset, guard)
        return _State(renamed[:count], renamed[count], renamed[count + 1:]), legal
    return _compile(program, algebra, domain, offset, guard)


def _with_discarded(state, outputs):
    discarded = tuple(root for q, root in enumerate(state.outputs) if q not in outputs)
    return _State(state.outputs, state.phase0, state.outcome_coefficients + discarded)


def coherence_signature(program, x, y, outputs=None):
    """Independent scalar image: None is zero, otherwise (row, column, sign)."""
    if outputs is None:
        outputs = tuple(range(program.width))
    a, b = _scalar(program, x), _scalar(program, y)
    if a[2] != b[2]:
        return None
    discarded = tuple(q for q in range(program.width) if q not in outputs)
    if any((a[0] >> q & 1) != (b[0] >> q & 1) for q in discarded):
        return None
    def project(value):
        return sum((value >> q & 1) << j for j, q in enumerate(outputs))
    return project(a[0]), project(b[0]), a[1] ^ b[1]


def _diagonal_difference(left, right, algebra, domain, lx, rx, legal_x,
                         outputs_left, outputs_right, theorem, backend, guard):
    """Check diagonal images before allocating either y coherence half."""
    with stage("outputs_compare"):
        for index, (lq, rq) in enumerate(zip(outputs_left, outputs_right)):
            guard.check_time()
            difference = algebra.product((legal_x, algebra.xor(lx.outputs[lq], rx.outputs[rq])))
            if algebra.is_zero(difference):
                continue
            with stage("witness"):
                parameter = algebra.min_monomial(difference)
                if parameter is None:
                    raise RuntimeError("nonzero output difference has no witness")
                parameter &= (1 << domain.parameters) - 1
                x = domain.decode(parameter)
                if not domain.contains(x) or coherence_signature(left, x, x, outputs_left) == (
                        coherence_signature(right, x, x, outputs_right)):
                    raise RuntimeError("output witness fails independent scalar replay")
            guard.check_time()
            label = "full" if theorem == "full_channel" else "retained"
            stats = tuple((name, getattr(algebra.stats, name)) for name in
                          ("gates", "products", "conversions", "conversion_terms",
                           "conversion_seconds", "seconds"))
            return ChannelDecision(False, backend,
                                   "full_quantum_channel" if theorem == "full_channel" else
                                   "reduced_quantum_channel", f"{label} output wire {index} differs",
                                   _sha(left), _sha(right), left.measurements + right.measurements,
                                   "input", (x, x), statistics=stats)
    return None


def _compare_states(left, right, *, algebra, domain, lx, ly, legal_x, legal_y,
                    rx, ry, outputs_left, outputs_right, theorem, backend, guard):
    left_sha, right_sha = _sha(left), _sha(right)
    parameters = domain.parameters
    mask = (1 << parameters) - 1
    legal_pairs = algebra.product((legal_x, legal_y))
    lkernel_x = _with_discarded(lx, outputs_left)
    lkernel_y = _with_discarded(ly, outputs_left)
    rkernel_x = _with_discarded(rx, outputs_right)
    rkernel_y = _with_discarded(ry, outputs_right)
    before = len(lkernel_x.outcome_coefficients) + len(rkernel_x.outcome_coefficients)
    with stage("reduction"):
        left_basis = _reduction(algebra, lkernel_x.outcome_coefficients,
                                lkernel_y.outcome_coefficients, guard)
        right_basis = _reduction(algebra, rkernel_x.outcome_coefficients,
                                 rkernel_y.outcome_coefficients, guard)
        after = len(left_basis.basis) + len(right_basis.basis)
    with stage("diagnostics"):
        observe("zero_phase_final", int(algebra.is_zero(lx.phase0) and algebra.is_zero(rx.phase0)))
        observe("zero_coefficients_final", int(all(algebra.is_zero(c) for c in
                lx.outcome_coefficients + rx.outcome_coefficients)))
    decision_theorem = ("full_quantum_channel" if theorem == "full_channel"
                        else "reduced_quantum_channel")

    def result(equivalent, reason, kind=None, root=None):
        witness = None
        if root is not None:
            with stage("witness"):
                raw = algebra.min_monomial(root)
                if raw is None:
                    raise RuntimeError("nonzero channel difference has no witness")
                u, v = raw & mask, (raw >> parameters) & mask
                if kind == "input":
                    v = u
                x, y = domain.decode(u), domain.decode(v)
                if not domain.contains(x) or not domain.contains(y):
                    raise RuntimeError("symbolic witness escaped its coherent domain")
                if coherence_signature(left, x, y, outputs_left) == coherence_signature(
                        right, x, y, outputs_right):
                    raise RuntimeError("channel witness fails independent scalar replay")
                witness = (x, y)
        guard.check_time()
        if _sha(left) != left_sha or _sha(right) != right_sha:
            raise RuntimeError("mutable input programs changed during verification")
        stats = algebra.stats
        statistics = tuple((name, getattr(stats, name)) for name in
                           ("gates", "products", "conversions", "conversion_terms",
                            "conversion_seconds", "seconds"))
        statistics += (("node_count", algebra.node_count),)
        for name, value in statistics:
            observe(name, value)
        return ChannelDecision(equivalent, backend, decision_theorem, reason,
                               left_sha, right_sha, left.measurements + right.measurements,
                               kind, witness, before, after, statistics,
                               (left_basis.record, right_basis.record))

    # Diagonal images force equality of every retained output on the legal domain.
    for index, (lq, rq) in enumerate(zip(outputs_left, outputs_right)):
        guard.check_time()
        difference = algebra.product((legal_x, algebra.xor(lx.outputs[lq], rx.outputs[rq])))
        if not algebra.is_zero(difference):
            prefix = "full" if theorem == "full_channel" else "retained"
            return result(False, f"{prefix} output wire {index} differs", "input", difference)
    with stage("kernels"):
        kl = _kernel(algebra, lkernel_x, lkernel_y, guard, left_basis.basis)
        kr = _kernel(algebra, rkernel_x, rkernel_y, guard, right_basis.basis)
        mismatch = algebra.product((legal_pairs, algebra.xor(kl, kr)))
    if not algebra.is_zero(mismatch):
        return result(False, "outcome-dephasing kernels differ", "coherence", mismatch)
    with stage("phases"):
        phase_x = algebra.xor(lx.phase0, rx.phase0)
        phase_y = algebra.xor(ly.phase0, ry.phase0)
        mismatch = algebra.product((legal_pairs, kl, algebra.xor(phase_x, phase_y)))
    if not algebra.is_zero(mismatch):
        return result(False, "relative phase differs on retained coherence", "coherence", mismatch)
    return result(True, "all basis coherences match")


@session_scoped
def check_channel(left, right, *, backend="zdd", theorem="full_channel", domain=None,
                  left_outputs=None, right_outputs=None, budget=None,
                  max_events=10000, max_ops=100000):
    """Exact coherent-domain channel equality in the closed sign/HMR grammar.

    Reduced equality traces precisely the complement of the two explicit output
    mappings. Different ancilla widths are supported. Measurement records are
    forgotten; this theorem is not instrument equality.
    """
    from .domains import FullCube
    guard = Guard(budget)
    outputs_left, outputs_right = _validate_programs(left, right, theorem,
                                                    left_outputs, right_outputs)
    if backend not in {"zdd", "zdd-native", "zdd-native-wide"}:
        raise ValueError("explicit zdd, zdd-native or zdd-native-wide backend required")
    for name, limit in (("events", max_events), ("ops", max_ops)):
        if type(limit) is not int or limit < 1:
            raise ValueError("positive event and gate limits required")
        observed = max(p.measurements if name == "events" else len(p.ops)
                       for p in (left, right))
        if observed > limit:
            raise ResourceLimitExceeded(name, limit, observed)
    domain = FullCube(left.data) if domain is None else domain
    if domain.data != left.data:
        raise ValueError("domain data width differs from program")
    native_limit = getattr(BACKENDS.get(backend), "max_width", None)
    if native_limit is not None and 2 * domain.parameters > native_limit:
        raise ResourceLimitExceeded("native pair variables", native_limit, 2 * domain.parameters)
    algebra = make_algebra(backend, max(1, 2 * domain.parameters), budget)
    lx, legal_x = _compile(left, algebra, domain, 0, guard)
    if algebra.is_zero(legal_x):
        raise EmptyDomain("coherent input domain is empty")
    rx, _ = _compile(right, algebra, domain, 0, guard)
    diagonal = _diagonal_difference(left, right, algebra, domain, lx, rx, legal_x,
                                     outputs_left, outputs_right, theorem, backend, guard)
    if diagonal is not None:
        return diagonal
    ly, legal_y = _other_half(left, algebra, domain, lx, domain.parameters, guard)
    ry, _ = _other_half(right, algebra, domain, rx, domain.parameters, guard)
    return _compare_states(left, right, algebra=algebra, domain=domain, lx=lx, ly=ly,
                           legal_x=legal_x, legal_y=legal_y, rx=rx, ry=ry,
                           outputs_left=outputs_left, outputs_right=outputs_right,
                           theorem=theorem, backend=backend, guard=guard)


class EmptyDomain(ValueError):
    """An empty input domain cannot establish a nonvacuous theorem."""


@session_scoped
def check_full_channel(left, right, *, backend="zdd-native", budget=None,
                       max_events=10000, max_ops=100000):
    """Backward-compatible full-channel research entrypoint, now installed."""
    return check_channel(left, right, backend=backend, budget=budget,
                         max_events=max_events, max_ops=max_ops)
