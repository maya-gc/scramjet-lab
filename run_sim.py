"""scramjet-lab: single entry point for the cold-flow scramjet pipeline.

This is now a thin wrapper around the unified CLI (backend.interfaces.cli);
see there and docs/BACKEND.md for the full command surface.

Examples
--------
    # Full pipeline for the reference case
    python run_sim.py --case configs/cases/scramjet_coldflow.yaml

    # Only geometry + mesh (no solver needed)
    python run_sim.py --steps geometry,mesh

    # Sweep a parameter from the CLI
    python run_sim.py --overrides flow.mach=5.0 geometry.isolator_length=0.30

    # Custom experiment directory and solver path
    python run_sim.py --workdir runs/exp_m6 --solver-exe C:\\SU2\\bin\\SU2_CFD
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.interfaces import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.cli_run(sys.argv[1:]))
