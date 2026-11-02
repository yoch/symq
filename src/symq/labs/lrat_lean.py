"""Untrusted data-only export to Lean's verified LRAT checker, with kernel reduction.

Emitting Lean text is NOT checking a proof. The generated claim becomes a theorem
only when the pinned Lean kernel accepts it. The Python RUP inference checker is
not invoked. Source-to-CNF semantics and this literal translation remain separate
binding obligations; no source-level formal-verification verdict is returned.
"""
from __future__ import annotations

import hashlib

from symq.labs import lrat_rup as syntax

LEAN_TOOLCHAIN = 'leanprover/lean4:v4.19.0'
LEAN_COMMIT = '6caaee842e9495688c1567e78c0e68dbb96942aa'


def emit_lean(cnf: str, proof: str, *, expected_cnf_sha256: str,
              limits: syntax.Limits | None = None,
              absolute_deadline: float | None = None) -> dict:
    """Render literal CNF/LRAT data and ``check_sound ... (by decide +kernel)``.

    DIMACS variable n becomes Lean CNF variable n-1: Lean's verified CNF
    conversion lifts it back to n when it checks the unmodified LRAT literals.
    Only addition-only RUP syntax is rendered, not arbitrary Lean commands.
    The independent Python inference kernel may reject an emitted trace; Lean
    itself must reject that trace before a theorem can be accepted.
    """
    meter = syntax.Meter(syntax.Limits() if limits is None else limits, absolute_deadline)
    result = {'status': 'invalid', 'verified_unsat': False, 'lean_source': None}
    try:
        meter.text(cnf)
        meter.text(proof)
        if len(cnf) + len(proof) > meter.limits.max_bytes:
            raise syntax.ProofLimit('combined proof input byte limit')
        if type(expected_cnf_sha256) is not str or syntax._PIN.fullmatch(expected_cnf_sha256) is None:
            raise syntax.InvalidProof('external canonical CNF digest required')
        digest = hashlib.sha256(cnf.encode('ascii')).hexdigest()
        if digest != expected_cnf_sha256:
            raise syntax.InvalidProof('formula does not match consumer pin')
        variables, clauses = syntax.parse_dimacs(cnf, meter)
        # Only well-typed numeral/list syntax is accepted here. Unit propagation
        # and UNSAT are checked by Lean, not trusted from this producer.
        steps = []
        identifiers = set(range(1, len(clauses) + 1))
        last = len(clauses)
        finished = False
        for raw in proof.splitlines():
            meter.tick()
            words = raw.split()
            if not words:
                continue
            if finished:
                raise syntax.InvalidProof('trailing proof after empty clause')
            if len(steps) >= meter.limits.max_steps:
                raise syntax.ProofLimit('proof step limit')
            integers = [syntax._integer(word, meter) for word in words]
            if len(integers) < 4 or integers.count(0) != 2 or integers[-1] != 0:
                raise syntax.InvalidProof('expected id clause 0 hints 0')
            stop = integers.index(0)
            identifier = integers[0]
            if stop < 1 or identifier <= last:
                raise syntax.InvalidProof('increasing clause identifiers required')
            clause = syntax._clause(integers[1:stop], variables, meter)
            hints = integers[stop + 1:-1]
            if not hints:
                raise syntax.InvalidProof('nonempty positive RUP hints required')
            for hint in hints:
                meter.tick()
                if hint <= 0 or hint not in identifiers:
                    raise syntax.InvalidProof('missing/forward/unsupported hint')
            if len(identifiers) >= meter.limits.max_clauses:
                raise syntax.ProofLimit('stored clause limit')
            steps.append((identifier, clause, hints))
            identifiers.add(identifier)
            last = identifier
            finished = not clause
        if not finished:
            raise syntax.InvalidProof('no final empty-clause action')
        pieces, size = [], 0

        def put(text):
            nonlocal size
            meter.tick()
            size += len(text)
            if size > meter.limits.max_bytes:
                raise syntax.ProofLimit('generated Lean source byte limit')
            pieces.append(text)

        proof_digest = hashlib.sha256(proof.encode('ascii')).hexdigest()
        put('import Std.Tactic.BVDecide.LRAT.Checker\n\n')
        put('-- Generated DATA only; compile with pinned Lean v4.19.0.\n')
        put(f'-- CNF SHA256: {digest}\n-- LRAT SHA256: {proof_digest}\n')
        put('set_option maxRecDepth 8192\nset_option maxHeartbeats 8000000\n\n')
        put('namespace SymQPortable\n\ndef formula : Std.Sat.CNF Nat := [\n')
        for index, clause in enumerate(clauses):
            items = []
            for literal in clause:
                meter.tick()
                items.append(f'({abs(literal) - 1}, {"true" if literal > 0 else "false"})')
            put('  [' + ', '.join(items) + ']' + (',' if index + 1 < len(clauses) else '') + '\n')
        put(']\n\ndef witness : Array Std.Tactic.BVDecide.LRAT.IntAction := #[\n')
        for index, (identifier, clause, hints) in enumerate(steps):
            hint_text = ', '.join(str(hint) for hint in hints)
            if clause:
                literals = ', '.join(f'({lit})' if lit < 0 else str(lit) for lit in clause)
                action = f'.addRup {identifier} #[{literals}] #[{hint_text}]'
            else:
                action = f'.addEmpty {identifier} #[{hint_text}]'
            put('  ' + action + (',' if index + 1 < len(steps) else '') + '\n')
        put(']\n\n')
        put('theorem claim : formula.Unsat :=\n')
        put('  Std.Tactic.BVDecide.LRAT.check_sound witness formula (by decide +kernel)\n\n')
        put('#print axioms claim\nend SymQPortable\n')
        generated = ''.join(pieces)
        meter.tick()
        result.update(status='emitted', lean_source=generated,
                      cnf_sha256=digest, lrat_sha256=proof_digest,
                      lean_sha256=hashlib.sha256(generated.encode('ascii')).hexdigest(),
                      toolchain=LEAN_TOOLCHAIN, lean_commit=LEAN_COMMIT,
                      variables=variables, input_clauses=len(clauses), steps=len(steps),
                      theorem_name='SymQPortable.claim', source_semantics_formally_verified=False)
        meter.tick()
    except (syntax.InvalidProof, syntax.ProofLimit) as error:
        result = {'status': 'inconclusive' if isinstance(error, syntax.ProofLimit) else 'invalid',
                  'verified_unsat': False, 'lean_source': None, 'reason': str(error)}
    result['visits'] = meter.visits
    return result
