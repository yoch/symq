"""Matched-driver benchmark for the paper (issue #18, experiments E1, E2, E3).

``run.py`` drives every algebra through symq's ``Algebra`` contract, while ``zdd-native``
also has a fused C gate loop. This harness separates the two effects by running every
engine under *identical* drivers:

  <engine>/algebra       symq's generic ``Algebra.simulate`` (one Python call per gate, with
                         symq's guards and counters); for ``zdd-native`` the fused loop is
                         bypassed on purpose;
  <engine>/loop          the same minimal Python loop for every engine: no guard, no counter,
                         factors multiplied in gate order; only the two ring operations
                         differ (``mul``, ``add``);
  <engine>/loop-sorted   the same loop, factors sorted by monomial count (the order the fused
                         C loop uses); only for engines with a monomial count;
  zdd-native/fused       one C call for the whole gate list (the loop symq ships), fed
                         index arrays built outside the timer, like the loop's gate list;
  qcec                   MQT QCEC alternating checker: conversion, check on pre-built
                         computations and end-to-end, verdicts only.

Each repetition records separately: ``setup`` (manager and variables), ``compute`` (symbolic
simulation; both circuits for equiv/nonequiv), ``compare`` (output equality), ``witness``
(a distinguishing input, re-checked concretely) and ``end_to_end`` (the four together).
``extract`` (explicit monomials of every output) is timed once, after the repetitions,
together with the output fingerprint used to check that all modes agree.

Two cache regimes are measured in the same worker. *Cold* (``phases``): every run builds a
fresh manager, so no operation cache survives between runs; Sage caches PolyBoRi rings by
their arguments, so each PolyBoRi run gets a ring with fresh variable names. *Warm*
(``warm_phases``): one manager is reused for all runs after a filling run, which measures
re-verification with hot caches.

Memory: ``rss_growth_kib`` is the growth of the worker's peak RSS (``ru_maxrss``) across the
measured runs, so it includes native heaps that ``tracemalloc`` cannot see.

Usage:
  python benchmarks/matched.py --corpus blind --label matched-blind
  python benchmarks/matched.py --corpus qcec --label matched-qcec
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import operator
import os
import platform
import queue
import random
import resource
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from matched_report import write_report
from run import diff_patch, git, seed_for, tree_fingerprint

from symq import Budget, external
from symq.backends import Algebra, make_algebra
from symq.corpus import load_corpus, sha256_hex
from symq.generators import equivalent_variant, mutate

try:
    from sage.all__sagemath_brial import BooleanPolynomialRing
except ImportError:  # PolyBoRi modes then fail as worker errors, recorded per cell
    BooleanPolynomialRing = None

ROOT = Path(__file__).resolve().parent
CORPORA = {
    "qcec": ROOT / "corpus" / "qcec" / "MANIFEST.json",
    "blind": ROOT / "corpus" / "blind" / "MANIFEST.json",
}
WORKLOADS = ("simulate", "equiv", "nonequiv")
MODES = (
    "sparse/algebra",
    "zdd-python/algebra",
    "zdd-native/algebra",
    "zdd-native/loop",
    "zdd-native/loop-sorted",
    "zdd-native/fused",
    "polybori/algebra",
    "polybori/loop",
    "polybori/loop-sorted",
    "cudd-bdd/loop",
    "cudd-bdd-static/loop",
    "qcec",
)
EXTRACT_MAX_TERMS = 2_000_000
EXTRACT_MAX_SECONDS = 30.0


# --------------------------------------------------------------------------- engines


class Engine:
    """The two ring operations of one tool, plus setup, equality, witness and extraction.

    ``algebra`` is a symq ``Algebra`` over the same manager; it is used only outside the
    timed loop (extraction, witnesses) and by the ``/algebra`` driver.
    """

    sortable = True

    def __init__(self, width: int) -> None:
        self.algebra = self.make(width)
        self.state = [self.algebra.variable(i) for i in range(width)]

    def make(self, width: int) -> Algebra:
        raise NotImplementedError

    def equal(self, left, right) -> bool:
        return self.algebra.equal(left, right)

    def witness(self, left, right) -> int | None:
        return self.algebra.min_monomial(self.algebra.xor(left, right))

    def terms(self, value) -> int | None:
        return self.algebra.terms(value)


class NativeEngine(Engine):
    def make(self, width: int) -> Algebra:
        return make_algebra("zdd-native", width)

    def ops(self):
        manager = self.algebra.manager
        return manager.product, manager.xor, 1, manager.terms


class PythonZDDEngine(Engine):
    sortable = False

    def make(self, width: int) -> Algebra:
        return make_algebra("zdd", width)


class SparseEngine(Engine):
    sortable = False

    def make(self, width: int) -> Algebra:
        return make_algebra("sparse", width)


class PolyBoRiEngine(Engine):
    """Sage caches ``BooleanPolynomialRing`` by its arguments, so two algebras with the same
    width share one ring and one operation cache. Unique variable names give every engine a
    fresh ring, i.e. the same cold start as a new manager of the other tools."""

    created = itertools.count()

    def make(self, width: int) -> Algebra:
        algebra = external.EXTERNAL_BACKENDS["polybori"](width)
        algebra.ring = BooleanPolynomialRing(width, f"v{next(self.created)}_", order="lp")
        algebra._gens = algebra.ring.gens()
        return algebra

    def ops(self):
        return operator.mul, operator.add, self.algebra.one(), len


class CuddEngine(Engine):
    sortable = False
    reordering = True

    def make(self, width: int) -> Algebra:
        return external.EXTERNAL_BACKENDS["cudd-bdd"](width, reordering=self.reordering)

    def ops(self):
        manager = self.algebra.manager
        return operator.and_, partial(manager.apply, "xor"), manager.true, None

    def witness(self, left, right) -> int | None:
        """Any satisfying assignment of the difference (not of minimum degree)."""
        manager = self.algebra.manager
        difference = manager.apply("xor", left, right)
        assignment = manager.pick(difference)
        if assignment is None:
            return None
        return sum(1 << int(name[1:]) for name, value in assignment.items() if value)


class CuddStaticEngine(CuddEngine):
    reordering = False


ENGINES = {
    "sparse": SparseEngine,
    "zdd-python": PythonZDDEngine,
    "zdd-native": NativeEngine,
    "polybori": PolyBoRiEngine,
    "cudd-bdd": CuddEngine,
    "cudd-bdd-static": CuddStaticEngine,
}


def compile_gates(circuit) -> list[tuple[tuple[int, ...], int]]:
    return [(gate.qubits[:-1], gate.qubits[-1]) for gate in circuit.gates]


def compile_fused(circuit) -> tuple[list[int], list[int], list[int]]:
    """The arrays of the fused C loop, built outside the timer like the loop's gate list."""
    indices: list[int] = []
    offsets = [0]
    targets: list[int] = []
    for gate in circuit.gates:
        indices.extend(gate.qubits[:-1])
        offsets.append(len(indices))
        targets.append(gate.qubits[-1])
    return indices, offsets, targets


