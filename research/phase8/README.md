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
