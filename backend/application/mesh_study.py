"""Mesh-independence study: same case at 3-4 mesh resolutions."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.application.pipeline import run_experiment
from backend.domain.config import MeshParams, load_case
from backend.infrastructure.export import append_rows, results_row


def scaled_mesh_params(mp: MeshParams, scale: float) -> MeshParams:
    """Scale all bulk sizes; keep the first-cell height fixed (constant y+)."""
    return MeshParams(
        h_far=mp.h_far * scale,
        h_inlet=mp.h_inlet * scale,
        h_isolator=mp.h_isolator * scale,
        h_combustor=mp.h_combustor * scale,
        h_nozzle=mp.h_nozzle * scale,
        h_wall_n=mp.h_wall_n,
        bl_thickness=mp.bl_thickness * scale,
        bl_ratio=mp.bl_ratio,
    )


def run_mesh_study(case_path: str, scales=(1.0, 0.75, 0.5, 0.35),
                   workroot="runs/mesh_study", solver_exe=None) -> Path:
    workroot = Path(workroot)
    workroot.mkdir(parents=True, exist_ok=True)
    rows = []
    for scale in scales:
        cfg = load_case(case_path)
        cfg.mesh = scaled_mesh_params(cfg.mesh, scale)
        exp_dir = workroot / f"mesh_s{scale:g}"
        report = run_experiment(cfg, exp_dir, solver_exe=solver_exe)
        metrics = report.get("metrics") or {}
        metrics["mesh_scale"] = scale
        metrics["n_cells"] = (report.get("mesh") or {}).get("n_surface_elements")
        rows.append(results_row(cfg, metrics, exp_dir))
        print(f"[mesh_study] scale={scale}: "
              f"cells={metrics.get('n_cells')} "
              f"recovery={metrics.get('pressure_recovery'):.4f} "
              f"thrust_proxy={metrics.get('thrust_proxy'):.3f}")

    results_csv = workroot / "results.csv"
    append_rows(rows, results_csv)
    print(f"[mesh_study] wrote {results_csv}")
    print("[mesh_study] compare pressure_recovery / thrust_proxy across scales; "
          "converged when the change is below your acceptance threshold (e.g. 1%).")
    return results_csv


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mesh-independence study.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow.yaml")
    ap.add_argument("--workdir", default="runs/mesh_study")
    ap.add_argument("--scales", default="1.0,0.75,0.5,0.35")
    ap.add_argument("--solver-exe", default=None)
    args = ap.parse_args(argv)
    scales = tuple(float(s) for s in args.scales.split(","))
    run_mesh_study(args.case, scales, args.workdir, solver_exe=args.solver_exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
