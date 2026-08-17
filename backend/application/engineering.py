"""Automated post-processing of the SU2 solution with PyVista.

Extracts the engineering quantities used by the objective function:

* station integrals (mass flow, mass-weighted p, T, M, p0) at named planes,
* net axial force / thrust proxy by control-volume momentum balance,
* wall pressure profiles and separation (near-wall backflow) detection,
* rendered snapshots of the Mach field and streamlines.

The station-flux method is documented in docs/MODELING.md; it approximates
the flux through a plane by summing the contribution of every cell whose
bounding box crosses the plane (rho*u_x * A_cell / dx_cell per unit depth).
"""
from __future__ import annotations

import os

os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import sys
from pathlib import Path

import numpy as np

try:
    import pyvista as pv
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    pv = None
    plt = None

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.domain.geometry import build_geometry, station_x


# ---------------------------------------------------------------------------
# Solution loading and derived fields
# ---------------------------------------------------------------------------
def load_solution(cfg, workdir):
    """Read the most recent SU2 VTU solution as cell-data unstructured grid."""
    if pv is None:
        raise ImportError("pyvista is required for post-processing")
    from backend.infrastructure.su2 import locate_solution_vtu
    vtu = locate_solution_vtu(Path(workdir) / "run")
    mesh = pv.read(vtu)
    mesh = mesh.point_data_to_cell_data()
    add_derived_fields(mesh, cfg.flow)
    return mesh


def cell_array(mesh, name: str) -> np.ndarray | None:
    if name in mesh.cell_data:
        return np.asarray(mesh.cell_data[name], dtype=float)
    if name in mesh.point_data:
        return np.asarray(mesh.point_data_to_cell_data().cell_data[name], dtype=float)
    return None


def is_3d(mesh) -> bool:
    """True if the mesh has a non-zero spanwise extent (z varies)."""
    pts = np.asarray(mesh.points)
    return bool(np.any(np.abs(pts[:, 2]) > 1e-9))


def add_derived_fields(mesh, flow) -> None:
    g = flow.gamma
    p = cell_array(mesh, "Pressure")
    T = cell_array(mesh, "Temperature")
    v = cell_array(mesh, "Velocity")
    if p is None or T is None or v is None:
        raise ValueError("SU2 output missing Pressure/Temperature/Velocity arrays")
    speed = np.linalg.norm(v, axis=1)
    a = np.sqrt(g * flow.R * T)
    mach = speed / a
    p0 = p * (1.0 + 0.5 * (g - 1.0) * mach**2) ** (g / (g - 1.0))
    mesh.cell_data["Mach_derived"] = mach
    mesh.cell_data["P0"] = p0
    mesh.cell_data["Recirculation"] = (v[:, 0] < 0.0).astype(float)


# ---------------------------------------------------------------------------
# Point / line geometry helpers
# ---------------------------------------------------------------------------
def min_dist_to_polylines(pts: np.ndarray, polylines: list[list]) -> np.ndarray:
    """Distance from each point to the closest segment of any polyline (2D)."""
    from backend.infrastructure.accel import min_dist_to_polylines as _accel
    return _accel(pts, polylines)


# ---------------------------------------------------------------------------
# Station integrals
# ---------------------------------------------------------------------------
def _cell_extents(mesh):
    """Per-cell [xmin, xmax, ymin, ymax] from points + connectivity."""
    from backend.infrastructure.accel import cell_extents as _accel_extents
    conn = mesh.cell_connectivity
    offset = mesh.offset
    n = mesh.n_cells
    counts = np.diff(offset)
    cell_id = np.repeat(np.arange(n), counts)
    x = mesh.points[:, 0]
    y = mesh.points[:, 1]
    return _accel_extents(x, y, conn, cell_id, n)


