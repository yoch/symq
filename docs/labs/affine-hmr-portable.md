# Portable affine HMR channel certificates (strict research pilot)

Module: `symq.labs.affine_hmr_portable`. This is a **solver-free algebraic
certificate**, **not LRAT** and not a formally verified implementation.
The checker uses only the Python standard library, and can be executed as
a standalone script without installing SymQ or a SAT solver.

## Exact theorem

Input: `HybridProgram` with `data` arbitrary coherent data wires and
`ancillas` initialized to zero, an explicitly injective affine support
`x = offset XOR B*u` on those data wires, and an independent phase-free
reversible reference `Circuit`. All physical outputs are retained and
measurement records are forgotten.

The admitted hybrid grammar is X/CX/CCX/MCX and unconditional SWAP (only when every intermediate
quantum wire remains affine on the legal support), Z/CZ/CCZ/NEG (only if
the resulting phase is degree ≤2), unconditional X-basis HMR, classical
`store/invert/oxor` and declared classical conditions that preserve those
degree restrictions. General reset, Z measurement, arbitrary rotations,
non-affine intermediate quantum states and unsupported controls **fail closed**.

For each admitted computational input `u` and every outcome vector `m`,
the interpreter derives exactly

```text
K_m |u,0> = 2^(-h/2) * (-1)^(phase(u,m)) |F(u,m)>
```

where `h` is the number of HMR events. Each HMR has both outcome amplitudes
`±1/sqrt(2)` on every computational basis input, with the sign captured by
`m * measured_wire(u,m)` and the measured wire reset to zero. The state
`F` is affine and the phase polynomial over input/outcome bits is represented
canonically in the Boolean ring.

The checker accepts only if (i) every physical output of `F(u,m)` equals
the supplied phase-free reference circuit's output for **every** legal
`u,m`, and (ii) the phase polynomial contains no monomial that depends on
an input coordinate. Hence each branch is `K_m = c_m W` on the full declared
coherent span with a branch-dependent but input-independent scalar
`c_m = ±2^(-h/2)`. Since there are `2^h` outcome sequences,
`sum_m |c_m|² = 1`, so the complete channels (including arbitrary
external reference systems) agree. This is a **sufficient, restricted**
proof; returning `not_proved` or `unsupported` is never proof of difference.

## End-to-end source-bound use

```python
from symq import Circuit
from symq.experimental.hybrid import HybridProgram
from symq.experimental.serialization import program_to_dict
from symq.labs.affine_hmr_portable import (
    digest, export_affine_hmr_certificate, check_affine_hmr_certificate,
)

program = HybridProgram(1, 1).cx(0, 1).hmr(1, "b0").z(0, condition="b0")
source = program_to_dict(program)
reference = Circuit(2).to_dict()
support = {"kind": "affine_data_span", "offset": 0, "columns": [1]}

result = export_affine_hmr_certificate(source, reference, support)
assert result["status"] == "exported"
bundle = result["bundle"]
verified = check_affine_hmr_certificate(
    bundle,
    expected_source_sha256=digest(source),
    expected_reference_sha256=digest(reference),
    expected_support_sha256=digest(support),
)
assert verified["status"] == "verified" and verified["verified_channel"]
```

A source-independent caller must pin the **three exact canonical SHA-256s**
*externally*. The digests inside an untrusted bundle have no authority.
The consumer rechecks the complete source, expected circuit and coherent
support, reconstructs every state/phase form, and compares the entire
claim. It never trusts a stored `proved` flag or previously emitted
phase expression.

For a standalone consumer, run the module's source file as a script with
the JSON bundle path and `--source-pin`, `--reference-pin`,
`--support-pin`. It imports no SymQ code or solver. Export itself is not
a trusted verdict until the consumer has successfully rechecked.

## Synthetic scale and limitations

The tests include a **constructed** 40-physical-wire / 35-independent-data
coordinate / 89-HMR-event case. One genuinely input-dependent HMR is
cancelled by its conditional phase correction; the other 88 measurements
act on a proven-zero ancilla. The checker verifies the outcome-dependent
algebra **without enumerating 2^89 branches**. This is a very special
synthetic family; it is *not* a certified C39 loader, no real Kickmix
binary decoder, and no general scale/performance claim.

A 2-data/1-ancilla test additionally demonstrates that a Toffoli becomes
affine only under a separately declared correlated input support; expanding
the legal domain causes refusal. Small density/Kraus oracles test all
supported coherences and phase mutants; the in-repo oracle
(`symq.experimental.hybrid`) is implemented separately from this checker but
is not external to SymQ.

Budget caps: 128 physical wires, 256 HMR events, 100,000 operations
and 100,000 retained polynomial terms by default, with a cooperative
deadline. These are resource limits, not proof of general complexity.
The classical event names must remain exact, and a full channel is
not an observed instrument. An externally restricted coherent support
is not automatically established at a **cut in a larger circuit**.
That prefix-reachability obligation must be proved separately.

The next useful extension is a **source-bound SAT/LRAT certificate** for
affine-target HMR loader semantics with genuinely nonlinear lookup tables
and Z/reset events; see [#144](https://github.com/yoch/symq/issues/144)
and [#167](https://github.com/yoch/symq/issues/167). No default engine,
stable API or whole-invsqrt claim is implied.
