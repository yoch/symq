"""Strict importer into the existing sign-phase/HMR semantics.

This is NOT a general quantum channel evaluator. No external dependencies.
Unknown instructions, dirty resets and outcome-controlled VALUE writes fail closed.
Each HMR creates a fresh event, independently of reusable classical slot names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from symq.circuit import UnsupportedOperation
from symq.phase import PhaseProgram
from symq.resources import Budget, Guard, session_scoped

# Adapted from yoch/symq PR #88, exact head
# 2757ba0552d50c5718d4d4c9d357e0fd51a53fa2 (MIT).

_Q = re.compile(r"q(0|[1-9][0-9]*)\Z")
_B = re.compile(r"b(0|[1-9][0-9]*)\Z")
_ARITY = {"X": 1, "CX": 2, "CCX": 3, "SWAP": 2, "CSWAP": 3,
          "Z": 1, "CZ": 2, "CCZ": 3, "NEG": 0, "MCX": -1}
_UNKNOWN = -1


@dataclass(frozen=True)
class Parity:
    constant: int = 0
    events: int = 0

    def __post_init__(self):
        if type(self.constant) is not int or self.constant not in (0, 1):
            raise ValueError("parity constant must be a bit")
        if type(self.events) is not int or self.events < 0:
            raise ValueError("outcome mask must be nonnegative")

    def __xor__(self, other: Parity) -> Parity:
        if not isinstance(other, Parity):
            return NotImplemented
        return Parity(self.constant ^ other.constant, self.events ^ other.events)

    def invert(self) -> Parity:
        return Parity(self.constant ^ 1, self.events)


@dataclass
class ImportedPhaseStream:
    program: PhaseProgram
    instructions: int
    measurement_events: int
    resets_proved_zero: int
    final_classical: dict[str, Parity]


def _qid(token: str, width: int) -> int:
    match = _Q.fullmatch(token)
    if match is None or int(match.group(1)) >= width:
        raise UnsupportedOperation(f"invalid quantum wire {token!r}")
    return int(match.group(1))


def _bit(token: str) -> str:
    if _B.fullmatch(token) is None:
        raise UnsupportedOperation(f"invalid classical bit {token!r}")
    return token


def _resolve(token: str, table: dict[str, Parity]) -> Parity:
    negated = token.startswith("!")
    name = _bit(token[1:] if negated else token)
    if name not in table:
        raise UnsupportedOperation(f"undefined/future classical bit {name!r}")
    return table[name].invert() if negated else table[name]


def _sign(program: PhaseProgram, event: int | None) -> None:
    """X Z X Z = -I; conditional Z gives (-1)^event on every input."""
    program.x(0)
    if event is None:
        program.z(0)
    else:
        program.z_if(event, 0)
    program.x(0)
    if event is None:
        program.z(0)
    else:
        program.z_if(event, 0)


def _phase(program: PhaseProgram, kind: str, wires: tuple[int, ...], parity: Parity) -> None:
    if parity.constant:
        if kind == "NEG":
            _sign(program, None)
        else:
            program.mcz(*wires)
    mask = parity.events
    while mask:
        low = mask & -mask
        event = low.bit_length() - 1
        if kind == "NEG":
            _sign(program, event)
        else:
            program.mcz_if(event, *wires)
        mask ^= low


def _update(known: list[int], controls: tuple[int, ...], target: int) -> None:
    values = [known[q] for q in controls]
    if 0 in values:
        return
    if all(v == 1 for v in values):
        if known[target] != _UNKNOWN:
            known[target] ^= 1
    else:
        known[target] = _UNKNOWN


@session_scoped
def parse_phase_stream(text: str, *, data: int, ancillas: int = 0,
                       max_instructions: int = 20_000,
                       budget: Budget | None = None) -> ImportedPhaseStream:
    """Import a closed stream: value/phase gates, HMR, clean R, XOR outcome slots.

    Supports X/CX/CCX/MCX/SWAP/CSWAP; Z/CZ/CCZ/NEG with optional if bN/!bN;
    HMR qN bM; R qN only when statically known zero;
    BIT_STORE0/1 bN; BIT_INVERT bN [if bM]; OXOR b_dest b_source.
    Not general OpenQASM, general reset, or outcome-conditional X/CX.
    """
    if type(text) is not str:
        raise TypeError("stream must be text")
    if type(max_instructions) is not int or max_instructions < 1:
        raise ValueError("max_instructions must be positive")
    guard = Guard(budget)
    guard.check_time()
    if len(text) > max_instructions * 1024:
        raise UnsupportedOperation("phase-stream source size budget exceeded")
    program = PhaseProgram(data, ancillas)
    # A conservative proof of zero (0), one (1), or unknown (-1).
    known = [_UNKNOWN] * data + [0] * ancillas
    classical: dict[str, Parity] = {}
    count = resets = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        guard.check_time()
        tokens = raw.split()
        if not tokens or tokens[0].startswith("#"):
            continue
        count += 1
        if count > max_instructions:
            raise UnsupportedOperation("instruction budget exceeded")
        if tokens.count("if") > 1:
            raise UnsupportedOperation(f"line {number}: malformed condition")
        cond = None
        if "if" in tokens:
            at = tokens.index("if")
            if at != len(tokens) - 2:
                raise UnsupportedOperation(f"line {number}: invalid condition position")
            cond = tokens[-1]
            tokens = tokens[:at]
        op, *args = tokens
        try:
            if op == "HMR":
                if cond is not None or len(args) != 2:
                    raise UnsupportedOperation("HMR requires qN bM")
                q, dest = _qid(args[0], program.width), _bit(args[1])
                event = program.hmr(q)
                classical[dest] = Parity(events=1 << event)
                known[q] = 0
            elif op == "R":
                if cond is not None or len(args) != 1:
                    raise UnsupportedOperation("only unguarded reset of a known-zero wire")
                q = _qid(args[0], program.width)
                if known[q] != 0:
                    raise UnsupportedOperation("reset of an unproven-zero wire is a channel")
                resets += 1
            elif op in {"BIT_STORE0", "BIT_STORE1"}:
                if cond is not None or len(args) != 1:
                    raise UnsupportedOperation("bad BIT_STORE signature")
                classical[_bit(args[0])] = Parity(constant=int(op[-1]))
            elif op == "BIT_INVERT":
                if len(args) != 1:
                    raise UnsupportedOperation("BIT_INVERT needs one destination")
                dest = _bit(args[0])
                if dest not in classical:
                    raise UnsupportedOperation("uninitialized BIT_INVERT destination")
                classical[dest] = classical[dest] ^ (
                    _resolve(cond, classical) if cond else Parity(1))
            elif op == "OXOR":
                if cond is not None or len(args) != 2:
                    raise UnsupportedOperation("OXOR needs destination and source")
                dest, other = map(_bit, args)
                if dest not in classical or other not in classical:
                    raise UnsupportedOperation("OXOR uses undefined bit")
                classical[dest] = classical[dest] ^ classical[other]
            elif op in _ARITY:
                if (op == "MCX" and len(args) < 2) or (op != "MCX" and len(args) != _ARITY[op]):
                    raise UnsupportedOperation("incorrect gate arity")
                qs = tuple(_qid(a, program.width) for a in args)
                if len(set(qs)) != len(qs):
                    raise UnsupportedOperation("duplicate quantum wires")
                if op in {"Z", "CZ", "CCZ", "NEG"}:
                    _phase(program, op, qs,
                           _resolve(cond, classical) if cond else Parity(1))
                else:
                    if cond is not None:
                        raise UnsupportedOperation(
                            "outcome-conditional values require new channel semantics")
                    if op == "X":
                        program.x(qs[0])
                        _update(known, (), qs[0])
                    elif op in {"CX", "CCX", "MCX"}:
                        getattr(program, op.lower())(*qs)
                        _update(known, qs[:-1], qs[-1])
                    elif op == "SWAP":
                        a, b = qs
                        program.cx(a, b).cx(b, a).cx(a, b)
                        known[a], known[b] = known[b], known[a]
                    else:
                        c, a, b = qs
                        program.cx(b, a).ccx(c, a, b).cx(b, a)
                        if known[c] == 1:
                            known[a], known[b] = known[b], known[a]
                        elif known[c] != 0 and known[a] != known[b]:
                            known[a] = known[b] = _UNKNOWN
            else:
                raise UnsupportedOperation(f"out-of-scope opcode {op!r}")
        except (UnsupportedOperation, ValueError) as exc:
            raise UnsupportedOperation(f"line {number}: {exc}") from exc
    program.validate()
    guard.check_time()
    return ImportedPhaseStream(program, count, program.measurements, resets, dict(classical))


@session_scoped
def lower_phase_program(program, *, budget: Budget | None = None):
    """Lower only when outputs are outcome-free and resets have a zero proof.

    General Z measurements, dirty resets and guarded value updates retain their
    full CPTP meaning in HybridProgram and are explicitly refused here.
    """
    from symq.experimental.hybrid import HybridIR, HybridProgram
    guard = Guard(budget)
    guard.check_time()
    if type(program) is HybridIR:
        program = program.to_program()
    if type(program) is not HybridProgram:
        raise TypeError("HybridProgram or HybridIR required")
    program.validate()
    lines = []
    for op in program.ops:
        guard.check_time()
        if op.kind == "measure_z":
            raise UnsupportedOperation(f"{op.kind} has no phase-stream lowering")
        if op.kind == "store":
            line = f"BIT_STORE{op.value} {op.slot}"
        elif op.kind == "invert":
            line = f"BIT_INVERT {op.slot}"
        elif op.kind == "oxor":
            line = f"OXOR {op.slot} {op.source}"
        elif op.kind == "hmr":
            line = f"HMR q{op.wires[0]} {op.slot}"
        else:
            name = "R" if op.kind == "reset" else op.kind.upper()
            line = " ".join((name, *(f"q{q}" for q in op.wires)))
        if op.condition:
            line += f" if {op.condition}"
        lines.append(line)
    return parse_phase_stream("\n".join(lines), data=program.data,
                              ancillas=program.ancillas, budget=budget).program

