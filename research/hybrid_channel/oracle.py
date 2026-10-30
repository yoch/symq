"""Compatibility imports for the canonical experimental hybrid oracle."""
from symq.experimental.hybrid import (
    _ARITY,
    _BIT,
    _CONTROLLED,
    _QUANTUM,
    ChannelResult,
    HOp,
    HybridProgram,
    InstrumentResult,
    Matrix,
    _add,
    _Branch,
    _condition,
    _evolve,
    _measure,
    _partial_trace,
    _permute,
    _quantum_step,
    _reset,
    _sign,
    _slot,
    coherence_image,
    coherence_instrument,
    same_channel,
    same_instrument,
)

__all__ = ['_ARITY', '_BIT', '_CONTROLLED', '_QUANTUM', 'ChannelResult', 'HOp', 'HybridProgram', 'InstrumentResult', 'Matrix', '_Branch', '_add', '_condition', '_evolve', '_measure', '_partial_trace', '_permute', '_quantum_step', '_reset', '_sign', '_slot', 'coherence_image', 'coherence_instrument', 'same_channel', 'same_instrument']