def compile_for(mode: str, circuit):
    return compile_fused(circuit) if mode.endswith("/fused") else compile_gates(circuit)


def run_loop(engine: Engine, gates, sort: bool) -> list:
    """The matched driver: identical for every engine, only ``mul`` and ``add`` differ."""
    mul, add, one, count = engine.ops()
    state = list(engine.state)
    for controls, target in gates:
        if not controls:
            state[target] = add(state[target], one)
            continue
        factors = [state[c] for c in controls]
        if sort and len(factors) > 1:
            factors.sort(key=count)
        product = factors[0]
        for factor in factors[1:]:
            product = mul(product, factor)
        state[target] = add(state[target], product)
    return state


def run_mode(mode: str, engine: Engine, circuit, gates) -> list:
    driver = mode.split("/", 1)[1]
    if driver == "algebra":
        return list(Algebra.simulate(engine.algebra, circuit))
    if driver == "fused":
        return fused_simulate(engine, circuit, gates)
    return run_loop(engine, gates, sort=driver == "loop-sorted")


def fused_simulate(engine: Engine, circuit, gates) -> list:
    """The shipped fused C loop, with the versioned result unpacked and checked.

    The native manager returns ``(roots, peak_terms, products)`` at ABI 4 and a flat list of
    root ids at ABI 3. Both are accepted, and both are checked against the circuit width, so a
    stale extension cannot silently produce a wrong number of outputs.
    """
    result = engine.algebra.manager.simulate(list(engine.state), *gates)
    if isinstance(result, tuple) and len(result) == 3 and isinstance(result[0], (list, tuple)):
        roots, peak_terms, products = result
        if peak_terms is not None:
            engine.algebra.stats.observe_terms(peak_terms)
        engine.algebra.stats.products += int(products)
    else:
        roots = result
    roots = list(roots)
    if len(roots) != circuit.width:
        raise RuntimeError(
            f"fused simulate returned {len(roots)} roots for a circuit of width "
            f"{circuit.width}; the loaded native extension does not match this harness")
    return roots


