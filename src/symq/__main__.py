"""Installed CLI: classical checks, experimental verification and environment diagnosis.

Exit codes: 0 equivalent (or success), 1 different, 2 inconclusive or unsupported, 3 usage or
input error.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path

from ._io import atomic_write_text
from .resources import Budget, ResourceLimitExceeded, VerificationSession

_ENGINES = {"native": "zdd-native", "native-wide": "zdd-native-wide",
            "native-blocks": "zdd-native-blocks", "python": "zdd"}


def _parser():
    parser = argparse.ArgumentParser(
        prog="symq", description="Exact reversible-circuit verification.",
        epilog="exit codes: 0 equivalent/success, 1 different, 2 inconclusive or unsupported, "
               "3 usage or input error")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    commands = parser.add_subparsers(dest="command", required=True)
    entry = commands.add_parser(
        "check", help="decide equivalence of two classical reversible circuits (QASM, .kmx or JSON)")
    entry.add_argument("left")
    entry.add_argument("right")
    entry.add_argument("--engine", default="auto",
                       help="backend name, 'sat', or 'auto' (linear for X/CX circuits, else the "
                            "native ZDD that holds the width when built, else zdd)")
    entry.add_argument("--order", choices=("auto", "identity", "reversed", "last_use"),
                       help="variable order of a ZDD engine (default: auto)")
    entry.add_argument("--observe", type=_wires, help="observed output wires, e.g. 0,1,3 (SAT)")
    entry.add_argument("--restore", type=_wires, default=(), help="wires that must be restored (SAT)")
    entry.add_argument("--json", action="store_true", help="print the verification record as JSON")
    _budget_arguments(entry)
    entry = commands.add_parser("anf", help="print the exact output ANFs of a classical circuit")
    entry.add_argument("circuit")
    entry.add_argument("--wire", type=int, action="append", help="only this output wire")
    entry.add_argument("--backend", default="zdd")
    entry.add_argument("--json", action="store_true")
    _budget_arguments(entry)
    entry = commands.add_parser("doctor", help="environment and optional toolchain report")
    entry.add_argument("--require-native", action="store_true",
                       help="exit with status 1 when the native C core cannot be loaded")
    entry.add_argument("--json", action="store_true",
                       help="print the machine-readable report (versions, ABI, source and binary SHA-256)")
    entry = commands.add_parser("inspect", help="inspect admissibility without a proof")
    entry.add_argument("program")
    entry.add_argument("--other")
    entry.add_argument("--contract")
    entry.add_argument("--json", action="store_true")
    for command in ("verify", "profile"):
        entry = commands.add_parser(command, help=f"{command} an experimental theorem")
        entry.add_argument("reference")
        entry.add_argument("candidate")
        entry.add_argument("--contract")
        entry.add_argument("--theorem")
        entry.add_argument("--engine")
        entry.add_argument("--report", help="self-contained JSON artifact")
        entry.add_argument("--html", help="standalone HTML profile")
        entry.add_argument("--isolate", action="store_true", default=command == "profile")
        entry.add_argument("--no-isolate", action="store_false", dest="isolate")
        entry.add_argument("--memory-mib", type=int, default=2048)
        _budget_arguments(entry)
    entry = commands.add_parser(
        "rewrite", help="prove a contextual rewrite request (experimental, no API promise)")
    entry.add_argument("request", help="symq_rewrite_request JSON naming source and replacement")
    entry.add_argument("--report", help="write the self-contained JSON report here")
    entry.add_argument("--engine", choices=("sat", "auto", "linear", "packed",
                                           "sparse", "zdd", "zdd-native"),
                       help="classical only; 'auto' uses full symbolic proof when safe, "
                            "SAT when contextual preconditions are present")
    entry.add_argument("--isolate", action="store_true",
                       help="run in a fresh process with hard wall-clock and memory limits")
    entry.add_argument("--memory-mib", type=int, default=2048)
    entry.add_argument("--timeout", type=float, default=30.0, help="seconds (default 30)")
    entry = commands.add_parser("locate",
        help="discover exact contiguous rewrite spans and injective wire maps (NOT a proof)")
    entry.add_argument("source", help="global source .json/.qasm/.kmx or hybrid program JSON")
    entry.add_argument("reference", help="original local circuit or hybrid_fragment JSON")
    entry.add_argument("--theorem", choices=("classical", "coherent"), required=True)
    entry.add_argument("--max-candidates", type=int, default=128)
    entry = commands.add_parser(
        "prepare-rewrite",
        help="lower one uniquely located local classical replacement into a proof request "
             "(no proof is performed)")
    entry.add_argument("source", help="global classical source QASM, .kmx or JSON")
    entry.add_argument("reference", help="original local classical block QASM, .kmx or JSON")
    entry.add_argument("replacement", help="candidate local classical block QASM, .kmx or JSON")
    entry.add_argument("--contract", required=True,
                       help="explicit classical cut contract JSON (use {} for unrestricted)")
    entry.add_argument("--weights", help="declared cost-weights JSON, optional")
    entry.add_argument("--engine", choices=("sat", "auto", "linear", "packed",
                                           "sparse", "zdd", "zdd-native"), default="sat")
    entry.add_argument("--require-saving", action="store_true",
                       help="later refuse an equivalent candidate without a strict cost saving")
    entry.add_argument("--output-dir", type=Path, required=True,
                       help="new directory for source.json, replacement.json and request.json")
    entry.add_argument("--max-candidates", type=int, default=128)
    entry = commands.add_parser("replay", help="replay witness or recompute equality")
    entry.add_argument("artifact")
    _budget_arguments(entry)
    return parser


def _version() -> str:
    from . import __version__

    return __version__


def _wires(text: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in text.split(",") if part.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected comma-separated wire indices, got {text!r}")


def _load_circuit(path: str):
    """A classical circuit from OpenQASM (strict reversible subset), kickmix ``.kmx`` or JSON.

    The JSON form is ``{"width": n, "gates": [["ccx", [0, 1, 2]], ...]}``.
    """
    from .circuit import load_circuit

    return load_circuit(path)


def _auto_engine(left, right) -> str:
    """The engine ``--engine auto`` picks: the affine backend for X/CX-only circuits, else the
    narrowest native ZDD core that holds the width, else the pure-Python ZDD (256 wires)."""
    from .backends import BACKENDS, has_native

    if all(len(gate.qubits) <= 2 for circuit in (left, right) for gate in circuit.gates):
        return "linear"
    width = max(left.width, right.width)
    if has_native() and width <= 64:
        return "zdd-native"
    if "zdd-native-wide" in BACKENDS and width <= 128:
        return "zdd-native-wide"
    return "zdd"


def _check(args):
    from .facade import verify
    from .sat import Contract

    left, right = _load_circuit(args.left), _load_circuit(args.right)
    engine = _ENGINES.get(args.engine, args.engine)
    if engine == "auto":
        engine = _auto_engine(left, right)
    budget = Budget(max_seconds=args.timeout, max_nodes=args.max_nodes, max_terms=args.max_terms)
    if args.observe is not None or args.restore:
        if engine != "sat":
            raise ValueError("--observe/--restore define a SAT contract: use --engine sat")
        contract = Contract(observed_outputs=args.observe, restored_wires=args.restore)
        budget = Budget(max_seconds=args.timeout)
        record = verify(left, right, theorem="classical_contract", engine="sat",
                        contract=contract, budget=budget)
    else:
        from .equivalence import order_option

        order = args.order
        if order_option(engine):
            order = order or "auto"
        elif order is not None:
            raise ValueError(f"--order applies to the ZDD engines, not {engine!r}")
        if engine == "sat":
            budget = Budget(max_seconds=args.timeout)
        record = verify(left, right, theorem="classical_full", engine=engine, budget=budget,
                        order=order)
    if args.json:
        _print_json({"schema_version": 1, "kind": "symq_classical_check", **asdict(record)})
    else:
        line = f"{record.outcome} ({record.theorem}, engine {record.engine})"
        if record.witness is not None:
            bits = "".join(str(record.witness >> wire & 1) for wire in range(left.width))
            line += f"\nwitness input: {record.witness} (wire 0 first: {bits})"
        if record.outcome != "equivalent":
            line += f"\nreason: {record.reason}"
        print(line)
    return {"equivalent": 0, "different": 1}.get(record.outcome, 2)


def _anf(args):
    from .backends import make_algebra, simulate

    circuit = _load_circuit(args.circuit)
    budget = Budget(max_seconds=args.timeout, max_nodes=args.max_nodes, max_terms=args.max_terms)
    algebra = make_algebra(args.backend, circuit.width, budget)
    outputs = simulate(circuit, algebra)
    wires = args.wire if args.wire else range(circuit.width)
    for wire in wires:
        if not 0 <= wire < circuit.width:
            raise ValueError(f"wire {wire} outside width {circuit.width}")
    polynomials = {wire: algebra.to_anf(outputs[wire]) for wire in wires}
    if args.json:
        _print_json({"schema_version": 1, "kind": "symq_anf", "width": circuit.width,
                     "outputs": {str(w): sorted(p.terms) for w, p in polynomials.items()}})
    else:
        for wire, polynomial in polynomials.items():
            print(f"y{wire} = {polynomial}")
    return 0


def _budget_arguments(parser):
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-nodes", type=int)
    parser.add_argument("--max-terms", type=int)


def _print_json(value):
    print(json.dumps(value, sort_keys=True, indent=2, allow_nan=False))


def _rewrite_cli_failure(outcome: str, reason: str, *, error_type: str | None = None):
    """Stable JSON envelope for every rewrite/replay runtime failure.

    This is a CLI status, NOT a saved proof or a claim of non-equivalence.
    Invalid input has its own outcome; timeouts never authorize a candidate.
    """
    data = {"schema_version": 1, "kind": "symq_rewrite_cli_result",
            "application": "not_applied",
            "result": {"outcome": outcome, "reason": reason}}
    if error_type:
        data["error_type"] = error_type
    _print_json(data)


def _rewrite_envelope(args) -> bool:
    """``symq rewrite``, and ``symq replay`` unless the artifact is a verification one."""
    return args.command == "rewrite" or (
        args.command == "replay" and getattr(args, "replay_kind", None) != "verification")


def _contract(args):
    from .experimental.contracts import VerificationContract
    from .experimental.serialization import load_contract
    theorem = args.theorem.replace("-", "_") if args.theorem else None
    engine = _ENGINES.get(args.engine, args.engine)
    if args.contract:
        contract = load_contract(args.contract)
        if theorem is not None and theorem != contract.theorem:
            raise ValueError("--theorem conflicts with the explicit contract")
        if engine is not None and engine != contract.backend:
            raise ValueError("--engine conflicts with the explicit contract")
        return contract
    if theorem is None or engine is None:
        raise ValueError("supply --contract or both --theorem and --engine")
    return VerificationContract(theorem=theorem, backend=engine)


def _inspect(args):
    from .experimental import inspect
    from .experimental.contracts import VerificationContract
    from .experimental.serialization import load_contract, load_program
    program = load_program(args.program)
    other = load_program(args.other) if args.other else None
    contracts = ((load_contract(args.contract),) if args.contract else
                 tuple(VerificationContract(backend=engine) for engine in
                       ("zdd", "zdd-native", "zdd-native-wide", "zdd-native-blocks")))
    reports = [asdict(inspect(program, contract=contract, other=other)) for contract in contracts]
    if args.json:
        _print_json({"schema_version": 1, "kind": "symq_capabilities", "engines": reports})
    else:
        print(f"{reports[0]['data']} coherent inputs; {reports[0]['pair_variables']} paired variables")
        for report in reports:
            status = "admissible" if report["supported"] else "unsupported"
            print(f"{report['backend']}: {status} — {report['reason']}")
    return 0


def _verify_inner(args, publication):
    from .experimental.execution import HardLimits, run_isolated, verification_job
    from .experimental.serialization import load_program, program_to_dict, save_json
    budget = Budget(max_seconds=args.timeout, max_nodes=args.max_nodes, max_terms=args.max_terms)
    with VerificationSession(budget) as session:
        contract = _contract(args)
        reference, candidate = load_program(args.reference), load_program(args.candidate)
        if args.isolate:
            isolated = run_isolated(
                verification_job, reference, candidate, contract, session.subprocess_budget(),
                args.command == "profile", session=session,
                limits=HardLimits(args.timeout, args.memory_mib * 1024**2))
            if isolated.status != "completed":
                _print_json({"outcome": isolated.status, "reason": isolated.reason})
                return 2
            report = isolated.value
            report["execution"] = {k: v for k, v in asdict(isolated).items() if k != "value"}
        else:
            report = verification_job(reference, candidate, contract, budget,
                                       args.command == "profile")
        artifact = {"schema_version": 1, "kind": "symq_verification",
                    "reference": program_to_dict(reference),
                    "candidate": program_to_dict(candidate), "contract": contract.to_dict(),
                    **report}
        publication["artifact"] = artifact
        session.check_time()
        if args.report:
            save_json(artifact, args.report)
        if args.html:
            if args.command != "profile":
                raise ValueError("--html requires profile")
            from html import escape
            atomic_write_text(
                args.html,
                "<!doctype html><meta charset='utf-8'><title>SymQ profile</title>"
                "<h1>SymQ experimental verification</h1><p>Engine decision; "
                "not an independent proof certificate.</p><pre>"
                + escape(json.dumps(artifact, indent=2, allow_nan=False)) + "</pre>",
                encoding="utf-8")
        session.check_time()
    _print_json(artifact)
    return {"equivalent": 0, "different": 1}.get(artifact["result"]["outcome"], 2)


def _verify(args):
    """Withdraw a decisive report if output generation exhausts the deadline."""
    if args.html and args.command != "profile":
        raise ValueError("--html requires profile")
    publication = {}
    try:
        return _verify_inner(args, publication)
    except ResourceLimitExceeded as error:
        artifact = publication.get("artifact")
        if artifact is not None:
            from .experimental.serialization import save_json
            artifact["result"].update(outcome="inconclusive", reason=str(error),
                                      witness=None, witness_kind=None, witness_checked=False,
                                      proof_kind="engine_decision")
            if args.report:
                save_json(artifact, args.report)
            if args.html:
                from html import escape
                atomic_write_text(args.html, "<!doctype html><meta charset='utf-8'>"
                                          "<h1>SymQ verification inconclusive</h1><pre>"
                                          + escape(str(error)) + "</pre>", encoding="utf-8")
        raise


def _locate(args):
    """Structural advice only: all local wires must be mapped, no implicit cut assumptions."""
    import hashlib

    from .experimental.serialization import parse_json, program_from_dict
    from .labs.rewrite_locator import locate_exact
    from .labs.rewrite_request import _read, fragment_from_dict

    source_bytes = _read(Path(args.source))
    reference_bytes = _read(Path(args.reference))
    if args.theorem == "classical":
        from .circuit import parse_circuit

        source = parse_circuit(source_bytes, args.source)
        reference = parse_circuit(reference_bytes, args.reference)
    else:
        from .experimental.hybrid import HybridProgram

        source = program_from_dict(parse_json(source_bytes))
        if type(source) is not HybridProgram:
            raise ValueError("coherent location requires a hybrid source program")
        reference = fragment_from_dict(parse_json(reference_bytes))
    locations = locate_exact(source, reference, max_candidates=args.max_candidates)
    locations["source_file_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    locations["reference_file_sha256"] = hashlib.sha256(reference_bytes).hexdigest()
    _print_json(locations)
    return 0 if locations["status"] == "unique" else 2


def _prepare_rewrite(args):
    """Versioned, fail-closed local-to-global lowering. Does not prove a rewrite."""
    import hashlib

    from .circuit import parse_circuit
    from .experimental.serialization import parse_json
    from .labs.rewrite_prepare import prepare_local_classical, write_prepared_rewrite
    from .labs.rewrite_request import _classical_contract, _read, _weights

    filenames = {
        "source": Path(args.source),
        "reference": Path(args.reference),
        "replacement": Path(args.replacement),
        "contract": Path(args.contract),
    }
    if args.weights:
        filenames["weights"] = Path(args.weights)
    originals = {name: _read(path) for name, path in filenames.items()}
    source = parse_circuit(originals["source"], args.source)
    reference = parse_circuit(originals["reference"], args.reference)
    candidate = parse_circuit(originals["replacement"], args.replacement)
    contract = _classical_contract(parse_json(originals["contract"]))
    weights = _weights(parse_json(originals["weights"])) if args.weights else None

    prepared = prepare_local_classical(
        source, reference, candidate, contract=contract, weights=weights,
        engine=args.engine, require_saving=args.require_saving,
        max_candidates=args.max_candidates,
    )
    if not prepared.ready:
        _print_json(prepared.to_dict())
        return 2
    record = write_prepared_rewrite(
        prepared, args.output_dir,
        file_sha256={
            name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()
        },
    )
    _print_json({**record, "directory": str(args.output_dir)})
    return 0


def _rewrite(args):
    from .experimental.execution import HardLimits, run_isolated
    from .experimental.serialization import save_json
    from .labs.rewrite_request import exit_code, load_request_files, rewrite_job

    budget = Budget(max_seconds=args.timeout)
    with VerificationSession(budget) as session:
        request, files, inputs = load_request_files(args.request)
        if args.engine is not None:
            if request.theorem != "classical":
                raise ValueError("--engine applies only to classical rewrites; "
                                 "coherent HMR has its own oracle")
            request = replace(request, engine=args.engine)
        if args.report and Path(args.report).resolve() in inputs:
            raise ValueError("--report must not overwrite the request or its input files")
        if args.isolate:
            isolated = run_isolated(rewrite_job, request, session.subprocess_budget(), files,
                                    session=session,
                                    limits=HardLimits(args.timeout, args.memory_mib * 1024**2))
            if isolated.status != "completed":
                _rewrite_cli_failure(isolated.status, isolated.reason)
                return 2
            report = isolated.value
        else:
            report = rewrite_job(request, session.remaining_budget(), files)
        if "input_error" in report:
            raise ValueError(report["input_error"])
        if args.isolate:
            report["provenance"]["execution"] = {k: v for k, v in asdict(isolated).items()
                                                 if k != "value"}
        session.check_time()
        if args.report:
            save_json(report, args.report)
    _print_json({"schema_version": 1, "kind": "symq_rewrite_cli_result",
                 **{key: report[key] for key in ("application", "result")}})
    return exit_code(report)


def _replay_rewrite(artifact, budget):
    from .labs.rewrite import ReceiptMismatch
    from .labs.rewrite_request import exit_code, replay_report

    try:
        with VerificationSession(budget) as session:
            report = replay_report(artifact, session.remaining_budget())
    except ReceiptMismatch as error:
        # An edited or contradicted report, distinct from malformed input; never authority.
        _rewrite_cli_failure("receipt_mismatch", str(error), error_type="ReceiptMismatch")
        return 3
    _print_json({"schema_version": 1, "kind": "symq_rewrite_cli_result",
                 "mode": "rewrite_recomputed", "replay": report["replay"],
                 "application": report["application"], "result": report["result"],
                 "provenance": report["provenance"]})
    return exit_code(report)


def _replay(args):
    from .experimental.serialization import load_json as _load

    artifact = _load(args.artifact)
    if type(artifact) is not dict:
        raise ValueError(f"{args.artifact}: a replay artifact is a JSON object")
    if artifact.get("kind") == "symq_rewrite":
        # The rewrite checkers refuse limits they cannot enforce rather than ignoring them.
        return _replay_rewrite(artifact, Budget(max_seconds=args.timeout,
                                                max_nodes=args.max_nodes,
                                                max_terms=args.max_terms))
    # Verification artifacts keep their established error contract (stderr), not the rewrite
    # JSON envelope.
    args.replay_kind = "verification"
    return _replay_verification(args, artifact)


def _replay_verification(args, artifact):
    from .experimental import replay, verify
    from .experimental.api import program_hash
    from .experimental.contracts import VerificationContract, VerificationResult
    from .experimental.serialization import program_from_dict
    budget = Budget(max_seconds=args.timeout, max_nodes=args.max_nodes, max_terms=args.max_terms)
    with VerificationSession(budget):
        if artifact.get("schema_version") != 1 or artifact.get("kind") != "symq_verification":
            raise ValueError("a version 1 self-contained symq_verification artifact is required")
        reference = program_from_dict(artifact["reference"])
        candidate = program_from_dict(artifact["candidate"])
        contract = VerificationContract.from_dict(artifact["contract"])
        fields = dict(artifact["result"])
        if fields.get("witness") is not None:
            fields["witness"] = tuple(fields["witness"])
        fields["statistics"] = tuple(tuple(pair) for pair in fields.get("statistics", ()))
        result = VerificationResult(**fields)
        if (result.left_sha256, result.right_sha256, result.contract_sha256) != (
                program_hash(reference), program_hash(candidate), contract.sha256):
            raise ValueError("artifact program or contract hash mismatch")
        if result.outcome == "different":
            checked = replay(result, reference, candidate, contract, budget=budget)
            mode = "witness_replayed"
        elif result.outcome == "equivalent":
            checked = verify(reference, candidate, contract, budget=budget)
            mode = "equality_recomputed"
        else:
            raise ValueError("artifact has no decisive claim to replay")
    _print_json({"mode": mode, "result": checked.to_dict()})
    return {"equivalent": 0, "different": 1}.get(checked.outcome, 2)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        from .doctor import doctor, report

        if args.json:
            data = report()
            _print_json(data)
            return 1 if args.require_native and not data["native"]["available"] else 0
        return doctor(require_native=args.require_native)
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "anf":
            return _anf(args)
        if args.command == "inspect":
            return _inspect(args)
        if args.command == "replay":
            return _replay(args)
        if args.command == "rewrite":
            return _rewrite(args)
        if args.command == "locate":
            return _locate(args)
        if args.command == "prepare-rewrite":
            return _prepare_rewrite(args)
        return _verify(args)
    except ResourceLimitExceeded as error:
        if _rewrite_envelope(args):
            _rewrite_cli_failure("inconclusive", str(error), error_type=type(error).__name__)
        elif args.command == "locate":
            _print_json({"schema_version": 1, "kind": "symq_rewrite_locations",
                         "status": "inconclusive", "matches": [], "reason": str(error)})
        elif args.command == "prepare-rewrite":
            _print_json({"schema_version": 1, "kind": "symq_rewrite_preparation",
                         "status": "inconclusive", "ready_for_proof": False,
                         "advisory_only": True, "reason": str(error)})
        else:
            _print_json({"outcome": "inconclusive", "reason": str(error)})
        return 2
    except (ValueError, TypeError, KeyError, OSError) as error:
        if _rewrite_envelope(args):
            _rewrite_cli_failure("invalid", str(error), error_type=type(error).__name__)
        elif args.command == "locate":
            _print_json({"schema_version": 1, "kind": "symq_rewrite_locations",
                         "status": "invalid", "matches": [], "reason": str(error)})
        elif args.command == "prepare-rewrite":
            _print_json({"schema_version": 1, "kind": "symq_rewrite_preparation",
                         "status": "invalid", "ready_for_proof": False,
                         "advisory_only": True, "reason": str(error)})
        else:
            print(f"symq: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
