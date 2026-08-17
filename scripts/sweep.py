"""Thin wrapper: parametric sweep.

Equivalent to:  python -m backend.interfaces.cli sweep ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.interfaces import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main(["sweep"] + sys.argv[1:]))
