# Innovation review -- 28 October 2026

Read `DECISION.md` first. Summary:

| file | content |
|---|---|
| `STATE_OF_THE_ART.md` | prior art per candidate mechanism, with citations, and what it forbids claiming |
| `HYPOTHESES.md` | mechanisms, falsifiable predictions, stop criteria (written before the runs) |
| `PILOTS.md` | every pilot that was executed, results and limits |
| `PILOT_A.md` | factored HMR phase and the channel criterion (with the proofs) |
| `PILOT_B.md` | equivalence by simulating the composed circuit |
| `PILOT_C.md` | dead-node measurement and rebuild cost (issue #56) |
| `RESULTS.json` | machine-readable results, keyed by pilot, with the git HEAD |
| `DECISION.md` | category per pilot and the overall verdict |
| `NEXT_STEPS.md` | only the experiments the data justify |
| `prototype/` | the code: `factored.py`, `channel.py`, `pilot_a.py`, `pilot_a2.py`, `pilot_b.py`, `pilot_b2.py`, `pilot_c.py`, `pilot_c2.py`, `pilot_scale.py` |
| `../../tests/test_factored.py` | 51 tests: the invariant, the criterion against the oracle, the closed form |

**Verdict: `ENGINEERING_IMPROVEMENT_ONLY`.**

To reproduce: `python research/innovation/2026-10-28/prototype/pilot_a.py` (and `_a2`, `_b`,
`_b2`, `_c`, `_c2`), each writes its own JSON; `pytest tests/test_factored.py` checks the
criterion against the density-matrix oracle. Every pilot runs against the production engine at
the commit in `RESULTS.json`; nothing in `src/` was changed by this work.
