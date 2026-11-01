"""Source-pinned, file-driven P0 for *coherent HMR* contextual substitutions.

This is NOT the classical P0 JSON theorem: every acceptance is proved by
the bounded coherent-channel/instrument transcript checker from PR #125,
then replayed against a frozen HybridProgram before any candidate is returned.
Input quantum data is arbitrary/coherent; only explicit ancillas are initially
|0>. Observed classical records require an instrument theorem.

Reports contain complete source/replacement streams, closed physical
contracts, exact hashes and operation weights. A saved positive verdict or
re-signed JSON is NEVER proof authority; replay re-runs the exact oracle.
The optional isolated CLI uses a fresh resource-limited subprocess.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from symq._io import atomic_write_text
from symq.experimental.hybrid import HOp, HybridProgram
from symq.experimental.serialization import program_from_dict, program_to_dict
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import FrozenHybridProgram, HybridFragment
from symq.labs.hybrid_substitution import (
    HybridWeights,
    apply_verified_hybrid_substitution,
    check_hybrid_substitution,
)
from symq.resources import Budget, Guard, ResourceLimitExceeded

REQUEST_KIND = "symq_hmr_contextual_request"
ARTIFACT_KIND = "symq_hmr_contextual_proof"
SCHEMA_VERSION = 1
MAX_BYTES = 2_000_000
MAX_OPS = 4_000
MAX_WIDTH = 128
MAX_LOCAL_WIDTH = 6
MAX_EVENTS = 8
MAX_BRANCHES = 256


def _read(path: Path) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("HMR input exceeds the 2 MB limit")
    return raw


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in pairs:
        if name in out:
            raise ValueError(f"duplicate JSON key {name!r}")
        out[name] = value
    return out


def _finite(value: str) -> Any:
    raise ValueError(f"nonfinite JSON constant {value!r} is not admissible")


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_finite)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("invalid UTF-8 or excessively nested JSON") from exc


def _object(value: Any, fields: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"closed JSON object requires exactly {sorted(fields)}")
    return value


def _indices(value: Any, label: str) -> tuple[int, ...]:
    if type(value) is not list or any(type(i) is not int for i in value):
        raise ValueError(f"{label} must be a list of integer wire indices")
    return tuple(value)


def _slots(value: Any, label: str) -> tuple[str, ...]:
    if type(value) is not list or any(type(s) is not str for s in value):
        raise ValueError(f"{label} must be a list of classical slot strings")
    return tuple(value)


def _bounds(value: Any, name: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 1..{maximum}")
    return value


def _seconds(value: Any) -> float:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not 0 < value <= 120):
        raise ValueError("timeout must be finite seconds in (0,120]")
    return float(value)


def _source(value: Any) -> HybridProgram:
    if type(value) is not dict or len(value.get("ops", [])) > MAX_OPS:
        raise ValueError("source must be a hybrid program with at most 4000 ops")
    program = program_from_dict(value)
    if type(program) is not HybridProgram or program.width > MAX_WIDTH:
        raise ValueError("HMR workflow accepts a HybridProgram of up to 128 wires")
    return program


def _fragment(value: Any) -> HybridFragment:
    fields = {"schema_version", "kind", "width", "classical_inputs", "ops"}
    doc = _object(value, fields)
    if doc["schema_version"] != SCHEMA_VERSION or type(doc["schema_version"]) is not int:
        raise ValueError("unsupported HMR fragment schema")
    if doc["kind"] != "hybrid_fragment":
        raise ValueError("HMR replacement must be a hybrid_fragment")
    width = _bounds(doc["width"], "fragment width", MAX_LOCAL_WIDTH)
    if type(doc["ops"]) is not list or len(doc["ops"]) > MAX_OPS:
        raise ValueError("replacement must contain <=4000 operations")
    classical_inputs = _slots(doc["classical_inputs"], "classical_inputs")
    operations = []
    for item in doc["ops"]:
        _object(item, {"kind", "wires", "slot", "condition", "source", "value"})
        if type(item["kind"]) is not str:
            raise ValueError("hybrid operation kind must be a string")
        ops_wires = _indices(item["wires"], "operation wires")
        operations.append(HOp(item["kind"], ops_wires, item["slot"],
                              item["condition"], item["source"], item["value"]))
    return HybridFragment(width, tuple(operations), classical_inputs)


def fragment_to_dict(value: HybridFragment) -> dict[str, Any]:
    if type(value) is not HybridFragment:
        raise TypeError("HybridFragment required")
    return {"schema_version": 1, "kind": "hybrid_fragment",
            "width": value.width, "classical_inputs": list(value.classical_inputs),
            "ops": [{"kind": op.kind, "wires": list(op.wires), "slot": op.slot,
                     "condition": op.condition, "source": op.source, "value": op.value}
                    for op in value.ops]}


def _contract(value: Any, width: int) -> dict[str, Any]:
    fields = {"span", "wires", "clean", "preserved", "discarded",
              "observed_slots", "discarded_global", "weights",
              "max_local_width", "max_events", "max_branches",
              "require_saving"}
    doc = _object(value, fields)
    span = _indices(doc["span"], "span")
    if len(span) != 2 or span[1] < span[0]:
        raise ValueError("span requires an ordered [start,stop) pair")
    wires = _indices(doc["wires"], "wires")
    clean = _indices(doc["clean"], "clean")
    preserved = _indices(doc["preserved"], "preserved")
    discarded = _indices(doc["discarded"], "discarded")
    discarded_global = _indices(doc["discarded_global"], "discarded_global")
    if type(doc["require_saving"]) is not bool:
        raise ValueError("require_saving must be Boolean")
    if (len(set(wires)) != len(wires) or any(w < 0 or w >= width for w in wires)
            or len(set(discarded_global)) != len(discarded_global)
            or any(w < 0 or w >= width for w in discarded_global)):
        raise ValueError("global wire map and discarded outputs must be distinct and in range")
    frame = (clean, preserved, discarded)
    if any(len(set(reg)) != len(reg) or any(w < 0 or w >= len(wires) for w in reg)
           for reg in frame):
        raise ValueError("local frame indices must be unique and in range")
    raw_weights = _object(doc["weights"], {"unit", "by_kind"})
    pairs = raw_weights["by_kind"]
    if (type(pairs) is not list or any(type(x) is not list or len(x) != 2
                                      for x in pairs)):
        raise ValueError("weights require [[operation, nonnegative integer], ...]")
    weights = HybridWeights(tuple(tuple(x) for x in pairs), unit=raw_weights["unit"])
    return {
        "span": span, "wires": wires, "clean": clean, "preserved": preserved,
        "discarded": discarded, "discarded_global": discarded_global,
        "observed_slots": _slots(doc["observed_slots"], "observed_slots"),
        "weights": weights, "max_local_width": _bounds(
            doc["max_local_width"], "max_local_width", MAX_LOCAL_WIDTH),
        "max_events": _bounds(doc["max_events"], "max_events", MAX_EVENTS),
        "max_branches": _bounds(doc["max_branches"], "max_branches", MAX_BRANCHES),
        "require_saving": doc["require_saving"],
    }


def _contract_json(contract: dict[str, Any]) -> dict[str, Any]:
    def convert(key: str, value: Any) -> Any:
        if key == "weights":
            return {"unit": value.unit, "by_kind": [
                [name, weight] for name, weight in value.by_kind
            ]}
        return list(value) if isinstance(value, tuple) else value

    return {key: convert(key, value) for key, value in contract.items()}


def _mark(record: dict[str, Any]) -> dict[str, Any]:
    record["semantic_sha256"] = canonical_sha256(record)
    return record


def _prove(
    original: HybridProgram, replacement: HybridFragment,
    contract: dict[str, Any], guard: Guard, provenance: dict[str, str],
) -> dict[str, Any]:
    frozen = FrozenHybridProgram.freeze(original)
    guard.check_time()
    args = {k: v for k, v in contract.items() if k not in ("span", "require_saving")}
    result = check_hybrid_substitution(
        frozen.to_program(), contract["span"], replacement,
        budget=guard.inherited_budget(), **args,
    )
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "kind": ARTIFACT_KIND,
        "inputs": {
            "source": program_to_dict(frozen.to_program()),
            "replacement": fragment_to_dict(replacement),
            "contract": _contract_json(contract),
        },
        "file_provenance": provenance,
        "result": result.to_dict(),
        "application_status": "unproved",
        "candidate": None,
    }
    guard.check_time()
    if result.equivalent:
        if contract["require_saving"] and result.cost.weighted_delta >= 0:
            record["application_status"] = "cost_policy_refused"
        else:
            # Replay reads the exact weights from the typed receipt.
            # Unlike the initial check, its API does not accept weights=.
            apply_args = {key: value for key, value in args.items() if key != "weights"}
            applied = apply_verified_hybrid_substitution(
                result, frozen.to_program(), contract["span"], replacement,
                budget=guard.inherited_budget(), **apply_args,
            )
            if not applied.proof.equivalent:
                raise ValueError("coherent proof replay did not validate the same contract")
            record["result"] = applied.proof.to_dict()
            record["candidate"] = program_to_dict(applied.candidate.to_program())
            record["application_status"] = "applied_after_reproof"
    guard.check_time()
    return _mark(record)


def prove_request(
    path: str | Path, *, timeout_seconds: float = 30,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    guard = Guard(Budget(max_seconds=_seconds(timeout_seconds)))
    filename = Path(path)
    raw = _read(filename)
    request = _object(_json(raw), {"schema_version", "kind", "source",
                                  "replacement", "contract"})
    if request["schema_version"] != SCHEMA_VERSION or request["kind"] != REQUEST_KIND:
        raise ValueError("unsupported HMR workflow request/version")
    targets = []
    for key in ("source", "replacement"):
        value = request[key]
        if type(value) is not str or not value or Path(value).is_absolute():
            raise ValueError(f"{key} must be a relative filename")
        resolved = (filename.parent / value).resolve()
        if not resolved.is_relative_to(filename.parent.resolve()):
            raise ValueError("HMR input path escapes request directory")
        targets.append(resolved)
    if report_path is not None:
        target = Path(report_path).resolve()
        sidecar = target.with_name(target.name + ".sha256")
        if any(x in (filename.resolve(), *targets) for x in (target, sidecar)):
            raise ValueError("report/sidecar cannot overwrite the request or source files")
    source_raw, replacement_raw = (_read(t) for t in targets)
    source = _source(_json(source_raw))
    replacement = _fragment(_json(replacement_raw))
    contract = _contract(request["contract"], source.width)
    if len(contract["wires"]) != replacement.width:
        raise ValueError("wires must map the complete local replacement frame")
    guard.check_time()
    return _prove(source, replacement, contract, guard, {
        "request_sha256": hashlib.sha256(raw).hexdigest(),
        "source_file_sha256": hashlib.sha256(source_raw).hexdigest(),
        "replacement_file_sha256": hashlib.sha256(replacement_raw).hexdigest(),
    })


def _validate_receipt(artifact: Any) -> dict:
    if (type(artifact) is not dict
            or type(artifact.get("semantic_sha256")) is not str):
        raise ValueError("HMR report lacks a semantic SHA-256")
    expected = canonical_sha256(
        {name: value for name, value in artifact.items()
         if name != "semantic_sha256"}
    )
    if expected != artifact["semantic_sha256"]:
        raise ValueError("HMR report semantic SHA-256 mismatch")
    if artifact.get("kind") != ARTIFACT_KIND or artifact.get("schema_version") != 1:
        raise ValueError("unsupported HMR proof artifact type")
    return artifact


def replay_report(artifact: dict, *, timeout_seconds: float = 30) -> dict:
    saved = _validate_receipt(artifact)
    source = _source(saved["inputs"]["source"])
    replacement = _fragment(saved["inputs"]["replacement"])
    contract = _contract(saved["inputs"]["contract"], source.width)
    fresh = _prove(
        source, replacement, contract,
        Guard(Budget(max_seconds=_seconds(timeout_seconds))),
        saved["file_provenance"],
    )
    before = saved["result"]
    if type(before) is not dict or before.get("outcome") in ("inconclusive", "unsupported"):
        raise ValueError("non-decisive HMR result has no replayable theorem")
    # Full value equality, not only outcome/contract hash; a forged or edited
    # report remains insufficient even when its public checksum is recomputed.
    if (canonical_sha256(before) != canonical_sha256(fresh["result"])
            or saved.get("candidate") != fresh["candidate"]
            or saved.get("application_status") != fresh["application_status"]):
        raise ValueError("fresh coherent proof or applied stream differs from saved report")
    return fresh


def _save(path: Path, report: dict) -> None:
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    atomic_write_text(path, raw)
    atomic_write_text(path.with_name(path.name + ".sha256"),
                      hashlib.sha256(raw.encode("utf-8")).hexdigest() + "\n")


def _load_report(path: Path) -> dict:
    raw = _read(path)
    digest = path.with_name(path.name + ".sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("HMR report SHA-256 sidecar mismatch")
    return _validate_receipt(_json(raw))


def _child_prove(path: str, seconds: float) -> dict:
    return prove_request(path, timeout_seconds=seconds)


def _child_replay(record: dict, seconds: float) -> dict:
    return replay_report(record, timeout_seconds=seconds)


def _isolated(function, *arguments, seconds: float, memory_mib: int) -> dict:
    from symq.experimental.execution import HardLimits, run_isolated

    limits = HardLimits(wall_seconds=seconds, cpu_seconds=seconds,
                        memory_bytes=memory_mib * 1024 * 1024)
    outcome = run_isolated(function, *arguments, limits=limits)
    if outcome.status == "completed":
        if type(outcome.value) is not dict:
            raise ValueError("isolated HMR worker did not return a typed report")
        return outcome.value
    if outcome.status in ("inconclusive", "unsupported"):
        raise ResourceLimitExceeded("isolated HMR worker", seconds, outcome.wall_seconds,
                                    outcome.reason)
    raise RuntimeError("isolated HMR worker: " + outcome.reason)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parsers = parser.add_subparsers(dest="command", required=True)
    verify = parsers.add_parser("verify", help="import, prove channel and save a pinned report")
    verify.add_argument("request", type=Path)
    verify.add_argument("--report", type=Path, required=True)
    replay = parsers.add_parser("replay", help="freshly recompute the saved coherent proof")
    replay.add_argument("report", type=Path)
    for child in (verify, replay):
        child.add_argument("--timeout", type=float, default=45.0)
        child.add_argument("--memory-mib", type=int, default=1024)
        child.add_argument("--no-isolate", action="store_true")
    args = parser.parse_args(argv)
    try:
        seconds = _seconds(args.timeout)
        if type(args.memory_mib) is not int or not 128 <= args.memory_mib <= 8192:
            raise ValueError("memory-mib must be an integer in 128..8192")
        if args.command == "verify":
            if args.no_isolate:
                report = prove_request(args.request, timeout_seconds=seconds,
                                       report_path=args.report)
            else:
                # Prevent file overwrites BEFORE invoking the child.
                path = args.request.resolve()
                raw = _json(_read(path))
                for target in (path, *(
                    (path.parent / raw[key]).resolve()
                    for key in ("source", "replacement")
                )):
                    if args.report.resolve() == target or (
                        args.report.resolve().with_name(args.report.name + ".sha256") == target
                    ):
                        raise ValueError("report would overwrite a workflow input")
                report = _isolated(
                    _child_prove, str(path), seconds, seconds=seconds,
                    memory_mib=args.memory_mib,
                )
            _save(args.report, report)
        else:
            saved = _load_report(args.report)
            report = (
                replay_report(saved, timeout_seconds=seconds) if args.no_isolate
                else _isolated(_child_replay, saved, seconds, seconds=seconds,
                               memory_mib=args.memory_mib)
            )
        status = report["application_status"]
        result = report["result"]
        print(json.dumps({
            "status": status, "outcome": result["outcome"],
            "coherences_checked": result["checked_pairs"],
            "weighted_delta": result["cost"]["weighted_delta"],
            "candidate_embedded": report["candidate"] is not None,
            "semantic_sha256": report["semantic_sha256"],
        }, indent=2, sort_keys=True))
        return (0 if status == "applied_after_reproof" else
                2 if result["outcome"] in ("unsupported", "inconclusive") else 1)
    except ResourceLimitExceeded as exc:
        print(f"symq HMR inconclusive: {exc}", file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print(f"symq HMR invalid: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
