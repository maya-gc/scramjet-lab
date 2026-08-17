"""Thin wrapper: static isometric 3D engine renders.

Equivalent to:  python -m backend.interfaces.cli viz-engine ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.interfaces import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main(["viz-engine"] + sys.argv[1:]))
