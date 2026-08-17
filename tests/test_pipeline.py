"""Pure-Python self tests (no gmsh / pyvista / SU2 required).

Run with:  python -m pytest tests -q   (or)   python tests/test_pipeline.py
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.domain.geometry import build_geometry, station_x, summary  # noqa: E402
from backend.domain.config import apply_overrides, load_case  # noqa: E402
from backend.infrastructure.casewriter import render_config  # noqa: E402


def test_load_case_defaults():
    cfg = load_case("configs/cases/scramjet_coldflow.yaml")
    assert cfg.flow.mach == 6.0
    assert cfg.geometry.contraction_ratio == 2.5
    assert cfg.solver.euler_init is True


def test_overrides():
    cfg = load_case("configs/cases/scramjet_coldflow.yaml")
    apply_overrides(cfg, ["flow.mach=5.0", "geometry.isolator_length=0.3", "solver.euler_init=false"])
    assert cfg.flow.mach == 5.0
    assert cfg.geometry.isolator_length == 0.3
    assert cfg.solver.euler_init is False


def test_geometry_consistency():
    cfg = load_case("configs/cases/scramjet_coldflow.yaml")
    geo = build_geometry(cfg.geometry)
    d = geo["derived"]
    H, H_iso = d["H_capture"], d["H_isolator"]
    # contraction ratio respected
    assert abs(H / H_iso - cfg.geometry.contraction_ratio) < 1e-9
    # ramp end height equals isolator height
    assert abs(geo["lower"][1][1] - (H - H_iso)) < 1e-12
    # cowl is flat at y = H
    assert all(abs(y - H) < 1e-12 for _, y in geo["upper"])
    # total length is the sum of the sections
    expect = geo["lower"][-1][0]
    assert abs(expect - d["x_total"]) < 1e-9
    # strut stays inside the channel
    if geo["strut"]:
        for x, y in geo["strut"]:
            assert 0.0 <= y < H
    # stations monotonic (isolator_out and combustor_in coincide by design)
    xs = [station_x(geo, s) for s in ("capture", "isolator_in", "isolator_out",
                                      "combustor_in", "combustor_out", "nozzle_exit")]
    assert all(a <= b for a, b in zip(xs, xs[1:]))
    assert xs[0] < xs[1] < xs[2] and xs[4] < xs[5]


def test_config_render():
    cfg = load_case("configs/cases/scramjet_coldflow.yaml")
    text = render_config(cfg, solver="RANS", restart=True)
    assert "SOLVER= RANS" in text
    assert "RESTART_SOL= YES" in text
    assert "RESTART_SOL= YES" in text
    assert "MACH_NUMBER= 6.000000" in text


def test_metrics_score_bounds():
    from backend.application.metrics import score
    good = {"valid": True, "pressure_recovery": 0.7, "thrust_normalized": 0.1,
            "mixing_uniformity": 0.8, "sep_fraction": 0.02, "continuity_error": 0.001,
            "unstart_risk": False}
    bad = {"valid": True, "pressure_recovery": 0.05, "thrust_normalized": -1.0,
           "mixing_uniformity": 0.2, "sep_fraction": 0.5, "continuity_error": 0.2,
           "unstart_risk": True}
    assert score(good) > score(bad)
    assert score({"valid": False}) < 0


def test_reynolds_estimate():
    cfg = load_case("configs/cases/scramjet_coldflow.yaml")
    re = cfg.flow.reynolds(1.0)
    # Mach 6, 30 km: rho*v*L/mu with L=1 m should be O(2e6)
    assert 1e6 < re < 1e7


def test_pipeline_geometry_step_only():
    """Smoke test: geometry step requires only numpy + yaml."""
    cfg = load_case("configs/cases/scramjet_coldflow.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        from backend.application.pipeline import run_experiment
        report = run_experiment(cfg, Path(tmp), steps=["geometry"])
        assert Path(tmp, "geometry", "geometry.json").exists()
        assert report["geometry_summary"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
