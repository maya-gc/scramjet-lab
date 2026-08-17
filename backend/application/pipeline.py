"""End-to-end pipeline orchestrator: geometry -> mesh -> case -> run -> post -> metrics.

Each experiment lives in its own directory so sweeps/optimization can run
many of them in isolation and the results are reproducible per experiment:

    <workdir>/geometry/geometry.json
    <workdir>/mesh/<case>.su2
    <workdir>/case/config/*.cfg
    <workdir>/run/<stage>.log   (+ SU2 solution files)
    <workdir>/post/*.png, stations.csv
    <workdir>/metrics.json
    <workdir>/report.json
"""
from __future__ import annotations

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

from backend.domain.config import CaseConfig
from backend.domain.geometry import build_geometry, summary, write_geometry_json

STEPS = ("geometry", "mesh", "case", "run", "post", "metrics")


def run_experiment(cfg: CaseConfig, workdir: str | Path,
                   steps: list[str] | None = None,
                   solver_exe: str | None = None,
                   verbose: bool = False,
                   timeout: float | None = None) -> dict:
    steps = set(steps or list(STEPS))
    unknown = steps - set(STEPS)
    if unknown:
        raise ValueError(f"unknown steps: {sorted(unknown)}")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    report: dict = {"case": cfg.name, "workdir": str(workdir),
                    "description": cfg.description}

    geo = build_geometry(cfg.geometry)

    if "geometry" in steps:
        write_geometry_json(geo, workdir / "geometry" / "geometry.json")
        report["geometry_summary"] = summary(cfg.geometry, geo)

    if "mesh" in steps:
        from backend.infrastructure.meshing import make_mesh
        mesh_path = workdir / "mesh" / f"{cfg.name}.su2"
        report["mesh"] = make_mesh(cfg, mesh_path, verbose=verbose)

    if "case" in steps:
        from backend.infrastructure.casewriter import write_case_configs
        configs = write_case_configs(cfg, workdir / "case")
        report["configs"] = [str(p) for p in configs]

    if "run" in steps:
        from backend.infrastructure.su2 import run_case_stages
        run_dir = workdir / "run"
        report["run"] = run_case_stages(cfg, run_dir, solver_exe=solver_exe,
                                        verbose=verbose, timeout=timeout)

    if "post" in steps:
        from backend.application.engineering import postprocess_case
        report["post"] = postprocess_case(cfg, workdir, geo=geo)

    if "metrics" in steps:
        from backend.application.metrics import compute_case_metrics
        report["metrics"] = compute_case_metrics(cfg, workdir, geo=geo)

    (workdir / "report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def run_step(cfg: CaseConfig, step: str, workdir: str | Path, **kw) -> None:
    run_experiment(cfg, workdir, steps=[step], **kw)
