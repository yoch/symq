# Decision, corrected -- 28 October 2026

Supersedes `DECISION.md`. That document drew three conclusions from measurements whose defects are
listed in `PILOT_CORRECTIONS.md`; this one redraws them from the corrected pilots
(`PILOT_A_CORRECTED.md`, `PILOT_B_CORRECTED.md`, `PILOT_C_CORRECTED.md`, and the JSON files
`RESULTS_A_CORRECTED.json`, `RESULTS_B_CORRECTED.json`, `RESULTS_C*.json`).

## What changed, per pilot

| pilot | original conclusion | corrected conclusion |
|---|---|---|
| A, factored phase | "factorisation buys nothing" (ratio 1.00) | **the ratio is 1.00 and always will be**, because the phase is affine in the outcomes; the factorisation is a *decomposition*, not a compression, and its value is that it turns the channel criterion into a statement about functions of the inputs alone |
| A, channel criterion | sound, accepts 4/300 extra programs | **sound and narrow**: 1 designed acceptance out of 14 programs (the invertible syndrome pair), 0 disagreements with the exact oracle across 14 designed + 550 random pairs |
| B, composed circuit | "real but unstable effect, -39 %/-42 % nodes on two instances" | **negative and closed**: in wall time the miter is **3.2-6.7× slower** on the family it was designed for, neutral elsewhere. The node reductions were real but the common prefix is simulated *twice*, which dominates |
| C, memory | 99.6-99.8 % dead, rebuild costs 44-72 % of the simulation | **larger and actionable**: 99.99 % dead, and a per-gate rebuild takes 14×200 from budget failure to **38.1 s** with **-87 % peak nodes** and identical outputs |

## Categories

| pilot | category | why |
|---|---|---|
| A1, factored phase | **III -- negative** | the expanded ANF is not larger; there is nothing to compress |
| A2, channel criterion | **I -- potential, unexercised** | new as a decision procedure for this fragment, verified sound, but no real program needs it: the one acceptance is a designed syndrome pair |
| B, composed circuit | **III -- negative** | prior art (Wille 2009, ABC) and measurably worse in its own intended regime |
| C, rebuild collector | **II -- engineering** | it decides what the engine can finish, which is the largest effect measured in this mission, and it is textbook |

## The three verdicts

**PILOTS: `PARTIALLY_VALIDATED`.** Every pilot now measures what it claims to, and the corrected
numbers are consistent across independent oracles (density matrix for A, monomial comparison for
C, function agreement for B). But two of the three original conclusions were wrong in *direction*
(B) or *magnitude* (C), so the original pilot report cannot be called validated; only the corrected
version can.

**ENGINE: `MATERIAL_IMPROVEMENT`.** Justified by two measurements, not by a percentage:

* a circuit that failed at every budget tried (14 wires, 200 gates, up to 30 M nodes) now verifies
  in 38 s with identical outputs and peak nodes down 87 % -- this is a change in *coverage*;
* 19 circuits that appear in neither tuning campaign run 3.3× faster under the reversed order, with
  one regression and no wrong function -- this is a change in *cost* on unseen inputs.

**SCIENCE: `ENGINEERING_ONLY`.** The only non-trivial result is the channel criterion. It is sound,
it is strictly weaker in its obligations than O2, and it was verified against an exact independent
oracle. Against that: the class of programs it newly accepts is one designed pair of syndromes, no
compiler output was shown to need it, and no comparison against Irene or phased outcome-complete
simulation was possible. A publication would have to claim a decision procedure nobody has asked
for, which is exactly the kind of paper this mission was told not to write.

## What would change the science verdict

One real family of measurement-assisted uncomputation where O2 rejects the correct program and the
channel criterion accepts it, with the reason being a correction an actual compiler emits. The
experiment is specified in `NEXT_STEPS.md` item 1 and costs one corpus import.
