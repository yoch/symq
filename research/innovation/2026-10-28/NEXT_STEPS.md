# Next steps, justified by the data only

Each item names the measurement that would justify it, and the measurement that would kill it.
Anything not on this list has no data behind it.

## 1. Find a real program the channel criterion needs (highest value)

The only route by which pilot A2 becomes a scientific result. Concretely:

1. Import a public measurement-assisted uncomputation corpus -- the programs in
   `andigu/uncompute` are the most likely source, since the project already cites it -- and the
   HMR-heavy fragments of the 2026 phased-simulation benchmarks.
2. Run O2 and the channel criterion on every program and record the four-way split
   (both accept / O2 only / channel only / neither).
3. **Kill criterion:** if no program is "channel only", the criterion stays a note in the
   repository and nothing more is written about it.

Estimated cost: importing the programs is the work; the analysis is already written
(`prototype/factored.py`, `prototype/channel.py`).

## 2. Collector prototype (engineering, already justified)

`pilot_c2.py` shows the rebuild is affordable; what is missing is the memory actually freed,
which needs instrumentation inside the C allocator. Concretely:

1. Instrument the native manager with `nodes_allocated`, `nodes_reachable` and
   `cache_bytes`, exposed through `cache_info()` or a new `memory_info()`; no behaviour change.
2. Re-run `pilot_c.py` on the circuits that currently die of memory (the blind-corpus adders
   that were killed at 15 GiB) and record the ratio.
3. **Kill criterion:** if the reachable set exceeds ~50 % on those circuits, the collector
   cannot help and the memory cost is structural.

## 3. Composed-circuit path (engineering, conditional)

Only worth integrating if the effect is stable across families. Concretely: re-run
`pilot_b2.py` on 50+ structured circuits with a paired node count, and keep the strategy only if
the geometric mean of `miter_nodes / separate_nodes` over non-equivalent pairs is below 0.9 with
a bootstrap interval that excludes 1. On the current 4 non-equivalent instances the ratios are
1.09, 0.61, 1.06, 0.58 -- far from stable.

## 4. Width > 64 (do not start)

No connected circuit with more than 64 wires and a *useful* equivalence question has been
identified. Block decomposition already handles disconnected ones. The Python backend handles
width. Nothing to do until a user brings such a circuit.

## 5. What would make this a paper

Any **one** of:

* Item 1 finds a real family where O2 rejects correct programs and the channel criterion accepts
  them, plus a comparison against Irene or phased outcome-complete simulation on the same
  programs.
* A cheaper ordering policy predicted from circuit structure (not chosen by trials) that beats
  the identity order on adders *and* does not regress on the rest -- the old variable-order
  runs already show the failures to fix, and no policy has been proposed yet.
* A proof obligation at circuit interfaces that lets two large circuits be compared block by
  block without materialising either polynomial -- this is axis E, not started, and the first
  step is one worked example, not a framework.

None of these is close. The current state is a solid tool, and `DECISION.md` records that.
