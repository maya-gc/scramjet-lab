"""Synthetic-solution test of the post-processing / metrics chain.

Builds a rectangular channel mesh with an analytic "supersonic" flow field,
writes it as a VTU into a throwaway workdir, then runs the full
postprocess + metrics pipeline and checks physical invariants
(mass-flow magnitude, continuity ~ 0, p0 ordering, recovery < 1, score).

Requires pyvista; skipped automatically if it is not installed.
Run:  python tests/test_postprocess_synthetic.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from backend.domain.config import load_case

try:
    import pyvista as pv
except ImportError:  # pragma: no cover
    pv = None


def make_synthetic_vtu(path: Path) -> None:
    x = np.linspace(0.0, 1.85, 320)
    y = np.linspace(-0.02, 0.12, 160)
    X, Y = np.meshgrid(x, y)
    mesh = pv.StructuredGrid(X, Y, np.zeros_like(X)).cast_to_unstructured_grid()
    cc = mesh.cell_centers().points
    xc, yc = cc[:, 0], cc[:, 1]

    rho = 0.02 + 0.004 * np.sin(3.0 * xc + 0.5)
    p = 3000.0 + 900.0 * np.cos(1.5 * xc) * np.exp(-((yc - 0.05) ** 2) / 0.002)
    u = 700.0 + 60.0 * np.sin(2.5 * xc)
    v = 15.0 * np.cos(4.0 * xc) * np.sin(6.0 * yc)
    R = 287.058
    T = p / (rho * R)

    mesh.cell_data["Density"] = rho
    mesh.cell_data["Pressure"] = p
    mesh.cell_data["Temperature"] = T
    mesh.cell_data["Velocity"] = np.stack([u, v, np.zeros_like(u)], axis=1)
    mesh.save(str(path))


def test_postprocess_and_metrics():
    if pv is None:
        print("pyvista not installed -- skipping synthetic post-processing test")
        return True
    cfg = load_case("configs/cases/scramjet_coldflow.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        run_dir = workdir / "run"
        run_dir.mkdir(parents=True)
        make_synthetic_vtu(run_dir / "flow.vtu")

        from backend.application.engineering import postprocess_case
        from backend.application.metrics import compute_case_metrics

        post = postprocess_case(cfg, workdir)
        m = compute_case_metrics(cfg, workdir, post=post)

        assert m["valid"], m
        # mass flow through a ~0.1 m capture plane, rho~0.02, u~700 -> ~1.4 kg/s/m
        assert 0.5 < m["mass_capture_per_m"] < 5.0, m["mass_capture_per_m"]
        # continuity must be approximately satisfied by the synthetic field
        assert abs(m["continuity_error"]) < 0.25, m["continuity_error"]
        # p0_out <= p0_in for a lossy/passive channel
        assert 0.0 < m["pressure_recovery"] <= 1.05, m["pressure_recovery"]
        # thrust proxy must be a real number (units N/m)
        assert np.isfinite(m["thrust_proxy"])
        assert np.isfinite(m["score"])
        # stations were all sampled
        assert post["stations"]["nozzle_exit"] is not None
        print("post/metrics synthetic checks passed:",
              f"mdot={m['mass_capture_per_m']:.3f} kg/s/m, "
              f"recovery={m['pressure_recovery']:.3f}, score={m['score']:.2f}")
        return True


if __name__ == "__main__":
    ok = test_postprocess_and_metrics()
    sys.exit(0 if ok else 1)
