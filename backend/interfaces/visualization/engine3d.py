"""Deterministic static 3D renders of the scramjet engine.

Builds the engines as CHUNKY, OPAQUE solids (cowl plate, body plate and the
injection strut are extruded straight from the 2D geometry), adds bright
semi-opaque Mach cut-planes at selected stations plus streamlines, and
renders fixed isometric views to high-res PNG. Everything is opaque and
bright on a light canvas so the result is readable regardless of the camera
(no GIF quantization, no translucent haze over the flow).

Usage:
    python -m backend.interfaces.cli viz-engine --case configs/cases/scramjet_coldflow_3d.yaml \
        --workdir runs/meu3d
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pyvista as pv  # noqa: E402


def _extrude_ribbon(profile, offset_y: float, span: float) -> pv.PolyData:
    """Closed polygon (profile + a copy offset in +y) extruded into a slab."""
    P = np.asarray(profile, dtype=float)[:, :2]
    ring = np.vstack([P, P + [0.0, offset_y]][::-1])
    r3 = np.hstack([ring, np.zeros((ring.shape[0], 1))])
    poly = pv.PolyData(r3)
    poly.faces = np.array([r3.shape[0], *range(r3.shape[0])], dtype=np.int64)
    return poly.extrude((0.0, 0.0, span), capping=True)


def _scale_pts(obj, aspect: float) -> None:
    p = np.asarray(obj.points, dtype=float)
    p[:, 1] *= aspect
    p[:, 2] *= aspect
    obj.points = p


def _strut_solid(geo, span: float) -> pv.PolyData | None:
    pts = geo.get("strut")
    if pts is None:
        return None
    P = np.asarray(pts, dtype=float)[:, :2]
    P = np.hstack([P, np.zeros((P.shape[0], 1))])
    q = pv.PolyData(P)
    q.faces = np.array([len(P), *range(len(P))], dtype=np.int64)
    return q.extrude((0.0, 0.0, span), capping=True)


def _streamline_lines(cfg, mesh, scalar: str, aspect: float):
    lines = []
    try:
        b = mesh.bounds
        seed = pv.Plane(center=(b[0] + 2e-4, 0.5 * (b[2] + b[3]), 0.5 * (b[4] + b[5])),
                        direction=(1, 0, 0), i_size=b[5] - b[4], j_size=b[3] - b[2],
                        i_resolution=4, j_resolution=6)
        sl = mesh.streamlines_from_source(seed, vectors="Velocity",
                                          max_length=6.0 * (b[1] - b[0]),
                                          integration_direction="forward",
                                          surface_streamlines=False)
        lines.append(sl)
    except Exception:  # pragma: no cover
        pass
    return lines


def build_scene(cfg, workdir: Path, aspect: float = 6.0, scalar: str = "Mach"):
    from backend.infrastructure.su2 import locate_solution_vtu
    from backend.domain.geometry import build_geometry

    geo = build_geometry(cfg.geometry)
    span = float(cfg.geometry.span)
    A = float(aspect)

    cowl = _extrude_ribbon(geo["upper"], +0.010, span)
    body = _extrude_ribbon(geo["lower"], -0.010, span)
    strut = _strut_solid(geo, span)
    for m in (cowl, body):
        _scale_pts(m, A)
    if strut is not None:
        _scale_pts(strut, A)
    sol = [cowl, body]
    if strut is not None:
        sol.append(strut)

    mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
    mesh = mesh.point_data_to_cell_data()
    if scalar not in mesh.cell_data:
        g, R = cfg.flow.gamma, cfg.flow.R
        T = np.asarray(mesh.cell_data["Temperature"], dtype=float)
        v = np.asarray(mesh.cell_data["Velocity"], dtype=float)
        mesh.cell_data[scalar] = np.linalg.norm(v, axis=1) / np.sqrt(g * R * np.abs(T))
    # station planes (y-z cuts), x positions of interest
    x_stations = [0.30, 0.77, geo["derived"].get("x_strut", 1.05) or 1.05, 1.21, 1.55]
    offs = np.array([[0.0, 0.0, 0.0], [0.0, -0.04, 0.03], [0.0, -0.08, 0.06],
                     [0.0, -0.12, 0.10], [0.0, -0.16, 0.13]]) * A
    ci = np.asarray(mesh.cell_data[scalar], dtype=float)
    clim = (0.0, float(np.percentile(ci, 98.5)))
    planes = []
    for i, xx in enumerate(x_stations):
        try:
            sl_p = mesh.slice(normal=(1, 0, 0), origin=(xx, 0.5 * (mesh.bounds[2] + mesh.bounds[3]),
                                                        0.5 * (mesh.bounds[4] + mesh.bounds[5])))
            _scale_pts(sl_p, A)
            if i:
                sl_p.translate(offs[i], inplace=True)
            planes.append((sl_p, xx))
        except Exception:  # pragma: no cover
            pass
    return {"solids": sol, "planes": planes, "clim": clim, "scalar": scalar,
            "geo": geo, "span": span, "A": A, "streams": _streamline_lines(cfg, mesh, scalar, A)}


def _render(scene, out: Path, az: float, el: float = 25.0, resolution=(1680, 1050)):
    pl = pv.Plotter(off_screen=True, window_size=resolution)
    pl.enable_anti_aliasing()
    pl.set_background("#eef2f5")
    for s in scene["solids"]:
        pl.add_mesh(s, color="#8fa8bb", lighting=True, smooth_shading=True,
                    show_edges=False, opacity=1.0)
    for (pln, xx) in scene["planes"]:
        if pln.n_cells:
            pl.add_mesh(pln, scalars=scene["scalar"], clim=scene["clim"], cmap="turbo",
                        opacity=0.92, show_edges=True, edge_color="#5a6b7a",
                        lighting=True, smooth_shading=True)
    for sl in scene["streams"]:
        if sl.n_points:
            pl.add_mesh(sl, color="#14b8e8", line_width=2.6, opacity=1.0)
    pl.camera_position = "iso"
    try:
        pos = np.asarray(pl.camera_position[0], dtype=float)
        foc = np.asarray(pl.camera_position[1], dtype=float)
    except Exception:  # pragma: no cover
        pl.close()
        return
    ca, sa = np.cos(np.radians(az)), np.sin(np.radians(az))
    d = pos - foc
    new_xy = np.array([[ca, -sa], [sa, ca]]) @ d[:2]
    pl.camera_position = [(float(foc[0] + new_xy[0]), float(foc[1] + new_xy[1]), float(d[2])),
                          (float(foc[0]), float(foc[1]), float(foc[2])), (0.0, 0.0, 1.0)]
    pl.add_text(f"{scene['scalar']} · cortes nas estações",
                position="upper_left", font_size=12, color="#22303c")
    img = pl.screenshot(return_img=True)[:, :, :3].copy()
    pl.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.fromarray(img).save(out)
    return out


def main(argv=None):
    from backend.domain.config import load_case
    ap = argparse.ArgumentParser(description="Static isometric 3D engine renders.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow_3d.yaml")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--aspect", type=float, default=6.0)
    ap.add_argument("--scalar", default="Mach")
    args = ap.parse_args(argv)

    cfg = load_case(args.case)
    wd = Path(args.workdir)
    od = Path(args.outdir) if args.outdir else wd / "post"
    scene = build_scene(cfg, wd, aspect=args.aspect, scalar=args.scalar)
    p1 = _render(scene, od / "engine3d_front.png", az=35.0)
    p2 = _render(scene, od / "engine3d_rear.png", az=150.0)
    print(f"[engine3d] wrote {p1}\n[engine3d] wrote {p2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())