def station_integrals(mesh, geo: dict, flow,
                      stations=("capture", "isolator_in", "isolator_out",
                                "combustor_in", "combustor_out", "nozzle_exit")):
    """Mass-flux-weighted flow properties at the named axial stations."""
    g = flow.gamma
    cc = mesh.cell_centers().points
    xmin, xmax, ymin, ymax = _cell_extents(mesh)
    sizes = mesh.compute_cell_sizes()
    # 2D: cell Area is the planar area (per unit span); 3D: the swept cell
    # Volume gives the flux-plane area via A_cell ~= Volume / dx.
    area = sizes["Volume"] if is_3d(mesh) else sizes["Area"]
    ux = cell_array(mesh, "Velocity")[:, 0]
    rho = cell_array(mesh, "Density")
    p = cell_array(mesh, "Pressure")
    p0 = cell_array(mesh, "P0")
    mach = cell_array(mesh, "Mach_derived")
    dx = np.maximum(xmax - xmin, 1e-12)

    out: dict = {}
    tol = 1e-6
    for name in stations:
        x = station_x(geo, name)
        cross = (xmin <= x + tol) & (xmax >= x - tol)
        n = int(cross.sum())
        if n == 0:
            out[name] = None
            continue
        flux = rho * ux * area / dx
        mdot = float(np.sum(flux[cross]))
        if mdot <= 0:
            out[name] = None
            continue
        tarr = cell_array(mesh, "Temperature")
        out[name] = {
            "x": float(x),
            "mass_flow": mdot,
            "p_massavg": float(np.sum(p[cross] * flux[cross]) / mdot),
            "T_massavg": float(np.sum(tarr[cross] * flux[cross]) / mdot),
            "M_massavg": float(np.sum(mach[cross] * flux[cross]) / mdot),
            "p0_massavg": float(np.sum(p0[cross] * flux[cross]) / mdot),
            "Vx_massavg": float(np.sum(ux[cross] * flux[cross]) / mdot),
            "height": float(ymax[cross].max() - ymin[cross].min()),
            "area": float(np.sum(area[cross] / dx[cross])),
            "n_cells": int(n),
        }
    return out


# ---------------------------------------------------------------------------
# Wall quantities
# ---------------------------------------------------------------------------
def wall_pressure_profiles(mesh, geo: dict, tol: float = 1.5e-3):
    """Pressure along the body, cowl and strut walls."""
    cc = mesh.cell_centers().points
    p = cell_array(mesh, "Pressure")
    profiles = {}
    walls = {"body": geo["lower"], "cowl": geo["upper"]}
    if geo["strut"] is not None:
        walls["strut"] = geo["strut"]
    for name, poly in walls.items():
        d = min_dist_to_polylines(cc, [poly])
        m = d < tol
        profiles[name] = {"x": cc[m, 0], "p": p[m]}
    return profiles


def separation_metrics(mesh, geo: dict, wall_prox: float = 2.0e-3):
    """Fraction of near-wall cells with backflow (u_x < 0) and its x-extent."""
    cc = mesh.cell_centers().points
    ux = cell_array(mesh, "Velocity")[:, 0]
    walls = [geo["lower"], geo["upper"]]
    if geo["strut"] is not None:
        walls.append(geo["strut"])
    d = min_dist_to_polylines(cc, walls)
    near = d < wall_prox
    if near.sum() == 0:
        return {"near_wall_cells": 0, "sep_fraction": 0.0,
                "sep_xmin": None, "sep_xmax": None, "separated": False}
    backflow = near & (ux < 0.0)
    xs = cc[backflow, 0]
    return {
        "near_wall_cells": int(near.sum()),
        "sep_fraction": float(backflow.sum() / near.sum()),
        "sep_xmin": float(xs.min()) if len(xs) else None,
        "sep_xmax": float(xs.max()) if len(xs) else None,
        "separated": bool(len(xs) > 0),
    }


