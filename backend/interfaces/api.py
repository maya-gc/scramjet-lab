"""Programmatic facade / JSON API for building a GUI (Tk or web) on top.

Everything a front-end needs returns plain JSON-serializable dicts and
``str`` paths; no framework leakage. Render helpers load the case and
delegate to the visualization modules, returning the written output paths.
"""
from __future__ import annotations

import json
import sys as _sys
from dataclasses import asdict
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in _sys.path:
    _sys.path.insert(0, str(_REPO))

from pathlib import Path

from backend.domain.config import apply_overrides, load_case

ALL_STEPS = ["geometry", "mesh", "case", "run", "post", "metrics"]
OUT_KINDS = {".png", ".jpg", ".gif", ".csv", ".json", ".log", ".vtu",
             ".su2", ".msh", ".cfg"}


# ---------------------------------------------------------------------------
# Case / experiment introspection
# ---------------------------------------------------------------------------
def describe_case(case_path) -> dict:
    """Structured description of a case file for building a parameter editor."""
    cfg = load_case(case_path)
    return {
        "case": {"name": cfg.name, "dimension": cfg.dimension,
                 "domain": cfg.domain, "description": cfg.description},
        "groups": {g: asdict(getattr(cfg, g))
                   for g in ("flow", "geometry", "mesh", "solver")},
        "flow_derived": cfg.flow_as_dict(),
        "flat": cfg.to_flat_dict(),
    }


def run_case(case_path, workdir, *, steps=None, overrides=None, solver_exe=None,
             timeout=None, verbose=False) -> dict:
    """Run the full (or partial) pipeline and return the report dict."""
    from backend.application.pipeline import run_experiment
    cfg = load_case(case_path)
    if overrides:
        apply_overrides(cfg, overrides)
    return run_experiment(cfg, workdir, steps=steps, solver_exe=solver_exe,
                          verbose=verbose, timeout=timeout)


def _read_json(workdir, *parts):
    p = Path(workdir).joinpath(*parts)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_report(workdir):
    return _read_json(workdir, "report.json")


def load_geometry(workdir):
    return _read_json(workdir, "geometry", "geometry.json")


def load_stations(workdir):
    return _read_json(workdir, "post", "stations.json")


def load_metrics(workdir):
    report = load_report(workdir)
    if report and report.get("metrics") is not None:
        return report["metrics"]
    return _read_json(workdir, "summary.json")


def load_outputs(workdir) -> list[dict]:
    """Every browsable output file under an experiment dir (relative paths)."""
    root = Path(workdir)
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in OUT_KINDS:
            continue
        if p.suffix.lower() in (".vtu", ".su2", ".msh") and "geometry" in p.parts:
            continue
        files.append({"path": p.relative_to(root).as_posix(),
                      "size": p.stat().st_size})
    return files


def list_runs(runs_dir="runs", limit: int = 30) -> list[dict]:
    """Recent experiment directories with a quick metrics summary."""
    root = Path(runs_dir)
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir(),
                    key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
                    reverse=True):
        if not d.is_dir():
            continue
        report = _read_json(d, "report.json") or {}
        row = {"workdir": str(d), "case": report.get("case", d.name),
               "has_report": bool(report)}
        m = report.get("metrics")
        if m:
            row["metrics"] = {k: m[k] for k in
                              ("valid", "pressure_recovery", "thrust_proxy",
                               "continuity_error", "score") if k in m}
        out.append(row)
        if len(out) >= limit:
            break
    return out


def score_metrics(metrics: dict) -> float:
    from backend.application.metrics import score
    return score(metrics)


# ---------------------------------------------------------------------------
# Rendering helpers (return written file paths)
# ---------------------------------------------------------------------------
def render_schematic(case_path, workdir, out=None, aspect: float = 8.0) -> str:
    from backend.interfaces.visualization.schematic import make_schematic
    cfg = load_case(case_path)
    out = Path(out) if out else Path(workdir) / "post" / "scramjet_engine.png"
    return str(make_schematic(cfg, Path(workdir), out, aspect=aspect))


def render_engine3d(case_path, workdir, outdir=None, aspect: float = 6.0,
                    scalar: str = "Mach") -> list[str]:
    from backend.interfaces.visualization import engine3d
    cfg = load_case(case_path)
    od = Path(outdir) if outdir else Path(workdir) / "post"
    scene = engine3d.build_scene(cfg, Path(workdir), aspect=aspect, scalar=scalar)
    a = engine3d._render(scene, od / "engine3d_front.png", az=35.0)
    b = engine3d._render(scene, od / "engine3d_rear.png", az=150.0)
    return [str(a), str(b)]


def render_vehicle(case_path, workdir, outdir=None) -> list[str]:
    from backend.interfaces.visualization.vehicle import make_3d, make_side_schematic
    cfg = load_case(case_path)
    od = Path(outdir) if outdir else Path(workdir) / "post"
    a = make_side_schematic(cfg, Path(workdir), od / "scramjet_vehicle_side.png")
    b = make_3d(cfg, Path(workdir), od / "engine3d_vehicle.png")
    return [str(a), str(b)]


def render_ramjet3d(case_path, workdir, outdir=None, frames: int = 36) -> list[str]:
    from backend.interfaces.visualization.ramjet3d import render_gif, render_static
    cfg = load_case(case_path)
    od = Path(outdir) if outdir else Path(workdir) / "post"
    a = render_static(cfg, Path(workdir), od / "ramjet_cylinder.png")
    b = render_gif(cfg, Path(workdir), od / "ramjet_cylinder.gif", frames=frames)
    return [str(a), str(b)]


def render_crosssection(case_path, workdir, outdir=None, frames: int = 60) -> list[str]:
    from backend.interfaces.visualization.crosssection import (
        make_montage, make_sweep_gif, make_vector_gif)
    cfg = load_case(case_path)
    od = Path(outdir) if outdir else Path(workdir) / "post"
    a = make_montage(cfg, Path(workdir), od / "crosssection.png")
    b = make_sweep_gif(cfg, Path(workdir), od / "crosssection_sweep.gif", frames=frames)
    c = make_vector_gif(cfg, Path(workdir), od / "crosssection_vectors.gif", frames=frames)
    return [str(a), str(b), str(c)]


def render_anim3d(case_path, workdir, out=None, **opts) -> str:
    from backend.interfaces.visualization.anim3d import make_animation
    cfg = load_case(case_path)
    out = Path(out) if out else Path(workdir) / "post" / "anim3d.gif"
    return str(make_animation(cfg, Path(workdir), out, **opts))


def render_all(case_path, workdir, outdir=None, frames: int = 36) -> dict:
    """Every renderer, keyed by name (see visualizations/README)."""
    od = Path(outdir) if outdir else Path(workdir) / "post"
    return {
        "schematic": render_schematic(case_path, workdir, od / "scramjet_engine.png"),
        "engine3d": render_engine3d(case_path, workdir, od),
        "vehicle": render_vehicle(case_path, workdir, od),
        "ramjet3d": render_ramjet3d(case_path, workdir, od, frames=frames),
        "crosssection": render_crosssection(case_path, workdir, od),
        "anim3d": render_anim3d(case_path, workdir, od / "anim3d.gif"),
    }