# --------------------------------------------------------------------------- worker


def prepare(circuit, name: str, workload: str):
    rng = random.Random(seed_for(name))
    if workload == "equiv":
        return equivalent_variant(circuit, rng, steps=len(circuit.gates))
    if workload == "nonequiv":
        return mutate(circuit, rng, kind="insert")[0]
    return None


def one_run(mode: str, circuit, other, gates, other_gates,
            engine: Engine | None = None) -> tuple[dict, Engine, list, dict]:
    """One verification. ``engine=None`` builds a fresh manager (cold caches, ``setup``
    timed); passing an engine reuses its manager and caches (warm, no setup)."""
    phases = {}
    started = time.perf_counter()
    if engine is None:
        engine = ENGINES[mode.split("/", 1)[0]](circuit.width)
        phases["setup"] = time.perf_counter() - started
    mark = time.perf_counter()
    outputs = run_mode(mode, engine, circuit, gates)
    others = run_mode(mode, engine, other, other_gates) if other is not None else None
    phases["compute"] = time.perf_counter() - mark
    verdict: dict = {}
    if others is not None:
        mark = time.perf_counter()
        differing = next((i for i, (a, b) in enumerate(zip(outputs, others))
                          if not engine.equal(a, b)), None)
        phases["compare"] = time.perf_counter() - mark
        mark = time.perf_counter()
        witness = (engine.witness(outputs[differing], others[differing])
                   if differing is not None else None)
        phases["witness"] = time.perf_counter() - mark
        verdict = {"equivalent": differing is None, "output": differing, "witness": witness}
    phases["end_to_end"] = time.perf_counter() - started
    return phases, engine, outputs, verdict


def fingerprint(engine: Engine, outputs: list) -> tuple[str | None, int | None, str | None]:
    algebra = engine.algebra
    algebra.guard = Budget(max_terms=EXTRACT_MAX_TERMS, max_seconds=EXTRACT_MAX_SECONDS).start()
    counts = [engine.terms(v) for v in outputs]
    if all(c is not None for c in counts) and sum(counts) > EXTRACT_MAX_TERMS:
        return None, sum(counts), "terms"
    try:
        digest = hashlib.sha256()
        total = 0
        for value in outputs:
            terms = sorted(algebra.to_anf(value).terms)
            total += len(terms)
            digest.update(",".join(map(str, terms)).encode())
            digest.update(b";")
    except Exception as error:  # noqa: BLE001 - budget or tool failure, recorded as such
        return None, None, type(error).__name__
    return digest.hexdigest(), total, None


def qcec_worker(cell: dict, circuit, other, record: dict) -> dict:
    if other is None:
        return {**record, "status": "not_applicable"}
    reps = cell["repetitions"]
    conversions, checks, end_to_end, verdicts = [], [], [], set()
    left = right = None
    for index in range(reps + 1):
        started = time.perf_counter()
        left = external.to_quantum_computation(circuit)
        right = external.to_quantum_computation(other)
        conversion = time.perf_counter() - started
        mark = time.perf_counter()
        result = external.qcec_check_computations(left, right, timeout=cell["timeout"] / 2)
        check = time.perf_counter() - mark
        if index:
            conversions.append(conversion)
            checks.append(check)
        verdicts.add(result.equivalent)
        if index == 0 and check > 1.0:
            reps = 3 if check < 10.0 else 1
        if index >= reps:
            break
    for _ in range(len(checks)):
        started = time.perf_counter()
        external.qcec_check(circuit, other, timeout=cell["timeout"] / 2)
        end_to_end.append(time.perf_counter() - started)
    expected = cell["workload"] == "equiv"
    status = ("inconclusive" if len(verdicts) > 1 or None in verdicts
              else "ok" if verdicts == {expected} else "wrong_verdict")
    return {**record, "status": status, "repetitions": len(checks),
            "phases": {"conversion": conversions, "compute": checks, "end_to_end": end_to_end},
            "equivalent": verdicts.pop() if len(verdicts) == 1 else None}


