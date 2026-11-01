# GF(2^6) rank-15 bilinear factorization and borrowed scratch (research)

This is a **reproduced external mathematical construction**, independent of
the 28-case substitution-manifest totals. **No bytes were fetched from
the Kaggle manwithacat/vqcc-bilinear-agent-evaluation dataset**. This is
not Kaggle-dataset qualification or an untouched holdout.

## Origin, representation and reproducibility

- External method: [Polytof](https://github.com/ZIB-IOL/polytof), MIT
  license, commit **0dcac107d15adc34dc646242d222f21ae7d32699**,
  source file scripts/make_cpd_gf.py (scheme_n6);
  [research manuscript](https://arxiv.org/abs/2602.15285).
- The exact field is GF(2^6), polynomial basis (1,x,...,x^5), with
  modulus x^6+x+1 (hex 0x43), matching the existing SymQ generator.
- The independent, standard-library-only
  [reconstruction](bilinear_rank15_reconstruction.py) uses
  GF(4)[z]/(z^3+z+1), evaluates a degree-two polynomial at four finite
  field points and infinity, decomposes each GF(4) product into three
  binary bilinear products, and finds the basis isomorphism.
- The [pinned factor certificate](bilinear_rank15_gf64.py) stores
  exactly 15 (left,right,output) six-bit masks. The SHA-256 of
  canonical JSON (sorted keys, compact separators, fields modulus=67,
  n=6 and terms=the ordered triples) is
  **f01ea3a59be8f6b40de148286fc3f968b469f8eb97eea2d0bf9976155b48c39c**.

## Exact obligations

A triple (u,v,w) denotes the output increment
parity(u AND a) * parity(v AND b) * w, with multiplication of
single-bit parities and bitwise-XOR addition. The SymQ tensor
checker recomputes all 216 GF(2) tensor entries; the independent
integer convolution/reduction oracle tests every one of the
4096 operand pairs. Two negative mutants (one omitted term; one
flipped output bit) must fail the independent oracle.

The 19-wire schedule acts on (a[6],b[6],z[6],s) and implements
(a,b,z XOR a*b,s). Each term folds its left/right parity controls,
computes the product into s with a CCX, distributes its value
to z with CNOTs, uncomputes s with a second CCX, and reverses the
input folds. The extra wire is **borrowable even if dirty**:
its unknown initial value cancels from the accumulator because
the XOR of all 15 output masks is zero; each term restores s.
No operation reads z. This is a precise reversible-permutation
identity on all basis states; its coherent-unitary extension also
holds on arbitrary superpositions including systems entangled with
s. This is **not** an HMR, reset, measurement or postselection claim.

## Counts, not an official quantum score

| Generator | CCX | CX | Wires | Extra constraint |
| --- | ---: | ---: | ---: | --- |
| SymQ schoolbook GF(64) | 51 | 0 | 18 | none |
| Rank-15 factors emitted without scratch | 40 | 116 | 18 | none |
| Rank-15 borrowed-scratch schedule | **30** | **156** | **19** | one borrowable bit |

Rank 15 is **not** automatically 15 executable Toffoli gates:
reversible fanout, reuse and uncomputation incur extra gates. These
counts are a declared X/CX/CCX proxy and do not establish smaller
Kaggle cost, Toffoli depth, T-count, physical volume, optimal rank,
or a compiler-wide improvement. The extra scratch may be unavailable
at a target insertion point; a contextual substitution must check
that interface and the restored-wire obligation.

## Qualification

Run from a checked-out PR #126 branch with its development dependencies:

    python -m pytest -q tests/test_bilinear_rank15_gf64.py

The standalone reproduction is outside the old 28-case matrix.
The separate Draft PRs #124/#125 provide future contextual-substitution
contracts; their APIs are not implied to be merged into main.

## Further improvement: use an existing output accumulator (no ancilla)

With an arbitrary output bit z[p] as a pivot and any other output bit
z[k], the sequence CX(p,k) / CCX(a,b,p) / CX(p,k) changes both
z[p] and z[k] by the same bilinear product; the old z[p] contribution
is cancelled by the two CNOT gates. Applied to the 15 factors, this gives
**15 CCX, 166 CX, 18 wires**. It is valid for all original z values
without assuming clean outputs or allocating new wires. The independent
plain-interpreter local campaign exhaustively checked all **2^18** input
states; the GitHub tests check all operand pairs and representative
nonzero output words. This is a reversible-permutation proof obligation
only and does not yet measure competition cost.
