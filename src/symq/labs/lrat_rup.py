"""Standalone, standard-library-only checker for an addition-only RUP subset of LRAT.

No SAT solver, clause search, SymQ semantics, unsafe deserialization or proof
producer is imported. Positive hints must be unit or conflicting in listed order.
RAT steps, deletions, duplicate/tautological clauses and extensions are refused.
This small Python kernel is independently testable, NOT formally machine-verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path


class InvalidProof(ValueError):
    """The closed syntax, binding or a claimed inference is invalid."""


class ProofLimit(Exception):
    """The requested bounded check did not finish; never a positive result."""


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 8_000_000
    max_variables: int = 200_000
    max_clauses: int = 500_000
    max_steps: int = 200_000
    max_visits: int = 20_000_000
    max_seconds: float = 10.0

    def validate(self) -> None:
        for value in (self.max_bytes, self.max_variables, self.max_clauses,
                      self.max_steps, self.max_visits):
            if type(value) is not int or value < 1:
                raise ValueError('proof limits must be positive exact integers')
        if (type(self.max_seconds) not in (int, float)
                or not math.isfinite(self.max_seconds) or self.max_seconds <= 0):
            raise ValueError('max_seconds must be finite and positive')


class Meter:
    def __init__(self, limits: Limits, deadline: float | None = None):
        if type(limits) is not Limits:
            raise TypeError('exact Limits required')
        limits.validate()
        if deadline is not None and (type(deadline) not in (int, float)
                                     or not math.isfinite(deadline)):
            raise ValueError('absolute deadline must be finite')
        self.limits = limits
        self.deadline = min(time.perf_counter() + limits.max_seconds,
                            deadline if deadline is not None else math.inf)
        self.visits = 0

    def tick(self, count: int = 1) -> None:
        self.visits += count
        if self.visits > self.limits.max_visits:
            raise ProofLimit('literal/token visit limit')
        if time.perf_counter() >= self.deadline:
            raise ProofLimit('proof deadline')

    def text(self, value: str) -> None:
        self.tick()
        if type(value) is not str:
            raise InvalidProof('exact ASCII string required')
        if len(value) > self.limits.max_bytes:
            raise ProofLimit('proof text byte limit')
        if not value.isascii():
            raise InvalidProof('non-ASCII proof syntax')
        self.tick()


_TOKEN = re.compile(r'(?:0|-?[1-9][0-9]*)\Z')
_PIN = re.compile(r'[0-9a-f]{64}\Z')


def _integer(token: str, meter: Meter) -> int:
    meter.tick()
    if len(token.removeprefix('-')) > 10 or _TOKEN.fullmatch(token) is None:
        raise InvalidProof('noncanonical or oversized integer token')
    result = int(token)
    if abs(result) > 2_147_483_647:
        raise InvalidProof('integer token outside the 31-bit format')
    return result


def _clause(literals: list[int], variables: int, meter: Meter) -> tuple[int, ...]:
    seen: set[int] = set()
    for literal in literals:
        meter.tick()
        if literal == 0 or abs(literal) > variables:
            raise InvalidProof('literal outside the original variable range')
        if literal in seen or -literal in seen:
            raise InvalidProof('duplicate or complementary clause literals unsupported')
        seen.add(literal)
    return tuple(literals)


def parse_dimacs(text: str, meter: Meter) -> tuple[int, list[tuple[int, ...]]]:
    """Closed DIMACS: one header, one zero-terminated clause per noncomment line."""
    meter.text(text)
    variables = declared = None
    clauses: list[tuple[int, ...]] = []
    for raw in text.splitlines():
        meter.tick()
        words = raw.split()
        if not words or words[0] == 'c':
            continue
        if variables is None:
            if len(words) != 4 or words[:2] != ['p', 'cnf']:
                raise InvalidProof('missing or malformed DIMACS header')
            variables, declared = (_integer(words[2], meter), _integer(words[3], meter))
            if variables < 0 or declared < 0:
                raise InvalidProof('negative DIMACS size')
            if variables > meter.limits.max_variables or declared > meter.limits.max_clauses:
                raise ProofLimit('DIMACS size limit')
            continue
        tokens = [_integer(token, meter) for token in words]
        if tokens[-1] != 0 or 0 in tokens[:-1]:
            raise InvalidProof('one zero-terminated clause required per line')
        if len(clauses) >= meter.limits.max_clauses:
            raise ProofLimit('CNF clause limit')
        clauses.append(_clause(tokens[:-1], variables, meter))
    if variables is None or len(clauses) != declared:
        raise InvalidProof('DIMACS clause count mismatch')
    meter.tick()
    return variables, clauses


def _inference(clause: tuple[int, ...], hints: list[int], database, meter: Meter) -> None:
    # Negate the proposed clause. Under these assumptions, every hint must force
    # its sole unassigned literal, or the LAST hint must already be falsified.
    assigned = {-literal for literal in clause}
    conflict = False
    if not hints:
        raise InvalidProof('a positive RUP hint chain is required')
    for position, identifier in enumerate(hints):
        meter.tick()
        if identifier <= 0 or identifier not in database:
            raise InvalidProof('unknown/forward/nonpositive clause hint')
        open_literal = None
        for literal in database[identifier]:
            meter.tick()
            if literal in assigned:
                raise InvalidProof('satisfied hint clause is outside the strict RUP subset')
            if -literal not in assigned:
                if open_literal is not None:
                    raise InvalidProof('hint clause is not unit or conflicting')
                open_literal = literal
        if open_literal is None:
            if position != len(hints) - 1:
                raise InvalidProof('hints after the conflict')
            conflict = True
        else:
            assigned.add(open_literal)
    if not conflict:
        raise InvalidProof('hint chain ends without contradiction')


def check_lrat(cnf: str, proof: str, *, expected_cnf_sha256: str,
               limits: Limits | None = None, absolute_deadline: float | None = None) -> dict:
    """Check only the independently identified CNF; this is NOT a source theorem.

    The external pin must come from the consumer, not from an untrusted bundle.
    No positive field escapes before complete syntax checking and the final clock.
    """
    meter = Meter(Limits() if limits is None else limits, absolute_deadline)
    result = {'status': 'invalid', 'verified_unsat': False, 'steps': 0, 'visits': 0}
    try:
        meter.text(cnf)
        meter.text(proof)
        if len(cnf) + len(proof) > meter.limits.max_bytes:
            raise ProofLimit('combined proof byte limit')
        if type(expected_cnf_sha256) is not str or _PIN.fullmatch(expected_cnf_sha256) is None:
            raise InvalidProof('independent lowercase SHA-256 formula pin required')
        digest = hashlib.sha256(cnf.encode('ascii')).hexdigest()
        if digest != expected_cnf_sha256:
            raise InvalidProof('formula does not match external identity')
        variables, initial = parse_dimacs(cnf, meter)
        database = {i + 1: clause for i, clause in enumerate(initial)}
        last = len(initial)
        finished = False
        for raw in proof.splitlines():
            meter.tick()
            words = raw.split()
            if not words:
                continue
            if finished:
                raise InvalidProof('proof has trailing steps after the empty clause')
            if result['steps'] >= meter.limits.max_steps:
                raise ProofLimit('proof step limit')
            tokens = [_integer(word, meter) for word in words]
            if len(tokens) < 4 or tokens.count(0) != 2 or tokens[-1] != 0:
                raise InvalidProof('expected id clause 0 positive-hints 0')
            stop = tokens.index(0)
            identifier = tokens[0]
            if stop < 1 or identifier <= last:
                raise InvalidProof('new clause ids must be strictly increasing')
            clause = _clause(tokens[1:stop], variables, meter)
            _inference(clause, tokens[stop + 1:-1], database, meter)
            if len(database) >= meter.limits.max_clauses:
                raise ProofLimit('total stored-clause limit')
            database[identifier] = clause
            last = identifier
            result['steps'] += 1
            finished = not clause
        if not finished:
            raise InvalidProof('no checked final empty clause')
        meter.tick()
        result.update(status='verified_unsat', verified_unsat=True,
                      cnf_sha256=digest, lrat_sha256=hashlib.sha256(proof.encode('ascii')).hexdigest())
        meter.tick()
    except (InvalidProof, ProofLimit) as error:
        result.update(status='inconclusive' if isinstance(error, ProofLimit) else 'invalid',
                      verified_unsat=False, reason=str(error))
        result.pop('cnf_sha256', None)
        result.pop('lrat_sha256', None)
    result['visits'] = meter.visits
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cnf', type=Path)
    parser.add_argument('proof', type=Path)
    parser.add_argument('--expected-cnf-sha256', required=True)
    parser.add_argument('--max-bytes', type=int, default=8_000_000)
    parser.add_argument('--max-seconds', type=float, default=10.0)
    args = parser.parse_args()
    started = time.perf_counter()
    limits = Limits(max_bytes=args.max_bytes, max_seconds=args.max_seconds)
    limits.validate()
    try:
        texts = []
        for path in (args.cnf, args.proof):
            with path.open('rb') as stream:
                data = stream.read(limits.max_bytes + 1)
            if len(data) > limits.max_bytes:
                raise ProofLimit('input file byte limit')
            texts.append(data.decode('ascii'))
        result = check_lrat(*texts, expected_cnf_sha256=args.expected_cnf_sha256,
                            limits=limits, absolute_deadline=started + limits.max_seconds)
    except (OSError, UnicodeError, ProofLimit) as error:
        result = {'status': 'inconclusive' if isinstance(error, ProofLimit) else 'invalid',
                  'verified_unsat': False, 'reason': str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'verified_unsat' else 1


if __name__ == '__main__':
    raise SystemExit(main())