def worker(cell: dict) -> dict:
    if cell.get("pin") is not None and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {cell["pin"]})
    corpus = load_corpus(cell["manifest"])
    entry = next(e for e in corpus.entries if e.name == cell["circuit"])
    circuit = entry.load()
    other = prepare(circuit, entry.name, cell["workload"])
    record: dict = {}
    if cell["mode"] == "qcec":
        return qcec_worker(cell, circuit, other, record)
    if cell["workload"] == "simulate":
        other = None
    gates = compile_for(cell["mode"], circuit)
    other_gates = compile_for(cell["mode"], other) if other is not None else None
    baseline_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    first = one_run(cell["mode"], circuit, other, gates, other_gates)[0]
    reps = cell["repetitions"]
    if first["end_to_end"] > 10.0:
        reps = 1
    elif first["end_to_end"] > 1.0:
        reps = min(reps, 3)
    samples: dict[str, list[float]] = {}
    for _ in range(reps):
        phases, engine, outputs, verdict = one_run(cell["mode"], circuit, other, gates,
                                                   other_gates)
        for key, value in phases.items():
            samples.setdefault(key, []).append(value)
    warm: dict[str, list[float]] = {}
    if cell.get("warm", True) and first["end_to_end"] <= 10.0:
        reused = one_run(cell["mode"], circuit, other, gates, other_gates)[1]
        one_run(cell["mode"], circuit, other, gates, other_gates, reused)
        for _ in range(reps):
            phases = one_run(cell["mode"], circuit, other, gates, other_gates, reused)[0]
            for key, value in phases.items():
                warm.setdefault(key, []).append(value)
    record.update(status="ok", repetitions=reps, phases=samples, warm_phases=warm,
                  rss_baseline_kib=baseline_rss,
                  rss_growth_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                  - baseline_rss)
    if cell["mode"].startswith("zdd"):
        record["zdd_nodes"] = engine.algebra.node_count
    counts = [engine.terms(v) for v in outputs]
    if all(c is not None for c in counts):
        record["output_terms"] = sum(counts)
        record["max_output_terms"] = max(counts)
    if other is None:
        started = time.perf_counter()
        digest, total, failure = fingerprint(engine, outputs)
        record.update(extract_seconds=time.perf_counter() - started, fingerprint=digest,
                      extracted_terms=total, extract_failure=failure)
    else:
        witness = verdict["witness"]
        valid = witness is not None and circuit.run(witness) != other.run(witness)
        record.update(equivalent=verdict["equivalent"], output=verdict["output"],
                      witness=witness, witness_valid=valid if witness is not None else None,
                      fingerprint=f"{verdict['equivalent']}:{verdict['output']}")
        expected = cell["workload"] == "equiv"
        if verdict["equivalent"] != expected or (not expected and not valid):
            record["status"] = "wrong_verdict"
    return record


# --------------------------------------------------------------------------- driver


def environment(args, corpus, manifest: Path) -> dict:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    native = sorted((ROOT.parent / "src" / "symq" / "backends").glob("_zdd*.so"))
    comment = subprocess.run(["readelf", "-p", ".comment", str(native[0])], capture_output=True,
                             text=True, check=False).stdout if native else ""
    compiler = [line.split("]", 1)[1].strip() for line in comment.splitlines() if "]" in line]
    return {
        "started_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symq_commit": git("rev-parse", "HEAD"),
        "symq_dirty": dirty,
        "symq_tree_sha256": tree_fingerprint(),
        "symq_patch_sha256": (hashlib.sha256(diff_patch().encode()).hexdigest() if dirty
                              else ""),
        "native_extension_sha256": (sha256_hex(native[0].read_bytes()) if native else None),
        "native_source_sha256": sha256_hex(
            (ROOT.parent / "src" / "symq" / "backends" / "_zdd.c").read_bytes()),
        "compiler": compiler[0] if compiler else None,
        "compiler_source": ".comment section of the built extension (readelf -p)",
        "compiler_flags": "-O3 -std=c11 -fPIC -shared (tools/build_native.py)",
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_model": cpu,
        "cpu_count": os.cpu_count(),
        "corpus": args.corpus,
        "corpus_manifest_sha256": sha256_hex(manifest.read_bytes()),
        "corpus_source": corpus.manifest["source"],
        "external_versions": external.versions(),
        "qcec_configuration": external.QCEC_CONFIGURATION,
        "protocol": {
            "modes": args.modes, "workloads": args.workloads,
            "warmup": 1, "repetitions": args.repetitions,
            "adaptive_repetitions": "3 if the warmup exceeds 1 s, 1 if it exceeds 10 s",
            "cell_timeout_seconds": args.timeout, "pinned_cpus": args.pins,
            "parallel_workers": len(args.pins or [None]),
            "censoring": ("cells of one (family, workload, mode) run in increasing size; "
                          "after a timeout the larger ones are recorded as timeout_censored"),
            "order": (f"(family, workload, mode) chains shuffled with "
                      f"random.Random({args.order_seed})"),
            "timing": "time.perf_counter per phase; one fresh worker process per cell",
            "memory": "growth of ru_maxrss over the measured runs (includes native heaps)",
            "regimes": ("phases: cold, a fresh manager per run (PolyBoRi: a fresh ring); "
                        "warm_phases: one manager reused across runs after one filling run, "
                        "skipped when a cold run exceeds 10 s"),
            "extraction_budget": {"max_terms": EXTRACT_MAX_TERMS,
                                  "max_seconds": EXTRACT_MAX_SECONDS},
        },
        "command": sys.argv,
    }


