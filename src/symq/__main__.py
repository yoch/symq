"""symq CLI entry point."""
from __future__ import annotations

import sys

from .doctor import doctor


def main() -> int:
    return doctor()


if __name__ == "__main__":
    sys.exit(main())
