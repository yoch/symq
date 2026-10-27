"""``python -m symq doctor``: environment report (see :mod:`symq.doctor`)."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .doctor import doctor


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m symq")
    parser.add_argument("command", choices=["doctor"], help="environment and toolchain report")
    parser.parse_args(argv)
    return doctor()


if __name__ == "__main__":
    sys.exit(main())
