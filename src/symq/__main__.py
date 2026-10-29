"""Installed CLI: explicit experimental verification and environment diagnosis."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .doctor import doctor
from .resources import Budget, ResourceLimitExceeded, VerificationSession

_ENGINES = {"native": "zdd-native", "native-wide": "zdd-native-wide",
            "native-blocks": "zdd-native-blocks", "python": "zdd"}


def _parser():
    parser = argparse.ArgumentParser(prog="symq")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="environment and optional toolchain report")
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
    entry = commands.add_parser("replay", help="replay witness or recompute equality")
    entry.add_argument("artifact")
    _budget_arguments(entry)
    return parser


def _budget_arguments(parser):
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-nodes", type=int)
    parser.add_argument("--max-terms", type=int)


def _print_json(value):
    print(json.dumps(value, sort_keys=True, indent=2, allow_nan=False))


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
                verification_job, reference, candidate, contract, session.remaining_budget(),
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
            Path(args.html).write_text(
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
                Path(args.html).write_text("<!doctype html><meta charset='utf-8'>"
                                          "<h1>SymQ verification inconclusive</h1><pre>"
                                          + escape(str(error)) + "</pre>", encoding="utf-8")
        raise


def _replay(args):
    from .experimental import replay, verify
    from .experimental.api import program_hash
    from .experimental.contracts import VerificationContract, VerificationResult
    from .experimental.serialization import load_json, program_from_dict
    budget = Budget(max_seconds=args.timeout, max_nodes=args.max_nodes, max_terms=args.max_terms)
    with VerificationSession(budget):
        artifact = load_json(args.artifact)
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
        return doctor()
    try:
        if args.command == "inspect":
            return _inspect(args)
        if args.command == "replay":
            return _replay(args)
        return _verify(args)
    except ResourceLimitExceeded as error:
        _print_json({"outcome": "inconclusive", "reason": str(error)})
        return 2
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(f"symq: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
