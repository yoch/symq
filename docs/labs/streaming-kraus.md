# Streaming Kraus obligations: eliminate deterministic events, reject leaks early

Research checkpoint on #160. The reference anchored ANF engine is unchanged.
The new opt-in `symq.labs.anchored_stream.verify_stream` accepts the same closed
source/table documents. It is not a generic channel or instrument comparison.

## Prefix-information lemma and reduction

After eliminating earlier Z/reset events, let r denote only preceding HMR
outcomes. Every r is reachable on every legal basis input with probability
2^(-H_prefix). Immediately before a Z measurement/reset of q, prove

```math
D(x)(q(x,r)\oplus q(x_0,r))=0.
```

If the identity fails, the immutable prefix record distinguishes two legal
inputs. Its distributions have positive classical fidelity loss. Any final
channel equal to an isometry on that coherent support must have an input-independent
complementary/environment channel, so no trace-preserving suffix can repair this
information leakage. The witness contains the two legal inputs, HMR prefix and
operation index, and is replayed by a separate scalar interpreter before return.
Overwriting or forgetting a user-facing classical slot is not quantum erasure
of the measurement environment.

If it succeeds, replace that event by q(x0,r), a Boolean function of existing
HMR variables. No new random bit and no support-product factor are needed. For
measure_z the measured wire may also be replaced by that expression on D; reset
sets it to zero. Induction gives a support-free symbolic trace. Final equality
of all output bits and input-independence of phase are then necessary and
sufficient for the same retained-output / forgotten-record isometry contract.
This is a specialization of information-disturbance and rank-one Kraus facts,
not a claim to discover those general results.

Primary background: Nielsen et al., *Information-theoretic approach to quantum
error correction and reversible measurement*, https://arxiv.org/abs/quant-ph/9706064;
Beny and Oreshkov, *Approximate simulation of quantum channels*,
https://arxiv.org/abs/1103.0649. Neither source is claimed to contain this exact
implementation, and no novelty claim is made over general symbolic hybrid methods.

## Additional engineering

The current implementation shares the whole-call SymQ Guard/VerificationSession
limits, refuses unsupported inherited node/byte limits, snapshots exact JSON
primitives under explicit size/depth/time limits, and independently replays each
refutation. Dead classical slots are released after their last read; immutable
HMR variables retained in actual proof expressions remain untouched. The peak
term statistic is explicit polynomial storage accounting, not process RSS.

## Executed checkpoint, not external-performance evidence

An authenticated minimal snapshot was reconstructed via GitHub (no working Git
network was available). Standalone Python 3.13 execution of 400 sources x 12
contracts at seed159: 4800 verdicts agree with the independent rational-density
oracle, 366 positive / 4434 negative, all negative coherence pairs checked.
Six new local pytest tests pass, including another 1200 cases at seed311.

- Twelve Z measurements: reference hits 5000-term cap; streaming refutes at the
  first operation with peak 14 terms. Larger widths through 129 were exercised.
- 128 repeated measurements of a known-zero ancilla: reference hits the cap;
  streaming proves equivalence with all 128 deterministic events eliminated.
- Corrected 256-HMR chain: 262 -> 8 peak terms, 256 -> 1 live classical slots.
  At 1024 HMR the optimized term statistic remains 8. No full-scale external
  corpus, holdout, general constant-memory claim or speedup is asserted.

A graph/SAT algebra is the next separate experiment on the same obligations.
Code/qualification on the installed complete repository still needs final CI
and independent semantic review. Nothing is merged or promoted to the stable API.
