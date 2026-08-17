"""Annotated engineering schematic of the scramjet (readable by construction).

Replaces the rotating 3D volume animation with the classic, unmistakable
``side-view cutaway`` used in aerospace papers: a Mach field on the mid-span
slice, the cowl/body hardware drawn as solid metal walls, the fuel injection
strut as a solid wedge, labeled regions (inlet / isolator / combustor /
nozzle), streamlines, and a row of y-z cross-sections below the motor.

The transverse dimension is exaggerated by ``--aspect`` (default 8) so the
18:1 drag duct reads like a scramjet diagram instead of a ribbon.

Usage:
    python -m backend.interfaces.cli viz-schematic --case configs/cases/scramjet_coldflow_3d.yaml \
        --workdir runs/meu3d --aspect 8
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


def cell_array(mesh, name: str) -> np.ndarray:
    if name in mesh.cell_data:
        return np.asarray(mesh.cell_data[name], dtype=float)
    if name in mesh.point_data:
        return np.asarray(mesh.point_data_to_cell_data()[name], dtype=float)
    raise KeyError(name)


def _midspan_cells(mesh):
    cc = mesh.cell_centers().points
    z0, z1 = mesh.bounds[4], mesh.bounds[5]
    zc = 0.5 * (z0 + z1)
    sel = np.abs(cc[:, 2] - zc) < 0.35 * 0.5 * (z1 - z0)
    return cc, sel


def _streamplot(ax, mesh, S: float, n: int = 48):
    try:
        from scipy.interpolate import griddata
    except Exception:  # pragma: no cover
        return
    cc, sel = _midspan_cells(mesh)
    b = mesh.bounds
    xs, ys = cc[sel, 0], cc[sel, 1]
    vel = np.asarray(mesh.cell_data.get("Velocity",
                                        mesh.point_data.get("Velocity")), dtype=float)
    if vel.ndim == 1:
        vel = vel.reshape(-1, 3)
    u, v = vel[sel, 0], vel[sel, 1]
    gx = np.linspace(b[0], b[1], n)
    gy = np.linspace(b[2], b[3], 12)
    GX, GY = np.meshgrid(gx, gy)
    try:
        U = griddata((xs, ys), u, (GX, GY), method="linear", fill_value=0.0)
        V = griddata((xs, ys), v, (GX, GY), method="linear", fill_value=0.0)
    except Exception:  # pragma: no cover
        return
    sp = ax.streamplot(GX, GY * S, U, V * S, color="#16405f", linewidth=0.8,
                       density=1.1, arrowsize=0.7, arrowstyle="-|>",
                       broken_streamlines=False)
    if sp.lines is not None:
        sp.lines.set_alpha(0.5)


def _draw_walls(ax, geo, S: float, wall_t: float = 0.006):
    up = np.asarray(geo["upper"])
    lo = np.asarray(geo["lower"])
    ax.plot(up[:, 0], S * up[:, 1], color="#1f2b36", lw=3.4, solid_capstyle="round")
    ax.plot(lo[:, 0], S * lo[:, 1], color="#1f2b36", lw=3.4, solid_capstyle="round")
    ax.fill_between(up[:, 0], S * up[:, 1], S * (up[:, 1] + wall_t),
                    color="#9fb2bf", edgecolor="none", alpha=0.9, zorder=4)
    ax.fill_between(lo[:, 0], S * (lo[:, 1] - wall_t), S * lo[:, 1],
                    color="#9fb2bf", edgecolor="none", alpha=0.9, zorder=4)


def _draw_strut(ax, strut, S: float):
    import matplotlib.pyplot as plt
    p = np.asarray(strut)[:, :2]
    ax.add_patch(plt.Polygon(np.stack([p[:, 0], S * p[:, 1]], axis=1),
                             closed=True, facecolor="#3f4d59",
                             edgecolor="#1f2b36", lw=1.4, zorder=6))


def _annotate_regions(ax, d: dict, S: float, mach: float):
    x_in = d["x_inlet_end"]
    x_iso = d["x_isolator_end"]
    x_comb = d["x_combustor_end"]
    x_noz = d["x_total"]
    ytop = S * d["y_isolator"]
    ax.annotate(f"FREE STREAM\nM = {mach:.1f}", xy=(0.06, S * 0.099),
                xytext=(0.02, S * 0.125), fontsize=9, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="#c0392b", lw=1.8,
                                mutation_scale=16), color="#7f1d1d")
    ax.annotate("INLET\n(rampa de compressão)", xy=(0.30 * x_in, S * 0.030),
                xytext=(0.16, S * -0.055), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#1f2b36"), color="#1f2b36")
    ax.annotate("ISOLADOR", xy=(0.5 * (x_in + x_iso), ytop * 0.92),
                xytext=(0.64, ytop + S * 0.14), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#1f2b36"), color="#1f2b36")
    ax.annotate("COMBUSTOR\n(canal divergente)", xy=(0.62 * x_comb, ytop * 0.9),
                xytext=(1.03, ytop + S * 0.18), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#1f2b36"), color="#1f2b36")
    ax.annotate("NOZZLE DE\nEXPANSÃO", xy=(0.5 * (x_comb + x_noz), S * 0.048),
                xytext=(1.42, S * -0.07), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#1f2b36"), color="#1f2b36")
    if d.get("x_strut") is not None:
        ax.annotate("STRUT (injetor)", xy=(d["x_strut"], S * 0.058), xytext=(d["x_strut"],
                   ytop + S * 0.20), fontsize=9, color="#1f2b36",
                   arrowprops=dict(arrowstyle="->", color="#3f4d59", lw=1.6))


def _channel_height(geo, x: float) -> float:
    up = np.asarray(geo["upper"])[:, 1].mean()
    lo = np.asarray(geo["lower"])
    y_lo = np.interp(x, lo[:, 0], lo[:, 1])
    return float(up - y_lo)


def _cross_section(ax, H_ch: float, x_strut: float | None, span: float,
                   title: str, show_strut: bool):
    import matplotlib.pyplot as plt
    ax.set_aspect("equal")
    ax.add_patch(plt.Rectangle((0, 0), span, H_ch, facecolor="#eef3f7",
                               edgecolor="#1f2b36", lw=1.5))
    t = H_ch * 0.14
    ax.add_patch(plt.Rectangle((0, -t), span, t, facecolor="#9fb2bf", edgecolor="none"))
    ax.add_patch(plt.Rectangle((0, H_ch), span, t, facecolor="#9fb2bf", edgecolor="none"))
    if show_strut and x_strut is not None:
        th = H_ch * 0.30          # strut vertical thickness in the cut
        ax.add_patch(plt.Rectangle((0, H_ch * 0.5 - th * 0.5), span, th,
                                   facecolor="#3f4d59", edgecolor="#1f2b36", lw=1.2))
    ax.set_xlim(-0.012, span + 0.012)
    ax.set_ylim(-t * 1.6, H_ch + t * 1.6)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=7.5)


def make_schematic(cfg, workdir: Path, out: Path, *, aspect: float = 8.0,
                   scalar: str = "Mach_derived") -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from backend.infrastructure.su2 import locate_solution_vtu
    from backend.domain.geometry import build_geometry
    try:
        import pyvista as pv
        mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
        mesh = mesh.point_data_to_cell_data()
        if scalar not in mesh.cell_data:
            g, R = cfg.flow.gamma, cfg.flow.R
            p = np.asarray(mesh.cell_data["Pressure"], dtype=float)
            T = np.asarray(mesh.cell_data["Temperature"], dtype=float)
            v = np.asarray(mesh.cell_data["Velocity"], dtype=float)
            a = np.sqrt(g * R * np.abs(T))
            mesh.cell_data[scalar] = np.linalg.norm(v, axis=1) / a
    except Exception:  # pragma: no cover
        mesh = None

    geo = build_geometry(cfg.geometry)
    d = geo["derived"]
    S = float(aspect)

    fig = plt.figure(figsize=(14.5, 7.4), dpi=200)
    ax = fig.add_axes([0.07, 0.30, 0.86, 0.62])
    span = float(getattr(cfg.geometry, "span", 0.10))

    hi = 6.0
    if mesh is not None:
        cc, sel = _midspan_cells(mesh)
        vals = cell_array(mesh, scalar)[sel]
        hi = float(np.percentile(vals, 98.5))
        ax.scatter(cc[sel, 0], S * cc[sel, 1], c=vals, s=2.2, cmap="turbo",
                   vmin=0.0, vmax=hi, linewidths=0, zorder=2)
        _streamplot(ax, mesh, S)

    _draw_walls(ax, geo, S)
    if geo["strut"] is not None:
        _draw_strut(ax, geo["strut"], S)
    _annotate_regions(ax, d, S, cfg.flow.mach)

    ax.set_xlim(0.0, d["x_total"])
    ax.set_ylim(-0.34, 0.80)
    ax.set_xticks(np.arange(0.0, 1.9, 0.2))
    ax.grid(alpha=0.25)
    ax.tick_params(labelsize=9)
    ax.set_xlabel("x  [m]  ·  motor completo L = 1.82 m  ·  y exagerado ×%d" % S, fontsize=10)
    ax.set_ylabel("y [m] (esquema)", fontsize=10)
    ax.set_title(f"SCRAMJET — motor completo: campo {scalar} na seção de meia-envergadura "
                 "(fonte: SU2 RANS)", fontsize=12, fontweight="bold")

    cbax = fig.add_axes([0.955, 0.40, 0.012, 0.44])
    sm = matplotlib.cm.ScalarMappable(cmap="turbo", norm=matplotlib.colors.Normalize(0.0, hi))
    cb = fig.colorbar(sm, cax=cbax)
    cb.set_label(scalar, fontsize=10)

    # --- y-z cross-sections, spatially aligned under the motor ---
    stations = [
        (0.30, "inlet (B—B)", False),
        (0.77, "isolador (C—C)", False),
        (d.get("x_strut", 1.05), "combustor, seção do strut (D—D)", True),
        (1.55, "nozzle (E—E)", False),
    ]
    n_sec = len(stations)
    for i, (x_sec, title, show_strut) in enumerate(stations):
        H_ch = _channel_height(geo, x_sec)
        axs = fig.add_axes([0.085 + 0.205 * i, 0.045, 0.135, 0.135])
        _cross_section(axs, H_ch, d.get("x_strut"), span, title, show_strut)
        axs.text(0.5, -0.42, "y–z", ha="center", fontsize=6, color="#666")

    fig.text(0.06, 0.935,
             "Vista esquemática (transversal exagerada) · motor real: 1.82 m × 0.10 m × 0.10 m "
             "· strut: {:.1f} mm".format(cfg.geometry.strut_height * 1000),
             fontsize=8, color="#555")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def main(argv=None):
    from backend.domain.config import load_case
    ap = argparse.ArgumentParser(description="Annotated scramjet engine schematic.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow_3d.yaml")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--aspect", type=float, default=8.0)
    args = ap.parse_args(argv)

    cfg = load_case(args.case)
    wd = Path(args.workdir)
    out = Path(args.out) if args.out else wd / "post" / "scramjet_engine.png"
    png = make_schematic(cfg, wd, out, aspect=args.aspect)
    print(f"[schematic] wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())