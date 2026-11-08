"""Bounded pure-bit facts and non-use reservations in complete pinned KMB sources.

This optional NumPy adapter proves a deliberately sufficient resource theorem:
an unconditional reset/HMR followed only by top-level X on a wire establishes
a pure computational constant. Other possible writes forget the fact. Initial
constants are explicit assumptions; missing writers never imply zero. Conditions
are overapproximated, not sampled. No allocator or global substitution is issued.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import stat
from dataclasses import asdict, dataclass
from pathlib import Path

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.serialization import parse_json
from symq.hashing import canonical_sha256
from symq.labs import kmb_window
from symq.labs.rewrite import ReceiptMismatch, call_budget
from symq.resources import Budget, VerificationSession

__all__ = ["FrontierLimits", "assess_kmb_resources", "replay_kmb_resources"]
_KIND = "symq_kmb_resource_frontier"
_SUPPORTED = set(kmb_window._OPS) - {0x13, 0x93, 7, 0x87, 0x47, 0xC7, 0x17, 0x97}


@dataclass(frozen=True)
class FrontierLimits:
    max_source_bytes: int = 2 * 1024**3
    max_source_ops: int = 100_000_000
    max_global_wires: int = 65_536
    max_observed_wires: int = 4096
    max_lease_ops: int = 20_000
    max_request_bytes: int = 200_000
    chunk_ops: int = 1 << 20

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.chunk_ops > 1 << 20:
            raise ValueError("chunk_ops must be <=1048576")


_LIMITS = FrontierLimits()


def _over(resource, value, limit):
    if value > limit:
        raise ResourceLimitExceeded(resource, limit, value)


def _request(request, source_pin, request_pin, limits):
    if type(request) is bytes:
        _over("request bytes", len(request), limits.max_request_bytes)
        request = parse_json(request)
    if type(request) is not dict:
        raise ValueError("closed JSON resource request required")
    data = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    _over("request bytes", len(data), limits.max_request_bytes)
    request = parse_json(data)
    if set(request) != {"kind", "schema_version", "source_file_sha256", "cut_op",
                        "lease_stop_op", "wires", "initial_constants"}:
        raise ValueError("resource request has missing or unknown fields")
    if (request["kind"] != _KIND or type(request["schema_version"]) is not int
            or request["schema_version"] != 1):
        raise ValueError("unsupported resource request schema")
    if canonical_sha256(request) != request_pin or request["source_file_sha256"] != source_pin:
        raise ReceiptMismatch("resource request differs from independent source/request pins")
    a, b = request["cut_op"], request["lease_stop_op"]
    if type(a) is not int or type(b) is not int or not 0 <= a <= b:
        raise ValueError("ordered nonnegative raw cut/lease coordinates required")
    _over("lease operations", b - a, limits.max_lease_ops)
    wires = request["wires"]
    if (type(wires) is not list or not wires or any(type(q) is not int or q < 0 for q in wires)
            or len(set(wires)) != len(wires)):
        raise ValueError("distinct nonnegative observed wires required")
    _over("observed wires", len(wires), limits.max_observed_wires)
    constants = request["initial_constants"]
    if (type(constants) is not list or any(type(p) is not list or len(p) != 2
            or type(p[0]) is not int or p[0] < 0 or type(p[1]) is not int or p[1] not in (0, 1)
            for p in constants) or len({p[0] for p in constants}) != len(constants)):
        raise ValueError("initial constants need unique nonnegative (wire, 0/1) pairs")
    return request


def _depths(np, types, raw, minimum):
    change = (types == 0x81).astype(np.int8) - (types == 1).astype(np.int8)
    levels = np.cumsum(change, dtype=np.int64) + raw
    minima = np.minimum(np.minimum.accumulate(levels), minimum)
    after = levels - np.minimum(minima, 0)
    before = np.empty_like(after)
    before[0] = raw - min(0, minimum)
    before[1:] = after[:-1]
    return before, int(levels[-1]), int(minima[-1])


def _scan(np, view, info, packets, request, guard, limits):
    width = info["num_qubits"]
    _over("global wires", width, limits.max_global_wires)
    if request["lease_stop_op"] > info["num_ops"]:
        raise ValueError("lease extends past complete source")
    if any(q >= width for q in request["wires"] + [p[0] for p in request["initial_constants"]]):
        raise ValueError("request wire outside complete source width")
    # Every state starts arbitrary. Constants restrict P; no external preparation is inferred.
    values = np.full(width, -1, dtype=np.int8)
    for q, bit in request["initial_constants"]:
        values[q] = bit
    anchors = np.full(width, -1, dtype=np.int64)
    flips = np.zeros(width, dtype=np.int64)
    counters = [0] * 7
    raw_depth = minimum = 0
    maximum_q, maximum_b = info["max_q_reg"], info["max_b_reg"]
    touches = {q: [] for q in request["wires"]}
    reads = 0

    def array(packet, offset, count, dtype):
        nonlocal reads
        size = count * (1 if dtype == "u1" else 4)
        reads += size
        begin = packets[packet] + offset * (1 if dtype == "u1" else 4)
        # Own bounded bytes, rather than retaining an exported mmap buffer in an exception.
        return np.frombuffer(view[begin:begin + size], dtype=dtype)

    seen = np.zeros(256, dtype=np.int64)
    for at in range(0, info["num_ops"], limits.chunk_ops):
        guard.check_time()
        n = min(limits.chunk_ops, info["num_ops"] - at)
        types = array(1, at, n, "u1")
        frequency = np.bincount(types, minlength=256)
        if any(frequency[c] for c in range(256) if c not in _SUPPORTED):
            raise UnsupportedOperation("complete source has unknown, Z_POW or debug instructions")
        seen += frequency
        depths, raw_depth, minimum = _depths(np, types, raw_depth, minimum)
        indices = np.arange(at, at + n, dtype=np.int64)
        barriers = np.full(width, -1, dtype=np.int64)
        x_wires, x_indices = [], []
        for arity, channels in ((1, (7,)), (2, (5, 6)), (3, (2, 3, 4))):
            selected = (types & 48) == 16 * arity
            ids, codes, depth = indices[selected], types[selected], depths[selected]
            count = len(ids)
            position = 3 - arity
            if counters[position] + count > info["counts"][position]:
                raise ValueError("KMB opcode/operand count contradiction")
            operands = [array(p, counters[position], count, "<u4") for p in channels]
            counters[position] += count
            if count:
                maximum_q = max(maximum_q, *(int(q.max()) for q in operands))
            if (any(np.any(q >= width) for q in operands)
                    or any(np.any(operands[i] == operands[j]) for i in range(arity) for j in range(i))):
                raise ValueError("aliased or out-of-range KMB qubits")
            base = codes & 127
            for target, wire_ids in enumerate(operands):
                lease = (ids >= request["cut_op"]) & (ids < request["lease_stop_op"])
                for q, i in zip(wire_ids[lease].tolist(), ids[lease].tolist()):
                    if q in touches:
                        touches[q].append(i)
                writes = (base == (17 if arity == 1 else 33 if arity == 2 else 49)) & (target == arity - 1)
                if arity == 1:
                    writes |= (base == 18) | (base == 80)
                elif arity == 2:
                    writes |= base == 34
                elif target > 0:
                    writes |= base == 50
                before_cut = ids < request["cut_op"]
                unconditional_x = (codes == 17) & (depth == 0) & before_cut if arity == 1 else np.zeros(count, dtype=bool)
                possible = writes & before_cut & ~unconditional_x
                np.maximum.at(barriers, wire_ids[possible], ids[possible])
                if arity == 1:
                    x_wires = wire_ids[unconditional_x]
                    x_indices = ids[unconditional_x]
        changed = barriers >= 0
        positions = barriers[changed] - at
        last_codes, last_depth = types[positions], depths[positions]
        values[changed] = np.where(((last_codes == 18) | (last_codes == 80)) & (last_depth == 0), 0, -1)
        anchors[changed] = barriers[changed]
        flips[changed] = 0
        if len(x_wires):
            after = x_indices > barriers[x_wires]
            toggles = np.bincount(x_wires[after], minlength=width)
            flips += toggles
            known = values >= 0
            values[known] ^= (toggles[known] & 1).astype(np.int8)
        for mask, packet, position in ((64, 8, 3), (128, 9, 4)):
            count = int(np.count_nonzero(types & mask))
            if counters[position] + count > info["counts"][position]:
                raise ValueError("classical operand count contradiction")
            bits = array(packet, counters[position], count, "<u4")
            if count:
                maximum_b = max(maximum_b, int(bits.max()))
            if np.any(bits >= info["num_bits"]):
                raise ValueError("classical operand outside header")
            counters[position] += count
        counters[5] += int(frequency[0x13] + frequency[0x93])
        counters[6] += int(frequency[6])
        guard.check_time()
    if tuple(counters) != info["counts"] or maximum_q + 1 != width or maximum_b + 1 != info["num_bits"]:
        raise ValueError("complete KMB counts/maxima contradict header")
    if raw_depth - min(0, minimum):
        raise UnsupportedOperation("complete source ends under a condition stack")
    facts = []
    for q in sorted(touches):
        guard.check_time()
        anchor = int(anchors[q])
        value = None if values[q] < 0 else int(values[q])
        facts.append({"wire": q, "value": value,
                      "cleanliness": "proved_zero" if value == 0 else "proved_one" if value == 1 else "unknown",
                      "anchor_raw_op": None if anchor < 0 else anchor,
                      "anchor_opcode": None if anchor < 0 else view[packets[1] + anchor],
                      "top_level_x_after_anchor": int(flips[q]),
                      "initial_value_is_supplied_assumption": anchor < 0 and value is not None,
                      "reservation": "proved_no_source_use" if not touches[q] else "source_interference",
                      "source_touches": sorted(touches[q])})
    return facts, {"vector_buffer_source_bytes": reads, "source_ops_validated": info["num_ops"],
                   "chunk_ops": limits.chunk_ops, "empty_pop_noop_count": -min(0, minimum)}


def _dependencies(np, guard):
    import symq.errors
    import symq.experimental.serialization
    import symq.hashing
    import symq.labs.rewrite
    import symq.resources

    paths = {"analyzer": Path(__file__), "binary_reader": Path(kmb_window.__file__)}
    for module in (symq.resources, symq.errors, symq.hashing,
                   symq.experimental.serialization, symq.labs.rewrite):
        paths[module.__name__] = Path(module.__file__)
    try:
        spec = importlib.util.find_spec("numpy._core._multiarray_umath")
    except ModuleNotFoundError:
        spec = None
    if spec is None:  # NumPy 1.x uses the older core module path.
        spec = importlib.util.find_spec("numpy.core._multiarray_umath")
    if spec is not None and spec.origin:
        paths["numpy_core"] = Path(spec.origin)
    hashes = {}
    for name, path in paths.items():
        guard.check_time()
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    # A version string and one extension do not bind Python dispatch wrappers or
    # bundled libraries. Bind the installed executable NumPy tree as well.
    root = Path(np.__file__).resolve().parent
    package_files = {}
    for directory in (root, root.parent / "numpy.libs"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            guard.check_time()
            if not path.is_file() or not (path.suffix == ".py" or any(
                    marker in path.name for marker in (".so", ".pyd", ".dll", ".dylib"))):
                continue
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    guard.check_time()
                    digest.update(chunk)
            package_files[path.relative_to(root.parent).as_posix()] = digest.hexdigest()
    if not package_files:
        raise UnsupportedOperation("NumPy executable package content is unavailable")
    return {"python": platform.python_version(), "numpy": np.__version__, "content_sha256": hashes,
            "numpy_executable_tree_sha256": canonical_sha256(package_files),
            "numpy_executable_file_count": len(package_files)}


def assess_kmb_resources(path: str | Path, request: dict | bytes, *, expected_source_sha256: str,
                         expected_request_sha256: str, limits: FrontierLimits = _LIMITS,
                         budget: Budget | None = None) -> dict:
    """Recompute quantum pure-constant and reservation facts, never authorize a rewrite."""
    kmb_window._pin(expected_source_sha256)
    kmb_window._pin(expected_request_sha256)
    if type(limits) is not FrontierLimits:
        raise TypeError("FrontierLimits required")
    limits.__post_init__()
    budget = call_budget(budget)
    result = {"kind": _KIND, "schema_version": 1, "source_file_sha256": expected_source_sha256,
              "request_sha256": expected_request_sha256, "status": "inconclusive",
              "facts": [], "available_zero_wires": [], "candidate_authorized": False}
    try:
        with VerificationSession(budget) as session:
            if any(getattr(session.budget, field) is not None for field in ("max_terms", "max_nodes", "max_bytes")):
                raise ValueError("resource frontier uses time and explicit source/chunk limits")
            document = _request(request, expected_source_sha256, expected_request_sha256, limits)
            try:
                import numpy as np
            except ImportError as error:
                raise UnsupportedOperation("install symq[source] for the NumPy resource analyzer") from error
            source = Path(path)
            if source.suffix.lower() != ".kmb":
                raise UnsupportedOperation("only canonical KMB v2 is supported")
            fd = os.open(source, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as stream:
                status = os.fstat(stream.fileno())
                if not stat.S_ISREG(status.st_mode) or status.st_size < 104:
                    raise UnsupportedOperation("a regular complete KMB source is required")
                _over("source snapshot bytes", status.st_size, limits.max_source_bytes)
                deadline = session.deadline if session.deadline is not None else float("inf")
                with kmb_window._private_snapshot(stream, status.st_size, deadline=deadline,
                                                  max_seconds=session.remaining_seconds() or 30) as (view, pin):
                    if pin != expected_source_sha256:
                        raise ReceiptMismatch("copied source differs from the independent file pin")
                    info, packets = kmb_window._layout(view, max_registers=100_000, max_register_entries=5_000_000,
                                                       max_ops=limits.max_source_ops, max_seconds_deadline=deadline)
                    if not info["num_ops"]:
                        raise UnsupportedOperation("nonempty source required")
                    facts, work = _scan(np, view, info, packets, document, session, limits)
                    dependencies = _dependencies(np, session)
                session.check_time()
                result.update(status="assessed", request=document, facts=facts,
                              available_zero_wires=[f["wire"] for f in facts if f["value"] == 0
                                                    and f["reservation"] == "proved_no_source_use"],
                              source_bytes=status.st_size, source_ops=info["num_ops"],
                              position_basis="zero_based_raw_KMB_including_INFO_TAG",
                              dependencies=dependencies, limits=asdict(limits), work=work,
                              initial_quantum_domain="arbitrary except explicit independent constants",
                              initial_classical_domain="arbitrary; SSA definition/use not certified",
                              theorem="pure_constant_from_unconditional_reset_or_input_and_top_level_X",
                              external_preparation_proved=False, allocation_proved=False,
                              cache_relations_proved=False, global_substitution_proved=False)
            session.check_time()
            return result
    except (ResourceLimitExceeded, UnsupportedOperation) as error:
        result.update(status="unsupported" if isinstance(error, UnsupportedOperation) else "inconclusive",
                      reason=str(error), facts=[], available_zero_wires=[])
        return result


def _same(value, expected, guard):
    guard.check_time()
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return value.keys() == expected.keys() and all(_same(value[k], v, guard) for k, v in expected.items())
    if type(expected) is list:
        return len(value) == len(expected) and all(_same(a, b, guard) for a, b in zip(value, expected))
    return bool(value == expected)


def replay_kmb_resources(path: str | Path, request, receipt, *, expected_source_sha256: str,
                         expected_request_sha256: str, limits: FrontierLimits = _LIMITS,
                         budget: Budget | None = None) -> dict:
    """Re-copy/hash/validate/scan; a stored cleanliness verdict has no authority."""
    budget = call_budget(budget)
    try:
        with VerificationSession(budget) as session:
            fresh = assess_kmb_resources(path, request, expected_source_sha256=expected_source_sha256,
                                         expected_request_sha256=expected_request_sha256,
                                         limits=limits, budget=session.remaining_budget())
            if fresh["status"] == "assessed" and not _same(receipt, fresh, session):
                raise ReceiptMismatch("stored resource facts differ from full fresh reconstruction")
            session.check_time()
            return fresh
    except ResourceLimitExceeded as error:
        return {"kind": _KIND, "schema_version": 1, "status": "inconclusive", "reason": str(error),
                "facts": [], "available_zero_wires": [], "candidate_authorized": False}
