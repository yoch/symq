# Public demonstration: SymQ in 6–8 minutes

This walkthrough uses **only the public, maintained Python installation**.
It requires no notebook, proprietary corpus, cloud service, optional native
compiler or external quantum provider.

It answers three questions with one small reproducible program:

1. Can SymQ prove equivalence between two reversible Boolean circuits?
2. Can it return a concrete input when they differ, and replay that input?
3. Can an outcome-forgotten measurement-assisted circuit preserve **all quantum
   coherences**, and detect a missing phase correction which basis-state tests miss?

## 1. Setup (before the presentation)

From a clean source checkout:

```bash
git clone https://github.com/yoch/symq.git
cd symq
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python examples/public_demo.py
```

On Windows use the activation command for your shell. Python 3.10 or newer is
required. No extra installations are needed for the demo.

The output is JSON with a `classical` section, an `hmr` section and the
limits of what was demonstrated. Witness values depend on the exact reference
and backend; never hardcode a particular witness as a performance or proof claim.

Run the exact automated smoke check beforehand if the `dev` extra is installed:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_public_demo.py
```

If the demo fails, **do not substitute a claimed success**. Inspect the
environment and run the same source SHA as the CI artifact.

## 2. Classical full-function equivalence (2 minutes)

Open [`examples/public_demo.py`](../examples/public_demo.py).

The reference is the empty 3-wire circuit. The candidate applies one CCX and
its inverse (another CCX), so their complete output functions are equal. An
unpaired CCX produces a genuinely different function. A returned integer
witness is checked by executing both concrete circuits.

A second, independent representation, the pure-Python monomial-ZDD, exports
the target's Boolean ANF. Its degree is two: the Toffoli target contains a
product of its two controls.

**What this establishes:** exact equality/non-equality under the full
`X/CX/CCX/MCX` reversible Boolean grammar, for these tiny circuits.

**What it does not:** that SAT, CUDD and native ZDD are equivalent in speed,
that arbitrary quantum circuits are supported, or that every difficult
circuit fits memory.

## 3. Prepared HMR and quantum coherences (3 minutes)

The demo constructs a 2-data-wire, 1-zero-ancilla temporary AND:

- Apply CCX to compute a product into the ancilla.
- Measure that ancilla in the X basis and reset it to zero (HMR).
- Apply the outcome-conditioned CZ phase to erase the phase debt.

The repaired stream has the same **full, outcome-forgotten quantum channel**
as identity under the specified preparation, including all coherent input
matrix units `|x><y|`. Removing CZ can leave classical basis outputs
unchanged while destroying off-diagonal coherences. The experimental
`symq.experimental.verify` API reports `different` and a witness pair.
`symq.experimental.replay` rechecks that witness.

The demo uses **`backend="zdd"`**, with no native extension. It uses one
specific sign-phase/HMR grammar, not arbitrary measurements, rotations,
Hadamards or dynamic classical programs.

**Key message to the audience:** checking truth tables is insufficient for a
coherent channel. The *declared theorem* determines what counts as a proof.

## 4. Optional CLI walkthrough (1 minute)

The installed tool accepts strict versioned JSON documents. With the
repository's existing sample files:

```bash
python -m symq inspect examples/experimental/candidate.json \
  --other examples/experimental/reference.json --json
python -m symq verify examples/experimental/reference.json \
  examples/experimental/candidate.json \
  --contract examples/experimental/contract.json \
  --report /tmp/symq-demo-result.json
python -m symq replay /tmp/symq-demo-result.json
```

`inspect` checks whether a theorem/backend pair is admissible; it is **not a
proof**. `verify` recomputes the requested result; `replay` validates a
negative witness or recomputes a positive result. A saved result file or
hash alone is not authority.

`python -m symq doctor` reports native availability; it intentionally exits
with code **1** if the optional native extension is absent, even when this
demo works. Do not mistake that diagnostic for failed pure-Python verification.

## 5. Evidence and disclosures (1 minute)

For a public talk, separate **capability**, **experiment** and **publication**:

| Claim | Defensible statement |
| --- | --- |
| Exact Boolean simulation | Yes, for the declared reversible gate grammar, within resource limits |
| Replayed difference | Yes, a concrete Boolean witness or coherent input-pair witness under the declared theorem |
| HMR channel proof | Restricted sign/HMR full/reduced coherent channels; the public Qualtran m=1/2 qualification is small and experimental |
| Native performance | No universal acceleration claim; different representations hit different resource frontiers |
| General quantum circuits | No — unsupported operations and contracts are rejected |
| Research paper | Draft and validation work are separate from an approved publication or arXiv submission |

For verified existing data, see [HMR qualification](hmr-qualification-20261030.md),
[synthetic campaign evidence](roadmap-evidence.md) and
[the architecture map](ARCHITECTURE.md). For remaining launch decisions,
see [public readiness](PUBLIC_READINESS.md).

**Suggested closing sentence:** SymQ is a testable research toolkit for exact
reversible-Boolean verification and explicitly scoped coherent-channel
experiments. It puts theorem boundaries and negative results ahead of blanket
speedup claims.
