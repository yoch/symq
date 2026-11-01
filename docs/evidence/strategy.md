# Automatic strategy: experimental, no demonstrated selector gain

`symq.strategy` computes cheap structural features in one pass over a gate list and turns them
into two **recommendations**: a variable order for the ZDD backends and an engine (symbolic or
SAT) for an equivalence task. Nothing in SymQ applies these recommendations automatically, and no
default behaviour depends on them.

## Features

| Feature | What it captures |
| --- | --- |
| `last_use_spread` | standard deviation of the normalised last-use positions; near 0 for a single cascade, large for staged circuits such as ripple-carry adders |
| `distinct_controls` | number of wires ever used as a control |
| `mean_arity`, `max_arity`, `controls_total` | control counts |
| `depth_estimate` | longest dependency path, computed per wire in one pass |
| `width`, `gates`, `used_wires`, `first_use_spread` | size and shape |

No rule reads a circuit's name or guesses semantics from wire positions.

## Rules

```text
order  : last_use  if last_use_spread >= 0.12 and distinct_controls >= 3 and gates >= 24
         reversed  if last_use_spread >= 0.12 and gates >= 24
         identity  otherwise
engine : sat       if a SAT solver is importable and (gates >= 20 or controls_total >= 40)
         symbolic  otherwise
```

The same rules are stated in `symq.strategy.ORDER_RULES` and `ENGINE_RULES`.

## What the evidence supports

- **Order.** `last_use` helped arithmetic circuits by large factors in the exploratory
  measurements (adders) and slowed single-cascade circuits (MCX chains). The discriminator is the
  shape of the last-use profile, not the circuit family.
- **Engine.** On a 12-task holdout, SAT was fastest on 7 tasks; where the symbolic engine won, it
  won clearly, because the encoder's fixed cost dominates below a few milliseconds. On every
  measured corpus the engine rule ends up choosing SAT, so it reproduces "always SAT" instead of
  beating it. The maximum holdout regret was 14.46× even though the median was 1.00.

The **order** rule is now available as `check_equivalence(..., order="auto")`, measured in
[the performance record](performance-2026-10-31.md): large gains on adders, a fixed sub-millisecond
cost elsewhere. The **engine** rule remains a recommendation only.

**Status of the engine rule: experimental, no demonstrated selector gain.** The thresholds were not calibrated on a
fresh independent corpus. The raw pilot data are preserved in the
[research archive](../archive-index.md).
