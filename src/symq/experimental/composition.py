"""Deprecated location: this module moved to ``symq.labs.channel_composition``.

Importing it still works and returns the same module object, with a ``DeprecationWarning``.
"""
import sys
import warnings

from symq.labs import channel_composition as _module

warnings.warn("symq.experimental.composition moved to symq.labs.channel_composition", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _module