def family(name: str) -> str:
    """Censoring chain: circuits that differ only in width (``rand_w_g_k`` by ``(g, k)``)."""
    parts = name.split("_")
    return "_".join([parts[0], *parts[2:]]) if parts[0] == "rand" else parts[0]


def run_cell(manifest: Path, entry, workload: str, mode: str, args, pin) -> dict:
    cell = {"manifest": str(manifest), "circuit": entry.name, "workload": workload,
            "mode": mode, "repetitions": args.repetitions, "timeout": args.timeout, "pin": pin}
    started = time.perf_counter()
    try:
        done = subprocess.run([sys.executable, __file__, "--worker", json.dumps(cell)],
                              capture_output=True, text=True, timeout=args.timeout,
                              check=False)
        outcome = (json.loads(done.stdout) if done.returncode == 0
                   else {"status": "error", "returncode": done.returncode,
                         "stderr": done.stderr[-2000:]})
    except subprocess.TimeoutExpired:
        outcome = {"status": "timeout", "limit": args.timeout}
    return {**outcome, "cell_wall_seconds": time.perf_counter() - started}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--corpus", choices=sorted(CORPORA), default="blind")
    parser.add_argument("--circuits", nargs="+", help="restrict to these circuit names")
    parser.add_argument("--modes", nargs="+", default=list(MODES), choices=MODES)
    parser.add_argument("--workloads", nargs="+", default=list(WORKLOADS), choices=WORKLOADS)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--pins", type=int, nargs="+",
                        help="one worker per listed CPU, each pinned to it")
    parser.add_argument("--order-seed", type=int, default=20261027)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--label", default="matched")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return 0

    manifest = CORPORA[args.corpus]
    corpus = load_corpus(manifest)
    problems = corpus.verify()
    if problems:
        raise SystemExit("corpus verification failed:\n" + "\n".join(problems))
    env = environment(args, corpus, manifest)
    if env["symq_dirty"] and not args.allow_dirty:
        raise SystemExit("tracked files are modified; commit first or pass --allow-dirty")
    stamp = env["started_utc"].replace("-", "").replace(":", "")
    target = args.out / f"{stamp}_{env['symq_commit'][:12]}_{args.label}"
    target.mkdir(parents=True, exist_ok=False)
    (target / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    if env["symq_dirty"]:
        (target / "working-tree.patch").write_text(diff_patch())

    chains: dict[tuple[str, str, str], list] = {}
    for entry in corpus.entries:
        if not entry.supported or (args.circuits and entry.name not in args.circuits):
            continue
        for workload in args.workloads:
            for mode in args.modes:
                chains.setdefault((family(entry.name), workload, mode), []).append(entry)
    order = list(chains.items())
    random.Random(args.order_seed).shuffle(order)
    total = sum(len(entries) for _, entries in order)
    pins = queue.Queue()
    for pin in args.pins or [None]:
        pins.put(pin)
    lock = threading.Lock()
    done_cells = itertools.count(1)
    sink = (target / "results.jsonl").open("w")

    def run_chain(item) -> None:
        (_, workload, mode), entries = item
        pin = pins.get()
        try:
            censored = False
            for entry in sorted(entries, key=lambda e: (e.width, e.gates, e.name)):
                base = {"circuit": entry.name, "split": entry.split, "width": entry.width,
                        "gates": entry.gates, "workload": workload, "mode": mode}
                if censored:
                    row = {**base, "status": "timeout_censored",
                           "reason": "a smaller circuit of the family timed out"}
                else:
                    row = {**base, **run_cell(manifest, entry, workload, mode, args, pin)}
                    censored = row["status"] == "timeout"
                with lock:
                    sink.write(json.dumps(row) + "\n")
                    sink.flush()
                    print(f"[{next(done_cells)}/{total}] cpu{pin} {entry.name:15s} "
                          f"{workload:9s} {mode:22s} {row['status']}", file=sys.stderr)
        finally:
            pins.put(pin)

    with ThreadPoolExecutor(max_workers=len(args.pins or [None])) as pool:
        list(pool.map(run_chain, order))
    sink.close()
    print(write_report(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
