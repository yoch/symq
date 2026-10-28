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
