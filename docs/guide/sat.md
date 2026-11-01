# SAT decision engine and relational composition

`symq.sat` decides classical equivalence of X/CX/CCX/MCX circuits with a SAT miter. It is a
**decision engine**, not a representation: it never exports ANFs. Install it with
`python -m pip install -e ".[sat]"`; without `python-sat`, `symq.sat.available()` is `False` and
the checkers raise `SatUnavailable`.

## Contracts

A `Contract` states what the verification may assume and what it must observe:

| Field | Meaning |
| --- | --- |
| `input_constants` | `{wire: 0/1}` forced on both circuits (a domain restriction) |
| `observed_outputs` | wires whose final values must agree; `None` means every wire |
| `restored_wires` | wires that must return to **their own input value** (clean or borrowed ancillas) |
| `output_map` | `{left_wire: right_wire}` when the outputs are permuted |

An ignored wire is not implicitly restored, and a restored wire may start dirty: the obligation
is that it ends with the value it started with, whatever that value was.

`assumption` restricts the inputs with any closed Boolean expression over the names `x.<wire>`
(`symq.sat.assumptions`: `Var`, `Const`, `Not`, `Xor`, `And`, `Eq`), for example an affine relation
between two wires or membership in a finite set of values. Every witness is replayed against it.
An assumption that no input satisfies makes the check vacuously `equivalent`.

```python
from symq import Circuit
from symq.sat import Contract, check_sat_equivalence
from symq.sat.assumptions import Eq, Var

left = Circuit(3).ccx(0, 1, 2)
right = Circuit(3).cx(0, 2)          # agrees with left exactly when x0 == x1
assert check_sat_equivalence(left, right).outcome == "different"
on_diagonal = Contract(assumption=Eq(Var("x.0"), Var("x.1")))
assert check_sat_equivalence(left, right, on_diagonal).outcome == "equivalent"
```

```python
from symq import Budget, Circuit
from symq.sat import Contract, check_sat_equivalence

left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
right = Circuit(3)
contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))

verdict = check_sat_equivalence(left, right, contract, budget=Budget(max_seconds=10))
assert verdict.outcome == "equivalent"
```

## Outcomes

| Outcome | Meaning |
| --- | --- |
| `equivalent` | the solver proved the miter unsatisfiable for this encoding and contract |
| `different` | the model was replayed through `Circuit.run` and differs on an observed or restored wire; `witness` is the LSB-first input |
| `inconclusive` | timeout, conflict ceiling or unknown solver response; never a proof |

A model that does not replay as a counterexample raises `InternalInconsistency`: it means the
encoding is wrong, which is a bug, not a verdict. No LRAT/DRAT certificate is exported, so an
`equivalent` answer is only as trustworthy as the encoder and the solver.

Only `Budget.max_seconds` applies to SAT; `max_nodes` and `max_terms` describe symbolic
structures. The deadline is cooperative: a solver call is interrupted from a watchdog thread, and
a decisive answer produced after the deadline is reported as `inconclusive`.

## Relational composition

`symq.sat.composition.check_composition` proves that two composed circuits `A;B` and `A';B'`
satisfy a postcondition **without encoding the composition as one miter**. The caller supplies an
interface and a guarantee as closed Boolean expressions (`symq.sat.assumptions`):

- `P(x)`: the input domain, over names `x.<wire>`;
- `R(u, v)`: the relation between the two cut states `u = A(x)` and `v = A'(x)`;
- `Pre_B(u)`: what the left suffix may assume about its input;
- `post(s, t)`: the required relation between the final states `s = B(u)` and `t = B'(v)`.

Four SAT obligations are checked, each with its own expected answer:

| Obligation | Query | Expected |
| --- | --- | --- |
| `domain` | `P(x)` | SAT, otherwise everything else is vacuous |
| `prefix` | `P(x) ∧ ¬R(A(x), A'(x))` | UNSAT |
| `interface` | `R(u, v) ∧ ¬Pre_B(u)` | UNSAT |
| `suffix` | `R(u, v) ∧ Pre_B(u) ∧ ¬post(B(u), B'(v))` | UNSAT |

The suffix obligation uses **fresh, unrelated** cut variables `u` and `v`, tied only by `R`. It is
therefore a reusable local lemma: it quantifies over every pair satisfying `R ∧ Pre_B`, not only
over the pairs the prefixes happen to reach. Only the `prefix` obligation links the blocks to a
common input. An earlier version tied the two cut states to a common input inside the suffix
query; that checked reachable states only and accepted relations that did not imply the
postcondition. The current encoding was introduced to fix exactly that.

```python
from symq import Circuit
from symq.sat.assumptions import Const
from symq.sat.composition import Guarantee, Interface, check_composition, equality_all

# A and A' leave different cut states (wire 3 differs), which no wire-for-wire equality relates.
width = 4
prefix_left = Circuit(width).ccx(0, 1, 2)
prefix_right = Circuit(width).ccx(0, 1, 2).x(3)
suffix = Circuit(width).cx(2, 0)

same_012 = equality_all("u.", "v.", 3)      # u.0 == v.0, u.1 == v.1, u.2 == v.2
outputs_012 = equality_all("s.", "t.", 3)
verdict = check_composition(
    prefix_left=prefix_left, prefix_right=prefix_right,
    suffix_left=suffix, suffix_right=suffix,
    interface=Interface(width, Const(True), same_012),
    guarantee=Guarantee(width, Const(True), outputs_012),
)
assert verdict.accepted
```

`replay_witness` replays a failed obligation against **its own** semantics: a `prefix` witness is
an input `x` in `P` whose cut states violate `R`; an `interface` or `suffix` witness is a pair
`(u, v)` and no input `x` is invented for it. Wire 3 in the example is garbage, not a restored
ancilla: restoration would need an additional obligation that is not implemented.

The composition engine is experimental. Composing does not, by itself, make verification cheaper
than a monolithic miter; its value is reusing a local lemma under an explicit interface.