def combustion_channel_metrics(mesh, geo: dict, flow):
    """Cold-flow mixing/uniformity proxy and channel-averaged state."""
    st = station_integrals(mesh, geo, flow, stations=("combustor_in", "combustor_out"))
    if st["combustor_in"] is None or st["combustor_out"] is None:
        return {"valid": False}
    min_ = st["combustor_in"]["M_massavg"]
    mout = st["combustor_out"]["M_massavg"]
    std = float(np.std(cell_array(mesh, "Mach_derived")))
    mean = float(np.mean(cell_array(mesh, "Mach_derived")))
    uniformity = 1.0 - std / max(mean, 1e-12)
    return {
        "valid": True,
        "M_combustor_in": min_,
        "M_combustor_out": mout,
        "M_ratio_out_in": mout / min_ if min_ else None,
        "Mach_uniformity": uniformity,
        "p_rise_combustor": st["combustor_out"]["p_massavg"] / st["combustor_in"]["p_massavg"]
        if st["combustor_in"]["p_massavg"] else None,
    }


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------
def _plot_2d(mesh, scalar, clim, title, out_png, cmap="jet"):
    if plt is None:
        return
    cdata = cell_array(mesh, scalar)
    cc = mesh.cell_centers().points
    fig, ax = plt.subplots(figsize=(11, 3.2))
    sc = ax.scatter(cc[:, 0], cc[:, 1], c=cdata, s=0.8, cmap=cmap, vmin=clim[0], vmax=clim[1])
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    fig.colorbar(sc, ax=ax, label=scalar)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def export_snapshots(mesh, cfg, workdir: Path, geo: dict) -> dict:
    post_dir = Path(workdir) / "post"
    post_dir.mkdir(parents=True, exist_ok=True)
    mach = cell_array(mesh, "Mach_derived")
    p = cell_array(mesh, "Pressure")
    snap = {}
    if len(mach):
        _plot_2d(mesh, "Mach_derived", (0.0, float(np.percentile(mach, 98))),
                 f"{cfg.name} -- Mach", post_dir / "mach_field.png")
        snap["mach_field"] = str(post_dir / "mach_field.png")
    if len(p):
        _plot_2d(mesh, "Pressure", (float(p.min()), float(np.percentile(p, 99))),
                 f"{cfg.name} -- Pressure [Pa]", post_dir / "pressure_field.png")
        snap["pressure_field"] = str(post_dir / "pressure_field.png")

    try:
        prof = wall_pressure_profiles(mesh, geo)
        fig, ax = plt.subplots(figsize=(9, 4))
        for name, pr in prof.items():
            if len(pr["x"]):
                ax.plot(pr["x"], pr["p"], marker=".", ms=2, label=name)
        ax.set_xlabel("x [m]"); ax.set_ylabel("wall pressure [Pa]")
        ax.set_title(f"{cfg.name} -- wall pressure"); ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(post_dir / "wall_pressure.png", dpi=150)
        plt.close(fig)
        snap["wall_pressure"] = str(post_dir / "wall_pressure.png")
    except Exception as exc:  # noqa: BLE001
        snap["wall_pressure"] = f"error: {exc}"
    return snap


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def postprocess_case(cfg, workdir, geo=None) -> dict:
    geo = geo or build_geometry(cfg.geometry)
    mesh = load_solution(cfg, workdir)
    report = {}
    report["stations"] = station_integrals(mesh, geo, cfg.flow)
    report["separation"] = separation_metrics(mesh, geo)
    report["combustor"] = combustion_channel_metrics(mesh, geo, cfg.flow)
    report["snapshots"] = export_snapshots(mesh, cfg, Path(workdir), geo)

    import json
    (Path(workdir) / "post" / "stations.json").write_text(
        json.dumps(report["stations"], indent=2, default=str), encoding="utf-8")
    return report


def main(argv=None):
    import argparse
    import json
    from backend.domain.config import load_case
    ap = argparse.ArgumentParser(description="Post-process a finished case.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow.yaml")
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args(argv)
    cfg = load_case(args.case)
    rep = postprocess_case(cfg, args.workdir)
    print(json.dumps(rep, indent=2, default=str))


if __name__ == "__main__":
    main()
