# Z8 phase-polynomial pilot — independent of qant

Research issue [#80](https://github.com/yoch/symq/issues/80). This prototype is **not**
installed as a production checker and does **not** change `symq.phase`.

For basis permutations and diagonal Clifford+T gates, the unitary is
`U|x> = omega^p(x) |F(x)>`, with `omega = exp(i*pi/4)`.
The maps `F` are exact GF(2) ANFs; `p` is a unique integer multilinear polynomial
over the Boolean cube with coefficients modulo 8. A canonical polynomial comparison
proves equality on all basis inputs, therefore on every superposition by linearity.

The pivotal identity is **not** ordinary Boolean ANF-to-Z8 conversion:

```
    lift(a XOR b) = lift(a) + lift(b) - 2*lift(a)*lift(b)  (mod 8).
```

Failure to include the cross term would accept incorrect phase gadgets after
CNOT layers. Test cases reproduce the error explicitly and validate independent
concrete state/phase output on all inputs for random widths up to 5.

Accepted gate grammar: X, CX, CCX, MCX, T, Tdg, S, Sdg, Z, CZ, CCZ.
Unsupported: arbitrary H, HMR, measure, reset, conditional gates, non-eighth-root rotations.

The checker distinguishes exact identity, equality up to global `omega^k`,
and actual output/relative-phase disagreement with concretely checked witnesses.
It provides coarse `Budget` guards, but is **not** a production-scale compiler
or proof certificate format. This path cannot verify arbitrary Clifford+T circuits
that contain H. An explicit optional MQT QCEC adapter is a separate P1 proposal.

Run: `PYTHONPATH=src python -m pytest tests/test_phase8_research.py -q`.

### Independent QCEC cross-check and resource discipline

The already-optional `[external]` CI job executes
`tests/test_phase8_external.py` against the currently installed MQT QCEC
on a **matched unitary-only fragment**. A QCEC `equivalent` or
`equivalent_up_to_global_phase` verdict must agree with the exact Z8 local
checker, and `not_equivalent` must agree with a local difference. MQT remains
an optional test dependency, not a dependency of SymQ or of any other project.

The public pilot `check_equivalence` charges both symbolic simulations to a
**single cooperative Budget**. A deterministic delayed-symbolic test verifies
that the second pass cannot restart the deadline.
