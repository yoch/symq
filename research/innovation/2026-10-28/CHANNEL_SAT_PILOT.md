# HMR channel SAT pilot (SymQ issue #73)

**Research-only, full-channel decision** for the existing ±1 HMR fragment.
No private `qant` imports, no automatic dispatch, and no changes to
`symq.phase.check_phase_equivalence` (which has the stricter branch-level contract).

Already available locally: `factored.factor` computes `F,phi0,G`;
the independent exact Kraus oracle is `channel.py`. This pilot adds a SAT miter
over **data input pairs** `(x,y)`, without expanding `2^M` HMR outcome strings.

Prove the three UNSAT obligations in order: output map, coherence-kernel
agreement, relative phase on surviving coherences. For a SAT witness, replay
against the exact factorized ANF functions; tests independently confirm the
same full density-matrix channel by Kraus enumeration on small programs.

This is **not** traced-ancilla equivalence; data and ancilla counts must match.
No arbitrary H/T/S, measurements in Z basis, or unsupported feed-forward.
No claim of external LRAT certificate or certified general quantum channels.

The solver uses the existing optional interruptible PySAT engine, cooperative
end-to-end time budget, CNF clause cap and tri-state
`equivalent/different/inconclusive`. A local SAT model is replayed; a timeout
or unsupported input can never become an equivalence verdict.

### Evidence and STOP/GO

`PYTHONPATH=src python -m pytest tests/test_channel_sat.py -q`

Compare exactly to the existing full-channel Kraus oracle on independent small
programs. Next: one licensed real measurement-assisted uncomputation fragment,
a fixed source SHA, end-to-end timing vs pair-ZDD and a concrete `channel-only`
case. Without these, keep the implementation experimental; do not claim a
coverage/performance improvement or promote the public runtime API.

### Public-source regression (no runtime dependency)

A two-episode miniature of the **temporary-AND / HMR / conditional CZ release**
pattern documented in [andigu/uncompute](https://github.com/andigu/uncompute),
Apache-2.0, pinned at commit
`64b5a13aa249f1360846657392e6c66817b26d0f`, is tested against both
strict branch semantics and the independent exact Kraus channel oracle.
Its source patterns are `uncompute/builder.py::and_release` and
`uncompute/gadgets/arith.py::booth_columns_release`.
The test is reconstructed by hand from the public documentation and **does not**
import the external library or require its circuit generator. The second phase
correction is omitted in a mutant, which must produce a concrete pair of inputs
witnessing a channel mismatch.

This is a **real, licensed source-pattern regression**, not a claim that SymQ
has imported or verified a full industrial HMR circuit. That larger coverage
and cost study remains the gate to promoting #73 beyond research.

### Matched small-corpus benchmark

`research/innovation/2026-10-28/benchmark_channel_sat.py` defines ten fixed,
small channel-equivalence pairs, including two chained temporary-AND releases,
noisy/channel-only phase, two syndrome bases defining the same kernel, and
output/kernel/relative-phase mutants. It calls the existing pair-ZDD criterion
and the SAT checker with **identical input programs**, five paired repetitions,
full public-call timing and no substitution of inconclusive outcomes.

The Python 3.12 CI job runs the benchmark and logs a JSON record with exact
commit, Python/PySAT version, cases, raw samples and paired medians. This is a
*small exploratory comparison*, not a sealed independent holdout or a claim
of general speed. Neither native RSS nor memory allocations are compared;
the run intentionally has no cross-project dependencies.

### Résultat de performance — négatif sur les dix petites paires

La [campagne appariée versionnée](RESULTS/channel_sat_matched_20261028.json)
a été exécutée par GitHub Actions [run 40767122111](https://github.com/yoch/symq/actions/runs/40767122111)
sur le HEAD publié `a65cf3e60329151e375c211bb48b599cb333a812` (checkout de test
`0fa8ab803624986633235e2a4ae939069518b187`), Python 3.12.15, cinq répétitions
par paire. **Les deux moteurs rendent 10/10 verdicts identiques.**

- SAT est plus lent sur **10/10** paires ;
- ratio médian (médiane des dix ratios appariés) : **5.48×** en faveur du
  ZDD Python ;
- plage des ratios : **3.49× à 11.49×** ;
- pas de comparaison RSS, pas de véritable holdout indépendant, ni de gros circuit
  importé.

**Décision : `NEGATIVE` pour l'adoption du SAT comme vérificateur HMR par
défaut sur ces petits cas.** Conserver la preuve SAT et les témoins Kraus
comme outils de recherche indépendants, mais ne pas les promouvoir comme
amélioration de performance. Cela **n'invalide pas** l'hypothèse d'un gain sur
des circuits HMR beaucoup plus gros : cette hypothèse reste non mesurée et
exige un corpus public réellement compatible.
