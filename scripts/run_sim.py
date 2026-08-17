"""Thin wrapper: run one case through the pipeline.

Equivalent to:  python -m backend.interfaces.cli run ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.interfaces import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.cli_run(sys.argv[1:]))
