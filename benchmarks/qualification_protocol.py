"""Frozen-source, task-separated comparison of exact reversible Boolean engines.

No timing here is a general performance claim. ``freeze`` must run after the
protocol and manifest are committed; ``run`` executes only that read-only copy.
The historical explored corpus is not reused as a blind holdout. Foreign tools
are optional and produce explicit unsupported rows when unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import resource
import selectors
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
SCHEMA = "symq/qualification/v1"
MANIFEST = ROOT / "benchmarks/qualification_manifest.json"
PHASES = ("input_materialization", "conversion", "setup", "compute", "compare",
          "witness", "witness_replay", "export", "public_api", "oracle_validation",
          "cleanup", "orchestration")
ALGEBRA_BACKENDS = {"sparse", "zdd", "zdd-native", "zdd-native-fused",
                    "polybori", "cudd-bdd", "cudd-zdd"}
THREAD_LIMITS = {name: "1" for name in (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS")}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _emit(kind: str, **value) -> None:
    print(json.dumps({"event": kind, **value}, sort_keys=True), flush=True)


def _gate(circuit, controls, target):
    if not controls:
        circuit.x(target)
    elif len(controls) == 1:
        circuit.cx(controls[0], target)
    elif len(controls) == 2:
        circuit.ccx(*controls, target)
    else:
        circuit.mcx(*controls, target)


def build_case(case: dict):
    """Two independently constructed full-input circuits, and a rare-input mutant.

    All wires are free inputs; no silently initialized scratch. Gaussian row
    elimination synthesizes the affine candidate. Truth-table minterms and
    Möbius coefficients independently synthesize a triangular shear. The
    increment candidate is a minterm expansion, not a copied ripple stream.
    """
    from symq import Circuit, Gate

    width, family = case["width"], case["family"]
    rng = random.Random(case["seed"])
    left, right = Circuit(width), Circuit(width)
    if family == "affine":
        matrix = [1 << q for q in range(width)]
        for _ in range(case["depth"]):
            control, target = rng.sample(range(width), 2)
            left.cx(control, target)
            matrix[target] ^= matrix[control]
        reduction = Circuit(width)
        for column in range(width):
            pivot = next(q for q in range(column, width) if matrix[q] >> column & 1)
            if pivot != column:
                for a, b in ((pivot, column), (column, pivot), (pivot, column)):
                    matrix[b] ^= matrix[a]
                    reduction.cx(a, b)
            for row in range(width):
                if row != column and matrix[row] >> column & 1:
                    matrix[row] ^= matrix[column]
                    reduction.cx(column, row)
        assert matrix == [1 << q for q in range(width)]
        right = reduction.inverse()
    elif family == "triangular_shear":
        # The final target is never used as a control, so arbitrary truth tables
        # define reversible shears without assuming any clean ancilla.
        controls, target = tuple(range(width - 1)), width - 1
        truth = [rng.randrange(2) for _ in range(1 << len(controls))]
        coefficients = list(truth)
        for bit in controls:
            for mask in range(len(coefficients)):
                if mask >> bit & 1:
                    coefficients[mask] ^= coefficients[mask ^ (1 << bit)]
        for mask, coefficient in enumerate(coefficients):
            if coefficient:
                _gate(left, tuple(q for q in controls if mask >> q & 1), target)
        for assignment, bit in enumerate(truth):
            if bit:
                negative = tuple(q for q in controls if not assignment >> q & 1)
                for q in negative:
                    right.x(q)
                _gate(right, controls, target)
                for q in reversed(negative):
                    right.x(q)
    elif family == "increment":
        for target in reversed(range(width)):
            _gate(left, tuple(range(target)), target)
        # Complement/decrement/complement is an independently derived integer
        # implementation, with a different physical gate stream and no ancilla.
        for q in range(width):
            right.x(q)
        for target in reversed(range(width)):
            legal = [x for x in range(1 << target)
                     if ((((x - 1) % (1 << (target + 1))) >> target) & 1) != ((x >> target) & 1)]
            for assignment in legal:
                negative = [q for q in range(target) if not assignment >> q & 1]
                for q in negative:
                    right.x(q)
                _gate(right, tuple(range(target)), target)
                for q in reversed(negative):
                    right.x(q)
        for q in range(width):
            right.x(q)
    elif family == "mixed_nonlinear":
        # Adverse cases are preregistered but not run in the short qualification.
        # The candidate is the same synthetic stream with a deliberately
        # adjacent cancelling pair; it is not independent compiler output.
        for _ in range(case["depth"]):
            arity = rng.choice((1, 2, 3))
            qubits = rng.sample(range(width), arity + 1)
            _gate(left, qubits[:-1], qubits[-1])
        right = Circuit(width, list(left.gates))
        a, b = rng.sample(range(width), 2)
        # Adjacent same-gate cancellation is explicitly synthetic, not an
        # independent optimizer pair or evidence on external compiler output.
        right.gates[0:0] = [Gate("cx", (a, b)), Gate("cx", (a, b))]
    else:
        raise ValueError(f"unknown family {family!r}")
    mutant = Circuit(width, list(right.gates))
    _gate(mutant, tuple(range(width - 1)), width - 1)
    return left, right, mutant


def scalar_run(circuit, value: int) -> int:
    """Independent gate interpreter, sharing no symbolic product/encoder code."""
    for gate in circuit.gates:
        controls = sum(1 << q for q in gate.qubits[:-1])
        if value & controls == controls:
            value ^= 1 << gate.qubits[-1]
    return value


def exhaustive_pair(left, right, *, max_width: int = 10) -> tuple[bool, int | None]:
    if left.width > max_width:
        raise ValueError("exhaustive oracle width limit exceeded")
    for value in range(1 << left.width):
        if scalar_run(left, value) != scalar_run(right, value):
            return False, value
    return True, None


def _source_files(root: Path) -> list[Path]:
    return sorted([*root.glob("src/symq/**/*.py"), root / "src/symq/backends/_zdd.c",
                   root / "tools/build_native.py", root / "pyproject.toml", root / "LICENSE",
                   *(root / "benchmarks" / name for name in (
                       "qualification_protocol.py", "qualification_report.py",
                       "qualification_manifest.json", "native_contract.py"))])


def verify_snapshot(root: Path) -> dict:
    frozen = json.loads((root / "FREEZE.json").read_text())
    for path, expected in frozen["source"]["files"].items():
        if file_hash(root / path) != expected:
            raise RuntimeError(f"frozen source changed: {path}")
    native = frozen["source"].get("native")
    if native:
        if file_hash(root / native["snapshot_module"]) != native["binary_sha256"]:
            raise RuntimeError("frozen native binary changed")
        if file_hash(root / native["snapshot_receipt"]) != native["receipt_sha256"]:
            raise RuntimeError("frozen native build receipt changed")
    return frozen


def freeze_snapshot(destination: Path, *, root: Path = ROOT) -> dict:
    """Materialize only committed sources, then attach the exact validated binary."""
    from native_contract import native_provenance

    root, destination = root.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError("freeze destination must not exist")
    command = ["git", "-C", str(root)]
    commit = subprocess.check_output([*command, "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output([*command, "diff", "--name-only", "HEAD"], text=True).strip():
        raise RuntimeError("commit all source changes before freezing")
    selected = [str(p.relative_to(root)) for p in _source_files(root)]
    tracked = set(subprocess.check_output([*command, "ls-files"], text=True).splitlines())
    if any(path not in tracked for path in selected):
        raise RuntimeError("qualification source files must be tracked in the frozen commit")
    native = native_provenance(root=root)
    destination.mkdir(parents=True)
    archive = destination / ".source.tar"
    subprocess.run([*command, "archive", "--format=tar", "--output", str(archive), commit,
                    *selected], check=True)
    with tarfile.open(archive) as handle:
        # Trusted paths are chosen from git ls-files above, not uploaded data.
        handle.extractall(destination)
    archive.unlink()
    # The native helper validates the build receipt against _zdd.c and binary.
    module = root / native["module"]
    receipt = Path(str(module) + ".build.json")
    target = destination / "src/symq/backends" / module.name
    shutil.copy2(module, target)
    shutil.copy2(receipt, Path(str(target) + ".build.json"))
    native = {**native, "snapshot_module": str(target.relative_to(destination)),
              "snapshot_receipt": str(Path(str(target) + ".build.json").relative_to(destination)),
              "receipt_sha256": file_hash(receipt)}
    files = {str(p.relative_to(destination)): file_hash(p) for p in _source_files(destination)}
    frozen = {"schema": SCHEMA, "source": {"commit": commit,
              "tree": subprocess.check_output([*command, "rev-parse", "HEAD^{tree}"], text=True).strip(),
              "files": files, "native": native},
              "manifest_sha256": file_hash(destination / "benchmarks/qualification_manifest.json")}
    (destination / "FREEZE.json").write_text(json.dumps(frozen, indent=2) + "\n")
    for path in sorted(destination.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    destination.chmod(0o555)
    return verify_snapshot(destination)


def _backend(name, width, budget):
    from symq import external
    from symq.backends import BACKENDS, make_algebra
    if name in {"polybori", "cudd-bdd", "cudd-zdd"}:
        cls = external.EXTERNAL_BACKENDS.get(name)
        if cls is None:
            raise ImportError(external.UNAVAILABLE.get(name, "optional backend unavailable"))
        return make_algebra(cls, width, budget)
    actual = "zdd-native" if name == "zdd-native-fused" else name
    if actual not in BACKENDS:
        raise ImportError(f"optional {actual} backend unavailable")
    return make_algebra(actual, width, budget)


def _simulate(name, algebra, circuit, compiled=None):
    from symq.backends import Algebra
    if name == "zdd-native-fused":
        if compiled is None:
            return algebra.simulate(circuit)
        from native_contract import unpack_simulation
        result = algebra.manager.simulate([algebra.variable(q) for q in range(circuit.width)],
                                          *compiled)
        roots, peak, products = unpack_simulation(result, circuit.width)
        algebra.stats.observe_terms(peak)
        algebra.stats.products += products
        return roots
    return Algebra.simulate(algebra, circuit)


def _public_service(left, right, task, backend, limits):
    """Actual installed APIs, with no invented attribution of their internals."""
    from symq import Budget, check_equivalence, external, make_algebra, simulate
    from symq.backends import BACKENDS, Algebra

    budget = Budget(max_seconds=limits["verification_wall_seconds"],
                    max_terms=limits["max_terms"] if backend in ALGEBRA_BACKENDS else None,
                    max_nodes=limits["max_nodes"] if backend in ALGEBRA_BACKENDS else None)
    if backend in {"sat", "qcec"} and task in {"simulate", "anf_export"}:
        return {"status": "unsupported", "reason": "decision API cannot export outputs"}, None, None, None
    if backend == "sat":
        from symq.sat import check_equivalence_sat
        result = check_equivalence_sat(left, right, budget=budget)
        return {"computed": True, "equivalent": {"equivalent": True, "different": False}.get(result.outcome),
                "witness": result.witness, "witness_checked": result.witness_checked is True,
                "statistics": dict(vars(result))}, None, None, None
    if backend == "qcec":
        if external.qcec_check is None:
            raise ImportError(external.UNAVAILABLE.get("qcec", "QCEC unavailable"))
        result = external.qcec_check(left, right, timeout=limits["verification_wall_seconds"])
        return {"computed": True, "equivalent": result.equivalent,
                "statistics": {"verdict": result.verdict}}, None, None, None
    specification = backend
    if backend.startswith("zdd-native") and "zdd-native" not in BACKENDS:
        raise ImportError("optional native backend unavailable")
    if backend in {"cudd-bdd", "cudd-zdd", "polybori"}:
        specification = external.EXTERNAL_BACKENDS.get(backend)
        if specification is None:
            raise ImportError(external.UNAVAILABLE.get(backend, "optional backend unavailable"))
    elif backend == "zdd-native-fused":
        specification = "zdd-native"
    elif backend == "zdd-native":
        from symq.backends.zdd_native import NativeZDDAlgebra

        class MatchedNativeAlgebra(NativeZDDAlgebra):
            def simulate(self, circuit):
                return Algebra.simulate(self, circuit)

        specification = MatchedNativeAlgebra
    if task in {"equivalence", "counterexample"}:
        result = check_equivalence(left, right, backend=specification, budget=budget)
        return {"computed": True, "equivalent": result.equivalent,
                "witness": result.witness, "witness_checked": result.witness is not None,
                "statistics": dict(vars(result.stats))}, None, None, None
    algebra = make_algebra(specification, left.width, budget)
    outputs = simulate(left, algebra)
    exported = None
    if task == "anf_export":
        from symq.resources import VerificationSession
        with VerificationSession(Budget(max_seconds=limits["export_seconds"],
                                        max_terms=limits["max_terms"])):
            exported = [sorted(algebra.to_anf(value).terms) for value in outputs]
    return {"computed": True, "exported": exported is not None,
            "statistics": dict(vars(algebra.stats)),
            **({"export_sha256": digest(exported)} if exported is not None else {})}, algebra, outputs, exported


def _cpu_seconds() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def _service_seconds(phases, boundary):
    if boundary == "public_api_end_to_end":
        return phases["public_api"]
    service = sum(value or 0.0 for phase, value in phases.items()
                  if phase not in {"oracle_validation", "orchestration", "cleanup"})
    return service - phases["conversion"] if boundary == "precompiled_service" else service


def execute_trial(case: dict, task: str, backend: str, boundary: str, limits: dict,
                  *, checkpoint: Callable | None = None) -> dict:
    """One service call; independent validation is measured separately afterward."""
    from symq import Budget, ResourceLimitExceeded
    from symq.resources import VerificationSession

    phases = dict.fromkeys(PHASES, 0.0)
    if boundary == "public_api_end_to_end":
        for key in ("conversion", "setup", "compute", "compare", "witness", "witness_replay", "export"):
            phases[key] = None
    record = {"status": "inconclusive", "reason": "trial did not complete", "computed": False,
              "exported": False, "oracle_checked": False, "witness_checked": False,
              "equivalent": None, "witness": None, "phases": phases, "statistics": {},
              "expected_equivalent": task != "counterexample", "service_completed": False,
              "validation_status": "not_run", "failure_stage": None}
    started = time.perf_counter()
    cpu_started = _cpu_seconds()
    current_stage = "service"
    validation_started = validation_cpu_started = None
    algebra = None

    def stage(name: str, function: Callable):
        before = time.perf_counter()
        try:
            return function()
        finally:
            phases[name] += time.perf_counter() - before

    try:
        with VerificationSession(Budget(max_seconds=limits["verification_wall_seconds"])) as session:
            left, equal, mutant = stage("input_materialization", lambda: build_case(case))
            right = mutant if task == "counterexample" else equal
            if backend in {"sat", "qcec"} and task in {"simulate", "anf_export"}:
                record.update(status="unsupported", reason="decision engine cannot export symbolic outputs")
                return record
            if boundary == "public_api_end_to_end":
                update, algebra, outputs, exported = stage("public_api", lambda: _public_service(
                    left, right, task, backend, limits))
                record.update(update)
                if update.get("status") == "unsupported":
                    return record
            elif backend in ALGEBRA_BACKENDS:
                budget = Budget(max_seconds=limits["verification_wall_seconds"],
                                max_terms=limits["max_terms"], max_nodes=limits["max_nodes"])
                algebra = stage("setup", lambda: _backend(backend, left.width, budget))
                compiled = [None, None]
                if backend == "zdd-native-fused":
                    def compile_fused(circuit):
                        indices, offsets, targets = [], [0], []
                        for gate in circuit.gates:
                            indices.extend(gate.qubits[:-1])
                            offsets.append(len(indices))
                            targets.append(gate.qubits[-1])
                        return indices, offsets, targets
                    compiled = stage("conversion", lambda: [compile_fused(left),
                        compile_fused(right) if task in {"equivalence", "counterexample"} else None])
                outputs = stage("compute", lambda: _simulate(backend, algebra, left, compiled[0]))
                record["computed"] = True
                if task in {"equivalence", "counterexample"}:
                    candidate = stage("compute", lambda: _simulate(backend, algebra, right, compiled[1]))
                    difference = stage("compare", lambda: next(
                        (algebra.xor(a, b) for a, b in zip(outputs, candidate)
                         if not algebra.equal(a, b)), None))
                    record["equivalent"] = difference is None
                    if difference is not None:
                        def witness():
                            if backend.startswith("cudd-"):
                                assignment = algebra.manager.pick(difference)
                                if assignment is None:
                                    raise RuntimeError("different CUDD function has no witness")
                                return sum(1 << int(key[1:]) for key, bit in assignment.items() if bit)
                            return algebra.min_monomial(difference)
                        record["witness"] = stage("witness", witness)
                if task == "anf_export":
                    def export():
                        # A separate export deadline intersects the whole call.
                        with VerificationSession(Budget(max_seconds=limits["export_seconds"])):
                            return [sorted(algebra.to_anf(value).terms) for value in outputs]
                    exported = stage("export", export)
                    record["exported"] = True
                    record["export_sha256"] = digest(exported)
                record["statistics"] = dict(vars(algebra.stats))
            elif backend == "sat":
                from pysat.solvers import Solver

                from symq.sat import build_miter
                miter = stage("conversion", lambda: build_miter(left, right))
                miter.encoder.add(*miter.difference)
                solver = stage("setup", lambda: Solver(name="glucose42", bootstrap_with=miter.encoder.clauses))
                try:
                    answer = stage("compute", solver.solve)
                    record["computed"] = True
                    record["equivalent"] = not answer
                    if answer:
                        def witness():
                            positive = {v for v in solver.get_model() if v > 0}
                            return sum(1 << q for q, v in enumerate(miter.inputs) if v in positive)
                        record["witness"] = stage("witness", witness)
                    record["statistics"] = {"clauses": len(miter.encoder.clauses),
                                               "variables": miter.encoder.next_variable - 1,
                                               "solver": "glucose42"}
                finally:
                    stage("setup", solver.delete)
            elif backend == "qcec":
                from symq import external
                if external.qcec_check_computations is None:
                    raise ImportError(external.UNAVAILABLE.get("qcec", "QCEC unavailable"))
                pair = stage("conversion", lambda: (external.to_quantum_computation(left),
                                                      external.to_quantum_computation(right)))
                decision = stage("compute", lambda: external.qcec_check_computations(
                    *pair, timeout=limits["verification_wall_seconds"]))
                record.update(computed=True, equivalent=decision.equivalent)
                record["statistics"] = {"verdict": decision.verdict,
                                          "configuration": external.QCEC_CONFIGURATION}
                if decision.equivalent is False:
                    # QCEC's Python adapter exposes a verdict, no concrete input.
                    # Never credit the independent oracle's witness to QCEC.
                    record["reason"] = "QCEC proves difference but exposes no counterexample"
            else:
                raise ValueError(f"unknown backend {backend}")
            if record["witness"] is not None and not record["witness_checked"]:
                def replay():
                    value = record["witness"]
                    if left.run(value) == right.run(value):
                        raise RuntimeError("concrete counterexample replay failed")
                    return True
                record["witness_checked"] = stage("witness_replay", replay)
            session.check_time()
            if (task in {"equivalence", "counterexample"}
                    and record["equivalent"] is not None
                    and record["equivalent"] != record["expected_equivalent"]):
                raise RuntimeError("verdict violates preregistered expected label")
            if (task == "counterexample" and record["equivalent"] is False
                    and backend != "qcec" and not record["witness_checked"]):
                raise RuntimeError("counterexample service returned no replayed witness")
            record["status"] = "ok" if record["equivalent"] is not None or task in {
                "simulate", "anf_export"} else "inconclusive"
            if task == "counterexample" and backend == "qcec" and record["equivalent"] is False:
                record["status"] = "unsupported"
            if record["status"] == "ok":
                record["reason"] = "service completed within declared limits"
        # The service session must finish successfully before validation starts.
        # Optional exhaustive work gets a fresh, independent budget, never the
        # service's remaining duration or a manager guard still bound to it.
        record["service_wall_seconds"] = time.perf_counter() - started
        record["service_cpu_seconds"] = _cpu_seconds() - cpu_started
        if record["service_cpu_seconds"] >= limits["verification_cpu_seconds"]:
            raise ResourceLimitExceeded("cpu", limits["verification_cpu_seconds"],
                                        record["service_cpu_seconds"])
        record["service_completed"] = record["status"] == "ok"
        record["service_status"] = record["status"]
        record["service_seconds"] = _service_seconds(phases, boundary)
        saved = json.loads(json.dumps(record))
        record["service_checkpoint"] = saved
        if checkpoint is not None:
            checkpoint(saved)
        current_stage = "validation"
        if case["width"] <= 10:
            validation_started, validation_cpu_started = time.perf_counter(), _cpu_seconds()
            with VerificationSession(Budget(max_seconds=limits["validation_wall_seconds"],
                                            max_terms=limits["max_terms"],
                                            max_nodes=limits["max_nodes"])) as validation:
                if algebra is not None:
                    if hasattr(algebra, "bind_guard"):
                        algebra.bind_guard(validation.guard)
                    else:
                        algebra.guard = validation.guard

                def oracle():
                    expected, _ = exhaustive_pair(left, right)
                    if expected != record["expected_equivalent"]:
                        raise RuntimeError("generated pair violates preregistered expected label")
                    if task in {"equivalence", "counterexample"}:
                        if record["equivalent"] is not None and record["equivalent"] != expected:
                            raise RuntimeError("verdict disagrees with independent all-input oracle")
                        return record["equivalent"] is not None
                    terms = (exported if task == "anf_export" else
                             [sorted(algebra.to_anf(value).terms) for value in outputs])
                    for value in range(1 << left.width):
                        actual = sum((sum((value & mask) == mask for mask in poly) % 2) << q
                                     for q, poly in enumerate(terms))
                        if actual != scalar_run(left, value):
                            raise RuntimeError("symbolic output disagrees with independent scalar oracle")
                    return True
                checked = stage("oracle_validation", oracle)
                validation_cpu = _cpu_seconds() - validation_cpu_started
                if validation_cpu >= limits["validation_cpu_seconds"]:
                    raise ResourceLimitExceeded("cpu", limits["validation_cpu_seconds"], validation_cpu)
            record["oracle_checked"] = checked
            record["validation_status"] = "passed"
    except ImportError as error:
        record.update(status="unsupported" if current_stage == "service" else "error", reason=str(error),
                      failure_stage=current_stage)
    except MemoryError:
        record.update(status="oom" if current_stage == "service" else "inconclusive",
                      reason="worker address-space limit exhausted", failure_stage=current_stage)
        if current_stage == "validation":
            record["validation_status"] = "oom"
    except ResourceLimitExceeded as error:
        timed = error.resource in {"seconds", "cpu"}
        record.update(status="timeout" if current_stage == "service" and timed else "inconclusive",
                      reason=str(error), resource=error.resource, failure_stage=current_stage)
        if current_stage == "validation":
            record["validation_status"] = "timeout" if timed else "inconclusive"
    except Exception as error:  # noqa: BLE001 -- failure record, never a verdict
        record.update(status="error", reason=f"{type(error).__name__}: {error}", failure_stage=current_stage)
        if current_stage == "validation":
            record["validation_status"] = "error"
    finally:
        total = time.perf_counter() - started
        phases["orchestration"] = max(0.0, total - sum(value or 0.0 for value in phases.values()))
        record["trial_wall_seconds"] = total
        record.setdefault("service_wall_seconds", total)
        record.setdefault("service_cpu_seconds", _cpu_seconds() - cpu_started)
        record.setdefault("service_status", record["status"])
        record["validation_wall_seconds"] = (0.0 if validation_started is None else
                                               time.perf_counter() - validation_started)
        record["validation_cpu_seconds"] = (0.0 if validation_cpu_started is None else
                                              _cpu_seconds() - validation_cpu_started)
        record["service_seconds"] = _service_seconds(phases, boundary)
        record["boundary"] = boundary
    if record["status"] not in {"ok", "unsupported"}:
        record["equivalent"] = None
        record["witness"] = None
        record["witness_checked"] = False
    return record


def _rss_cpu(pid: int) -> tuple[int, float]:
    try:
        text = Path(f"/proc/{pid}/status").read_text()
        rss = next(int(line.split()[1]) * 1024 for line in text.splitlines() if line.startswith("VmRSS:"))
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        cpu = (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
        return rss, cpu
    except (OSError, StopIteration, ValueError):
        return 0, 0.0


def check_worker_diagnostics(record: dict, stderr: str) -> dict:
    """A successful JSON answer cannot hide a native teardown failure."""
    if stderr:
        record["stderr"] = stderr
    if any(marker in stderr for marker in (
            "Exception ignored in", "AssertionError:", "Fatal Python error:",
            "ERROR: AddressSanitizer", "runtime error:")):
        record.update(status="error", reason="worker native/cleanup diagnostic after service",
                      equivalent=None, witness=None, witness_checked=False, oracle_checked=False)
    return record


def _parent_failure(status, reason, resource_name, phase, checkpoint=None):
    record = {} if checkpoint is None else dict(checkpoint)
    if checkpoint is not None:
        record["service_checkpoint"] = checkpoint
    record.update(status=("error" if status == "error" else "inconclusive")
                  if phase == "validation" else status,
                  reason=reason, resource=resource_name, failure_stage=phase,
                  equivalent=None, witness=None, witness_checked=False, oracle_checked=False)
    if phase == "validation":
        record["validation_status"] = status
    return record


def _worker(request: dict) -> None:
    root = Path(request["snapshot"])
    resource.setrlimit(resource.RLIMIT_AS, (request["limits"]["address_space_bytes"],) * 2)
    frozen = verify_snapshot(root)
    imported = time.perf_counter()
    from native_contract import native_provenance

    from symq import external
    from symq.sat import versions as sat_versions

    loaded_native = native_provenance(root=root)
    if loaded_native["binary_sha256"] != frozen["source"]["native"]["binary_sha256"]:
        raise RuntimeError("worker loaded a different native binary")
    versions = {**external.versions(), **sat_versions(), "python": platform.python_version()}
    # Loading optional extensions is a separate whole-worker cost, not charged
    # to an invented per-verification solver timer.
    import_seconds = time.perf_counter() - imported
    usage = resource.getrusage(resource.RUSAGE_SELF)
    baseline_cpu = usage.ru_utime + usage.ru_stime
    cpu_limit = math.ceil(baseline_cpu + request["limits"]["verification_cpu_seconds"]
                          + request["limits"]["validation_cpu_seconds"])
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
    _emit("ready", baseline_cpu_seconds=baseline_cpu)

    def checkpoint(saved):
        _emit("service_complete", checkpoint=saved, cpu_seconds=_cpu_seconds())

    record = execute_trial(request["case"], request["task"], request["backend"],
                           request["boundary"], request["limits"], checkpoint=checkpoint)
    verify_snapshot(root)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    record.update(worker_import_seconds=import_seconds, versions=versions,
                  cpu_seconds=usage.ru_utime + usage.ru_stime,
                  verification_cpu_seconds=record["service_cpu_seconds"],
                  peak_rss_bytes=int(usage.ru_maxrss) * 1024,
                  thread_limits={name: int(os.environ[name]) for name in THREAD_LIMITS},
                  source_hash_checked=True, source_commit=frozen["source"]["commit"],
                  native_sha256=loaded_native["binary_sha256"], native_abi=loaded_native["abi"],
                  native_module=loaded_native["module"])
    _emit("result", result=record)


def run_cell(snapshot: Path, request: dict) -> dict:
    """Fresh process, bounded before and after its verification-ready checkpoint."""
    verify_snapshot(snapshot)
    start = time.perf_counter()
    process = subprocess.Popen([sys.executable, str(snapshot / "benchmarks/qualification_protocol.py"),
                                "worker"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True,
                               env={**os.environ, "PYTHONPATH": str(snapshot / "src"),
                                    "PYTHONDONTWRITEBYTECODE": "1", **THREAD_LIMITS}, text=False)
    process.stdin.write(json.dumps({**request, "snapshot": str(snapshot)}).encode())
    process.stdin.close()
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    output, errors = b"", b""
    record = None
    worker_deadline = start + request["limits"]["worker_wall_seconds"]
    deadline = worker_deadline
    baseline_cpu = None
    cpu_limit = request["limits"]["verification_cpu_seconds"]
    current_stage = "startup"
    completed_service = None
    observed_rss = 0
    failure = None
    try:
        while selector.get_map() or process.poll() is None:
            now = time.perf_counter()
            rss, cpu = _rss_cpu(process.pid)
            observed_rss = max(observed_rss, rss)
            if rss > request["limits"]["rss_bytes"]:
                failure = ("oom", "parent observed worker RSS limit", "rss")
            elif baseline_cpu is not None and cpu - baseline_cpu >= cpu_limit:
                failure = ("timeout", f"parent observed {current_stage} CPU limit", "cpu")
            elif now >= deadline:
                failure = ("timeout", f"parent {current_stage} wall deadline exhausted", "wall")
            if failure:
                break
            for event, _ in selector.select(min(0.01, max(0, deadline - now))):
                chunk = os.read(event.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(event.fileobj)
                    continue
                if event.fileobj is process.stderr:
                    errors = (errors + chunk)[-16000:]
                    continue
                output += chunk
                if len(output) > 262144:
                    failure = ("error", "worker response exceeds protocol size", "ipc")
                    break
                while b"\n" in output:
                    line, output = output.split(b"\n", 1)
                    message = json.loads(line)
                    if message.get("event") == "ready":
                        baseline_cpu = message["baseline_cpu_seconds"]
                        current_stage = "service"
                        deadline = min(worker_deadline, time.perf_counter() + request["limits"]["verification_wall_seconds"])
                    elif message.get("event") == "service_complete":
                        completed_service = message["checkpoint"]
                        baseline_cpu = message["cpu_seconds"]
                        current_stage = "validation"
                        cpu_limit = request["limits"]["validation_cpu_seconds"]
                        deadline = min(worker_deadline, time.perf_counter() + request["limits"]["validation_wall_seconds"])
                    elif message.get("event") == "result":
                        record = message["result"]
        if failure:
            record = _parent_failure(*failure, current_stage, completed_service)
        elif time.perf_counter() >= deadline:
            record = _parent_failure("timeout", "parent result handling exceeded wall deadline",
                                     "wall", current_stage, completed_service)
    except (ValueError, OSError) as error:
        record = _parent_failure("error", f"worker IPC: {error}", "ipc",
                                 current_stage, completed_service)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=1)
        selector.close()
        process.stdout.close()
        process.stderr.close()
    if record is None:
        status = "timeout" if process.returncode == -signal.SIGXCPU else (
            "killed" if process.returncode < 0 else "error")
        record = _parent_failure(status, "worker exited without result", "process",
                                 current_stage, completed_service)
    if process.returncode != 0 and record["status"] == "ok":
        record = _parent_failure("error", "worker failed after result", "process",
                                 current_stage, completed_service)
    record = check_worker_diagnostics(record, errors.decode(errors="replace"))
    if record.get("service_wall_seconds", 0) >= request["limits"]["verification_wall_seconds"]:
        record = _parent_failure("timeout", "service exceeded verification wall limit", "wall", "service")
    record.update(worker_wall_seconds=time.perf_counter() - start,
                  peak_rss_bytes=max(record.get("peak_rss_bytes", 0), observed_rss),
                  worker_exitcode=process.returncode)
    verify_snapshot(snapshot)
    return record


def run_campaign(snapshot: Path, output: Path, *, cases=None, backends=None, tasks=None,
                 boundaries=None, repetitions=15, qualification=False) -> dict:
    from qualification_report import summarise

    if repetitions < 15 and not qualification:
        raise ValueError("at least fifteen paired repetitions; use --qualification for schema smoke only")
    snapshot = snapshot.resolve()
    if output.resolve().is_relative_to(snapshot):
        raise ValueError("results must be outside the immutable source snapshot")
    frozen = verify_snapshot(snapshot)
    manifest = json.loads((snapshot / "benchmarks/qualification_manifest.json").read_text())
    cases = set(cases or (c["id"] for c in manifest["cases"] if c["qualification"]))
    backends, tasks = backends or manifest["backends"], tasks or manifest["tasks"]
    boundaries = boundaries or ["public_api_end_to_end"]
    if (not cases <= {c["id"] for c in manifest["cases"]}
            or not set(backends) <= set(manifest["backends"])
            or not set(tasks) <= set(manifest["tasks"])
            or not set(boundaries) <= set(manifest["boundaries"])):
        raise ValueError("selection must come from the frozen manifest")
    result = {"schema": SCHEMA, **frozen, "limits": manifest["limits"],
              "environment": {"python": sys.version, "platform": platform.platform(),
                              "cpu_affinity": sorted(os.sched_getaffinity(0)),
                              "thread_limits": {name: int(value) for name, value in THREAD_LIMITS.items()}},
              "repetitions": repetitions, "qualification_only": qualification,
              "cases": manifest["cases"], "rows": [], "complete": False,
              "selection": {"cases": sorted(cases), "backends": backends,
                            "tasks": tasks, "boundaries": boundaries}}
    blocks = []
    for repetition in range(repetitions):
        for case in manifest["cases"]:
            for task in tasks:
                for boundary in boundaries:
                    block = list(backends)
                    random.Random(manifest["selection_seed"] + repetition + int(digest([case["id"], task, boundary])[:8], 16)).shuffle(block)
                    blocks.append([(case, task, boundary, backend, repetition) for backend in block])
    # Pair/block order, as well as backend order inside each pair, is randomized.
    random.Random(manifest["selection_seed"]).shuffle(blocks)
    jobs = [job for block in blocks for job in block]
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for case, task, boundary, backend, repetition in jobs:
            meta = {"case_id": case["id"], "family": case["family"], "split": case["split"],
                    "task": task, "backend": backend, "boundary": boundary, "repetition": repetition}
            row = ({"status": "not_run", "reason": "outside preregistered short qualification selection"}
                   if case["id"] not in cases else run_cell(snapshot, {
                       "case": case, "task": task, "backend": backend, "boundary": boundary,
                       "limits": manifest["limits"]}))
            result["rows"].append({**meta, **row})
            # Preserve partial measurements if a later invariant fails.
            output.write_text(json.dumps(result, indent=2) + "\n")
        verify_snapshot(snapshot)
        result["complete"] = True
    except Exception as error:
        result["aborted"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        result["report"] = summarise(result)
        output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--out", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--snapshot", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--cases", nargs="+")
    run.add_argument("--backends", nargs="+")
    run.add_argument("--tasks", nargs="+")
    run.add_argument("--boundaries", nargs="+")
    run.add_argument("--repetitions", type=int, default=15)
    run.add_argument("--qualification", action="store_true")
    sub.add_parser("worker")
    args = parser.parse_args()
    if args.command == "freeze":
        print(json.dumps(freeze_snapshot(args.out), indent=2))
    elif args.command == "worker":
        _worker(json.load(sys.stdin))
    else:
        kwargs = vars(args).copy()
        kwargs.pop("command")
        snapshot, output = kwargs.pop("snapshot"), kwargs.pop("out")
        result = run_campaign(snapshot, output, **kwargs)
        print(json.dumps(result["report"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
