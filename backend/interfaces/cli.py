"""Unified command-line entry point for the scramjet-lab tooling.

This is the single script surface: every historical ``python -m <pkg>.<mod>``
and ``scripts/*.py`` entry now dispatches through one of the subcommands
below. The individual modules keep their own ``main(argv)`` functions (used
by the dispatcher), so behaviour and flags are unchanged.

Usage:
    python -m backend.interfaces.cli run     --case configs/cases/scramjet_coldflow.yaml
    python -m backend.interfaces.cli sweep   --config configs/sweeps/sweep_isolator.yaml
    python -m backend.interfaces.cli mesh-study --case ...
    python -m backend.interfaces.cli anneal  --params geometry.isolator_length=0.2:0.6
    python -m backend.interfaces.cli mesh    --case ...
    python -m backend.interfaces.cli case    --case ...
    python -m backend.interfaces.cli postprocess --case ... --workdir runs/exp_m6
    python -m backend.interfaces.cli viz-schematic  --case ... --workdir runs/exp_m6
    python -m backend.interfaces.cli viz-ramjet     --case ... --workdir runs/exp_m6
    python -m backend.interfaces.cli viz-crosssection --case ... --workdir runs/exp_m6
    python -m backend.interfaces.cli viz-anim       --case ... --workdir runs/exp_m6
    python -m backend.interfaces.cli viz-engine     --case ... --workdir runs/exp_m6
    python -m backend.interfaces.cli viz-vehicle    --case ... --workdir runs/exp_m6
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.domain.config import apply_overrides, load_case  # noqa: E402
from backend.application.pipeline import run_experiment  # noqa: E402

ALL_STEPS = "geometry,mesh,case,run,post,metrics"

SUBCOMMANDS = {
    "sweep": "backend.application.sweep",
    "mesh-study": "backend.application.mesh_study",
    "anneal": "backend.application.optimizer",
    "mesh": "backend.infrastructure.meshing",
    "case": "backend.infrastructure.casewriter",
    "postprocess": "backend.application.engineering",
    "viz-ramjet": "backend.interfaces.visualization.ramjet3d",
    "viz-crosssection": "backend.interfaces.visualization.crosssection",
    "viz-anim": "backend.interfaces.visualization.anim3d",
    "viz-schematic": "backend.interfaces.visualization.schematic",
    "viz-engine": "backend.interfaces.visualization.engine3d",
    "viz-vehicle": "backend.interfaces.visualization.vehicle",
}

USAGE = (
    "scramjet-lab unified CLI\n\n"
    "usage:\n"
    "    python -m backend.interfaces.cli <command> [options]\n\n"
    "commands:\n"
    "    run            run one case through the pipeline (steps, overrides)\n"
    "    sweep          parametric sweep (configs/sweeps/*.yaml)\n"
    "    mesh-study     mesh-independence study\n"
    "    anneal         simulated-annealing design exploration\n"
    "    mesh           generate a mesh for a case\n"
    "    case           write the SU2 config deck for a case\n"
    "    postprocess    extract engineering quantities from a solved case\n"
    "    viz-schematic  annotated side-view engine schematic (PNG)\n"
    "    viz-ramjet     cylindrical ramjet-scramjet render + GIF\n"
    "    viz-crosssection  transverse Mach cross-sections + GIF\n"
    "    viz-anim       3D rotating/scrolling animation GIF\n"
    "    viz-engine     static isometric 3D engine renders\n"
    "    viz-vehicle    Hyper-X style vehicle renders\n\n"
    "run any command with -h for its full option list.\n"
)


def cli_run(argv: list[str] | None = None) -> int:
    """Run one case through the pipeline (replaces the old root run_sim.py)."""
    ap = argparse.ArgumentParser(
        prog="scramjet run",
        description="Run the cold-flow scramjet CFD pipeline (SU2).")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow.yaml",
                    help="case YAML (default: reference cold-flow case)")
    ap.add_argument("--workdir", default=None,
                    help="experiment output directory (default: runs/<case name>)")
    ap.add_argument("--steps", default=ALL_STEPS,
                    help="comma-separated steps: geometry,mesh,case,run,post,metrics")
    ap.add_argument("--overrides", nargs="*", default=[],
                    help="dotted overrides, e.g. geometry.isolator_length=0.30")
    ap.add_argument("--solver-exe", default=None,
                    help="path/name of SU2_CFD (default: $SU2_CFD or PATH)")
    ap.add_argument("--timeout", type=float, default=None,
                    help="per-stage solver timeout in seconds")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_case(args.case)
    apply_overrides(cfg, args.overrides)
    workdir = args.workdir or f"runs/{cfg.name}"
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]

    report = run_experiment(cfg, workdir, steps=steps, solver_exe=args.solver_exe,
                            verbose=args.verbose, timeout=args.timeout)

    print("\n==================== SUMMARY ====================")
    print(f"case      : {cfg.name}")
    print(f"workdir   : {workdir}")
    if report.get("geometry_summary"):
        print(report["geometry_summary"])
    if report.get("mesh"):
        print(f"mesh      : {report['mesh'].get('n_surface_elements')} elements")
    if report.get("run"):
        for stage, info in report["run"].items():
            print(f"run       : {stage:30s} -> {info.get('status'):10s} "
                  f"rms={info.get('final_rms_density')}")
    if report.get("metrics"):
        m = report["metrics"]
        if m.get("valid"):
            print(f"pressure recovery : {m['pressure_recovery']:.4f}")
            print(f"thrust proxy [N/m]: {m['thrust_proxy']:.3f}")
            print(f"M exit            : {m['M_exit']:.3f}")
            print(f"continuity error  : {m['continuity_error']:+.4f}")
            print(f"score             : {m['score']:.3f}")
        else:
            print(f"metrics: INVALID ({m.get('error')})")
    print("=================================================")

    if report.get("metrics", {}).get("valid"):
        summary_json = Path(workdir) / "summary.json"
        summary_json.write_text(json.dumps(report["metrics"], indent=2, default=str),
                                encoding="utf-8")
        print(f"metrics written to {summary_json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    name = argv[0]
    rest = argv[1:]
    if name == "run":
        return cli_run(rest)
    module = SUBCOMMANDS.get(name)
    if module is None:
        print(f"unknown command: {name!r}\n\n{USAGE}", file=sys.stderr)
        return 2
    return importlib.import_module(module).main(rest)


if __name__ == "__main__":
    sys.exit(main())