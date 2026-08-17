"""X-43A / Hyper-X style scramjet visualization.

The CFD duct is a bare channel, which reads like nothing. This module wraps
it in a continuous outer-mold-line (OML) vehicle profile inspired by the
Hyper-X (sharp nose, dorsal, compression forebody, cowl lip, engine duct on
the belly, expansion nozzle) and renders:

* ``scramjet_vehicle_side.png``  - annotated 2D side schematic with the Mach
  field inside the engine duct,
* ``engine3d_vehicle.png``       - 3D isometric half-cutaway (chined solid
  vehicle, flow field on the cut face, solid strut).

Curves are cubic splines through the OML control points so the silhouette is
one continuous smooth line (no disconnected shapes).

Usage:
    python -m backend.interfaces.cli viz-vehicle --case configs/cases/scramjet_coldflow_3d.yaml \
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

SCALE = 4.0  # transverse exaggeration of the vehicle profile for legibility


def build_oml(cfg) -> dict:
    """Vehicle outer mold line (x, y) polylines + the engine duct walls."""
    from scipy.interpolate import CubicSpline
    from backend.domain.geometry import build_geometry

    geo = build_geometry(cfg.geometry)
    d = geo["derived"]
    xN = d["x_total"]           # 1.821 duct length
    # --- dorsal (top) OML: sharp nose -> crest -> flat dorsal -> tail taper ---
    top_ctrl = np.array([
        (-0.42, 0.045), (-0.20, 0.118), (0.10, 0.132), (1.30, 0.132),
        (2.02, 0.118), (2.20, 0.045),
    ])
    xs = np.linspace(-0.42, 2.20, 260)
    top = np.stack([xs, CubicSpline(top_ctrl[:, 0], top_ctrl[:, 1],
                                    bc_type="natural")(xs)], axis=1)
    # --- belly (bottom) OML: nose underside -> compression wedge -> flat belly ---
    belly_ctrl = np.array([
        (-0.42, 0.045), (-0.24, 0.012), (-0.05, 0.002), (0.05, 0.0),
        (2.20, 0.0),
    ])
    xs = np.linspace(-0.42, 2.20, 260)
    belly = np.stack([xs, CubicSpline(belly_ctrl[:, 0], belly_ctrl[:, 1],
                                      bc_type="natural")(xs)], axis=1)

    # --- engine duct: the CFD domain (flat cowl top + solved lower wall) ---
    lower = np.asarray(geo["lower"])
    cowl = np.asarray(geo["upper"])
    return {"top": top, "belly": belly, "lower": lower, "cowl": cowl,
            "strut": geo.get("strut"), "d": d, "xN": xN,
            "channel_ymax": float(cowl[:, 1].mean())}


# ---------------------------------------------------------------------------
# 2D annotated side schematic
# ---------------------------------------------------------------------------
def make_side_schematic(cfg, workdir: Path, out: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch
    from backend.infrastructure.su2 import locate_solution_vtu

    oml = build_oml(cfg)
    S = SCALE
    d = oml["d"]

    try:
        import pyvista as pv
        mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
        mesh = mesh.point_data_to_cell_data()
    except Exception:  # pragma: no cover
        mesh = None

    fig, ax = plt.subplots(figsize=(14, 6.4), dpi=200)
    ax.set_facecolor("#eef2f5")

    # vehicle body (grey, smooth) between dorsal and belly OML
    body = MPath(np.vstack([oml["top"], oml["belly"][::-1]]))
    ax.add_patch(PathPatch(body, facecolor="#b9c6d0", edgecolor="#26323e", lw=2.0,
                           zorder=1))
    ax.add_patch(PathPatch(body, facecolor="none", edgecolor="none"))

    # engine duct cavity (cutout): from belly to cowl + lower wall, per x in [0, xN]
    xd = np.linspace(0.0, oml["xN"], 200)
    y_lo = np.interp(xd, oml["lower"][:, 0], oml["lower"][:, 1])
    y_up = np.interp(xd, oml["cowl"][:, 0], oml["cowl"][:, 1])
    ax.fill_between(xd, S * y_lo, S * y_up, color="#ffffff", zorder=0.5, alpha=0.55)
    ax.plot(xd, S * y_lo, color="#26323e", lw=3.0, zorder=5)
    ax.plot(xd, S * y_up, color="#26323e", lw=3.0, zorder=5)

    # cowl lip at the inlet plane (sharp leading edge of the duct top wall)
    ax.fill_between([0.0, 0.012], S * 0.0, S * cfg.geometry.capture_height,
                    color="#26323e", zorder=6)

    # Mach field inside the duct (mid-span cells), clipped to the channel
    if mesh is not None:
        cc = mesh.cell_centers().points
        z0, z1 = mesh.bounds[4], mesh.bounds[5]
        zc = 0.5 * (z0 + z1)
        sel = np.abs(cc[:, 2] - zc) < 0.35 * 0.5 * (z1 - z0)
        mval = mesh.cell_data.get("Mach")
        if mval is None:
            g, R = cfg.flow.gamma, cfg.flow.R
            T = np.asarray(mesh.cell_data["Temperature"], dtype=float)
            v = np.asarray(mesh.cell_data["Velocity"], dtype=float)
            mval = np.linalg.norm(v, axis=1) / np.sqrt(g * R * np.abs(T))
        mval = np.asarray(mval, dtype=float)[sel]
        lo = np.interp(cc[sel, 0], oml["lower"][:, 0], oml["lower"][:, 1])
        up = np.interp(cc[sel, 0], oml["cowl"][:, 0], oml["cowl"][:, 1])
        inside = (cc[sel, 1] > lo - 1e-4) & (cc[sel, 1] < up + 1e-4)
        hi = float(np.percentile(mval, 98.5))
        ax.scatter(cc[sel, 0][inside], S * cc[sel, 1][inside], c=mval[inside],
                   s=2.4, cmap="turbo", vmin=0.0, vmax=hi, linewidths=0, zorder=3)

    # strut solid
    if oml["strut"] is not None:
        p = np.asarray(oml["strut"])[:, :2]
        ax.add_patch(plt.Polygon(np.stack([p[:, 0], S * p[:, 1]], axis=1),
                                 closed=True, facecolor="#3f4d59",
                                 edgecolor="#1f2b36", lw=1.4, zorder=6))

    # station markers
    for xx, lab in [(0.30, "B"), (0.77, "C"), (d.get("x_strut") or 1.05, "D"),
                    (1.55, "E")]:
        ax.axvline(xx, color="#8fa2b0", lw=1.0, ls="--", zorder=2)
        ax.text(xx, S * 0.115, lab, fontsize=8, color="#4a5b69", ha="center")

    ax.annotate("NARIZ\n(leading edge)", xy=(-0.40, S * 0.05), xytext=(-0.52, S * 0.16),
                fontsize=9, color="#26323e",
                arrowprops=dict(arrowstyle="->", color="#26323e"))
    ax.annotate("DORSO (superfície\nsuperior do veículo)", xy=(0.90, S * 0.131),
                xytext=(0.75, S * 0.20), fontsize=9, color="#26323e",
                arrowprops=dict(arrowstyle="->", color="#26323e"))
    ax.annotate("FOREBODY\n(compressão)", xy=(-0.20, S * 0.005), xytext=(-0.30, S * -0.10),
                fontsize=9, color="#26323e",
                arrowprops=dict(arrowstyle="->", color="#26323e"))
    ax.annotate("COWL LIP\n(entrada do motor)", xy=(0.02, S * 0.085), xytext=(0.10, S * 0.18),
                fontsize=9, color="#7f1d1d", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#7f1d1d", lw=1.8))
    ax.annotate("DUTO DO MOTOR\n(scramjet embutido na barriga)", xy=(0.75, S * 0.045),
                xytext=(0.55, S * -0.08), fontsize=9, color="#26323e",
                arrowprops=dict(arrowstyle="->", color="#26323e"))
    if d.get("x_strut"):
        ax.annotate("STRUT", xy=(d["x_strut"], S * 0.059), xytext=(d["x_strut"] + 0.03, S * 0.17),
                    fontsize=9, color="#26323e",
                    arrowprops=dict(arrowstyle="->", color="#3f4d59", lw=1.6))
    ax.annotate("NOZZLE DE\nEXPANSÃO", xy=(1.72, S * 0.028), xytext=(1.62, S * -0.10),
                fontsize=9, color="#26323e",
                arrowprops=dict(arrowstyle="->", color="#26323e"))

    ax.set_xlim(-0.62, 2.30)
    ax.set_ylim(S * -0.16, S * 0.28)
    ax.set_aspect("auto")
    ax.grid(alpha=0.2)
    ax.set_xlabel("x [m]  ·  veículo esquemático ~2.6 m  ·  motor embutido L = %.2f m  ·  y ×%.0f"
                  % (oml["xN"], S), fontsize=10)
    ax.set_ylabel("y (esquema)", fontsize=10)
    ax.set_title("SCRAMJET INTEGRADO AO VEÍCULO (estilo Hyper-X / X-43A) — vista lateral",
                 fontsize=13, fontweight="bold")

    cb = fig.colorbar(matplotlib.cm.ScalarMappable(
        cmap="turbo", norm=matplotlib.colors.Normalize(0.0, 6.0)), ax=ax, shrink=0.8)
    cb.set_label("Mach", fontsize=10)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 3D half-cutaway (chined solid vehicle + flow on the cut face)
# ---------------------------------------------------------------------------
def make_3d(cfg, workdir: Path, out: Path) -> Path:
    import pyvista as pv
    from backend.infrastructure.su2 import locate_solution_vtu
    from backend.interfaces.visualization.engine3d import _strut_solid, _scale_pts

    oml = build_oml(cfg)
    span = float(cfg.geometry.span)
    A = 6.0  # transverse exaggeration applied consistently in 3D

    # chined vehicle solid: ring (dorsal + belly) extruded along z
    ring = np.vstack([oml["top"], oml["belly"][::-1]])
    ring3 = np.hstack([ring, np.zeros((ring.shape[0], 1))])
    poly = pv.PolyData(ring3)
    poly.faces = np.array([ring3.shape[0], *range(ring3.shape[0])], dtype=np.int64)
    vehicle = poly.extrude((0.0, 0.0, span), capping=True)
    _scale_pts(vehicle, A)

    # cut the vehicle at the duct mid-height -> open lower shell showing the
    # flow, with the solid cut face in the forebody/dorsal.
    y_cut = 0.045 * A
    half = vehicle.clip("y", origin=(0.0, y_cut, 0.0), invert=False)

    mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
    mesh = mesh.point_data_to_cell_data()
    if "Mach" not in mesh.cell_data:
        g, R = cfg.flow.gamma, cfg.flow.R
        T = np.asarray(mesh.cell_data["Temperature"], dtype=float)
        v = np.asarray(mesh.cell_data["Velocity"], dtype=float)
        mesh.cell_data["Mach"] = np.linalg.norm(v, axis=1) / np.sqrt(g * R * np.abs(T))
    ci = np.asarray(mesh.cell_data["Mach"], dtype=float)
    clim = (0.0, float(np.percentile(ci, 98.5)))

    pl = pv.Plotter(off_screen=True, window_size=(1680, 1050))
    pl.enable_anti_aliasing()
    pl.set_background("#eef2f5")
    pl.add_mesh(half, color="#aebbc6", lighting=True, smooth_shading=True,
                show_edges=False, opacity=1.0)
    if oml["strut"] is not None:
        st = _strut_solid(oml, span)
        _scale_pts(st, A)
        pl.add_mesh(st, color="#3f4d59", opacity=1.0, lighting=True,
                    smooth_shading=True)
    # station slices, colored, slightly translucent
    b = mesh.bounds
    for i, xx in enumerate([0.30, 0.77, oml["d"].get("x_strut") or 1.05, 1.55]):
        try:
            pln = mesh.slice(normal=(1, 0, 0), origin=(xx, 0.5 * (b[2] + b[3]), 0.5 * (b[4] + b[5])))
            _scale_pts(pln, A)
            pl.add_mesh(pln, scalars="Mach", clim=clim, cmap="turbo", opacity=0.92,
                        show_edges=True, edge_color="#5a6b7a", lighting=True,
                        smooth_shading=True)
        except Exception:  # pragma: no cover
            pass
    pl.camera_position = "iso"
    pl.add_text("Veículo estilo Hyper-X — meia-casca com campo de Mach no corte",
                position="upper_left", font_size=12, color="#22303c")
    img = pl.screenshot(return_img=True)[:, :, :3].copy()
    pl.close()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.fromarray(img).save(out)
    return out


def main(argv=None):
    from backend.domain.config import load_case
    ap = argparse.ArgumentParser(description="Hyper-X style scramjet renders.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow_3d.yaml")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args(argv)

    cfg = load_case(args.case)
    wd = Path(args.workdir)
    od = Path(args.outdir) if args.outdir else wd / "post"
    p1 = make_side_schematic(cfg, wd, od / "scramjet_vehicle_side.png")
    p2 = make_3d(cfg, wd, od / "engine3d_vehicle.png")
    print(f"[vehicle] wrote {p1}\n[vehicle] wrote {p2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())