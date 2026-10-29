# Experimental verification API (version 1)

The installed `symq.experimental` package exposes specialized exact theorems.
It does not change the stable `symq.verification` facade. Program and contract
documents use a closed, versioned JSON grammar; unknown fields are rejected.

```python
from symq.experimental import VerificationContract, verify, prepare_reference, profile
from symq.phase import PhaseProgram
from symq.resources import Budget

reference = PhaseProgram(2, 1)
candidate = PhaseProgram(2, 1).ccx(0, 1, 2)
event = candidate.hmr(2)
candidate.cz_if(event, 0, 1)
contract = VerificationContract(theorem="full_channel", backend="zdd")
result = verify(reference, candidate, contract, budget=Budget(max_seconds=10))
assert result.equivalent
with prepare_reference(reference, contract, budget=Budget(max_seconds=10)) as prepared:
    assert prepared.compare(candidate, budget=Budget(max_seconds=10)).equivalent
assert profile(reference, candidate, contract).result.equivalent
```

The programs declare arbitrary coherent data inputs and zero-prepared ancillas.
Full-channel equality retains every quantum output and forgets measurement
records. `reduced_channel` requires two explicit ordered output mappings;
`instrument` requires observed classical slots and the bounded `hybrid-exact`
engine. An omitted correction in the example leaves basis outputs unchanged
but destroys a data coherence, so its channel is different.

Engines are explicit: `zdd`, `zdd-native` (64 paired variables),
`zdd-native-wide` (128), `zdd-native-blocks` (common disjoint factors), and
`hybrid-exact` (bounded exact reference). Native backends are optional.
No failed backend triggers a different theorem or automatic engine fallback.
Domains include `FullCube`, injective affine coordinates, reversible
preparations with explicit free wires, and closed Boolean predicates.
Every theorem covers all coherent pairs in the declared domain.

`equivalent` is a conclusive engine decision, `different` carries a replayed
witness, `inconclusive` denotes resource exhaustion, `unsupported` denotes an
unavailable engine/grammar, and `precondition_failed` denotes an empty legal
domain. These records are not independently checked proof certificates.

## Executable CLI example

Run these commands after installing a wheel, from any working directory.
Use the distributed example JSON paths as inputs:

```bash
symq inspect examples/experimental/candidate.json --other examples/experimental/reference.json
symq verify examples/experimental/reference.json examples/experimental/candidate.json --contract examples/experimental/contract.json --report /tmp/symq-result.json
symq replay /tmp/symq-result.json
symq profile examples/experimental/reference.json examples/experimental/candidate.json --contract examples/experimental/contract.json --report /tmp/symq-profile.json --html /tmp/symq-profile.html
```

The CLI also works as `python -m symq`. Its exit codes are 0 for equivalent,
1 for different, 2 for an unestablished claim, and 3 for invalid input.
`inspect` reports admissibility and never proves equivalence. `replay` checks
a negative witness or recomputes a positive result; editing a result receipt
cannot supply proof authority. Artifacts embed both programs and their contract.

CLI verification defaults to a 30-second cooperative whole-call deadline.
`--isolate --memory-mib 2048` additionally imposes subprocess limits.
Profiling uses isolation by default. API callers can select
`experimental.execution.HardLimits` and `run_isolated` directly; cooperative
guards and operating-system limits are distinct. Spawned workers import the
same package implementation as their parent and never share native managers.

Stage profiles contain exclusive durations and orchestration overhead. Use
the separate campaign runner for comparative performance measurements.

## Additional specialized APIs

- [Exact dyadic phases, cyclotomic HMR reference, and optional QCEC](experimental-phases.md)
- [Local quantum substitutions, phase debt, and proof graphs](experimental-composition.md)
- [Public Qualtran fixture provenance](../benchmarks/corpus/qualtran/README.md)
- [Qualification evidence and reproducible campaigns](roadmap-evidence.md)

Prepared references serialize their comparisons, keep roots in one owner,
renew deadlines per request, bound retained candidate records, and support
explicit `clear_cache` and `close`. Changing a theorem or domain requires a
new prepared reference. Disk receipts are never accepted as cached proofs.
