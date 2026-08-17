"""Transverse (y-z) cross-sections of the cylindrical scramjet with Mach.

Deliverables:
* ``crosssection.png`` - static montage: engine side profile with the cut
  positions + a row of face-on annular cross-sections colored by Mach.
  The inlet is unambiguously marked (red ring + arrow "ENTRADA DO MOTOR").
* ``crosssection_sweep.gif`` - animation: a transverse cutting plane sweeps
  the engine from nozzle to inlet; the cut is painted by Mach and a fixed red
  inlet ring + label stay visible.

Usage:
    python -m backend.interfaces.cli viz-crosssection --case configs/cases/scramjet_coldflow_3d.yaml \
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
from backend.infrastructure.viz import (R0, RES, _annulus_disc, _channel_field,
                                        _revolve, _toroid_band)  # noqa: E402

INLET_RGBA = "#e63946"


def _stations(xN: float, n: int = 8) -> list[float]:
    return list(np.linspace(0.03, xN - 0.03, n))


def _annulus_color_rings(ax, r_lo, r_hi, mfn, n_r: int = 22, cmap=None):
    """Face-on annulus drawn as concentric colored rings (radial Mach)."""
    import warnings
    from matplotlib import cm
    from matplotlib.patches import Wedge
    if cmap is None:
        try:  # matplotlib >= 3.9
            cmap = cm.turbo
        except AttributeError:  # pragma: no cover
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cmap = cm.get_cmap("turbo")
    rr = np.linspace(r_lo, r_hi, n_r)
    for k in range(n_r - 1):
        r0, r1 = rr[k], rr[k + 1]
        y = (r0 + r1) / 2.0 - R0                    # r -> channel y
        mval = float(mfn(0.0, y))
        ax.add_patch(Wedge((0.0, 0.0), r1, 0.0, 360.0, width=r1 - r0,
                           facecolor=cmap(mval), edgecolor="none"))
    ax.set_aspect("equal")
    ax.set_xlim(-1.12 * r_hi, 1.12 * r_hi)
    ax.set_ylim(-1.12 * r_hi, 1.12 * r_hi)
    ax.axis("off")


def build_side_profile(cfg):
    from backend.domain.geometry import build_geometry
    geo = build_geometry(cfg.geometry)
    lower = np.asarray(geo["lower"])[:, :2]
    upper = np.asarray(geo["upper"])[:, :2]
    xN = lower[-1, 0]

    x_cowl = upper[:, 0]
    x_in = np.linspace(-0.18, 0.0, 40)
    t = (x_in + 0.18) / 0.18
    r_spk = R0 * t ** 1.75
    x_cb = np.concatenate([x_in[:-1], lower[1:, 0]])
    r_cb = np.concatenate([r_spk[:-1], lower[1:, 1] + R0])
    # nozzle plug
    x_plug = np.linspace(xN + 0.002, xN + 0.22, 26)
    r_plug = np.linspace(float(lower[-1, 1]) + R0, 0.0, 26) * 0.92
    return {"xN": xN, "x_cowl": np.r_[x_cowl], "r_cowl": upper[:, 1] + R0,
            "x_cb": x_cb, "r_cb": r_cb, "x_plug": x_plug, "r_plug": r_plug}


def make_montage(cfg, workdir: Path, out: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from backend.infrastructure.su2 import locate_solution_vtu

    mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
    mesh = mesh.point_data_to_cell_data()
    mfn, xN = _channel_field(mesh, cfg)
    prof = build_side_profile(cfg)
    st = _stations(xN)
    xs_fill = np.linspace(-0.18, xN, 240)
    r_lo_f = np.interp(xs_fill, prof["x_cb"], prof["r_cb"])
    r_hi_f = np.interp(xs_fill, prof["x_cowl"], prof["r_cowl"])

    fig = plt.figure(figsize=(15.5, 7.6), dpi=190)
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.05], hspace=0.34)

    # --- top: side profile with cut positions + inlet marker ---
    ax = fig.add_subplot(gs[0])
    ax.plot(prof["x_cowl"], prof["r_cowl"], color="#26323e", lw=2.4)
    ax.plot(prof["x_cb"], prof["r_cb"], color="#26323e", lw=2.4)
    ax.plot(prof["x_plug"], prof["r_plug"], color="#26323e", lw=2.0)
    ax.fill_between(xs_fill, r_lo_f, r_hi_f, color="#dbe6ec", alpha=0.6, zorder=0)
    for i, xi in enumerate(st):
        ax.axvline(xi, color="#7f94a5", lw=1.0, ls="--")
        ax.text(xi, 0.27, chr(65 + i), fontsize=9, color="#4a5b69",
                ha="center", fontweight="bold")
    # inlet marker
    ax.annotate("ENTRADA DO MOTOR  (inlet / cowl lip)\nfluxo →",
                xy=(0.02, 0.16), xytext=(0.02, 0.24), fontsize=10,
                color=INLET_RGBA, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color=INLET_RGBA, lw=2.4,
                                mutation_scale=22))
    ax.annotate("SAÍDA (nozzle)",
                xy=(xN - 0.02, 0.10), xytext=(xN - 0.22, 0.24), fontsize=9,
                color="#26323e", arrowprops=dict(arrowstyle="->", color="#26323e"))
    ax.set_xlim(-0.22, xN + 0.26)
    ax.set_ylim(-0.05, 0.30)
    ax.grid(alpha=0.25)
    ax.set_xticks(np.arange(0.0, xN + 0.01, 0.2))
    ax.set_xlabel("x [m]  ·  nacela do scramjet (corte longitudinal do duto anular)")
    ax.set_ylabel("raio [m]")
    ax.set_title("CORTES TRANSVERSAIS (y–z) AO LONGO DO MOTOR — posições A–H",
                 fontsize=12, fontweight="bold")

    # --- bottom: face-on annular cross-sections colored by Mach ---
    mmap = plt.cm.ScalarMappable(cmap="turbo", norm=plt.Normalize(0.0, 6.0))
    for i, xi in enumerate(st):
        axs = fig.add_axes([0.025 + 0.1221 * i, 0.045, 0.095, 0.115])
        from backend.domain.geometry import build_geometry
        geo = build_geometry(cfg.geometry)
        lower = np.asarray(geo["lower"])[:, :2]
        upper = np.asarray(geo["upper"])[:, :2]
        ri = np.interp(xi, lower[:, 0], lower[:, 1]) + R0
        ro = np.interp(xi, upper[:, 0], upper[:, 1]) + R0
        _annulus_color_rings(axs, ri, ro, mfn)
        if i == 0:
            for sp in axs.spines.values():
                sp.set_edgecolor(INLET_RGBA)
                sp.set_linewidth(3)
            axs.set_title(f"A  x={xi:.2f} m — ENTRADA", fontsize=9, color=INLET_RGBA,
                          fontweight="bold")
        elif i == len(st) - 1:
            axs.set_title(f"{chr(65+i)}  x={xi:.2f} m — SAÍDA", fontsize=9)
        else:
            axs.set_title(f"{chr(65+i)}  x={xi:.2f} m", fontsize=9)
    mmap.set_array(np.array([0.0, 6.0]))
    cb = fig.colorbar(mmap, ax=ax, fraction=0.025, pad=0.02, shrink=0.7)
    cb.set_label("Mach", fontsize=10)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def _engine_shell(cfg):
    from backend.domain.geometry import build_geometry
    geo = build_geometry(cfg.geometry)
    lower = np.asarray(geo["lower"])[:, :2]
    upper = np.asarray(geo["upper"])[:, :2]
    x_cowl = upper[:, 0]
    x_in = np.linspace(-0.18, 0.0, 40)
    t = (x_in + 0.18) / 0.18
    r_spk = R0 * t ** 1.75
    x_cb = np.concatenate([x_in[:-1], lower[1:, 0]])
    r_cb = np.concatenate([r_spk[:-1], lower[1:, 1] + R0])
    return (_revolve(upper[:, 1] + R0, x_cowl, n=RES),
            _revolve(r_cb, x_cb, n=RES),
            _toroid_band(0.0, float(upper[0, 1]) + R0, 0.014, n=RES))


def _cam(pl, zoom: float = 0.85, az: float = 35.0):
    pl.camera_position = "iso"
    try:
        pos = np.asarray(pl.camera_position[0], dtype=float)
        foc = np.asarray(pl.camera_position[1], dtype=float)
        pos = foc + zoom * (pos - foc)
        d0 = pos - foc
        ca, sa = np.cos(np.radians(az)), np.sin(np.radians(az))
        new_xy = np.array([[ca, -sa], [sa, ca]]) @ d0[:2]
        pl.camera_position = [(float(foc[0] + new_xy[0]), float(foc[1] + new_xy[1]),
                               float(d0[2])), (float(foc[0]), float(foc[1]),
                               float(foc[2])), (0.0, 0.0, 1.0)]
    except Exception:  # pragma: no cover
        pass


def make_sweep_gif(cfg, workdir: Path, out: Path, frames: int = 36,
                   resolution=(1500, 900)) -> Path:
    from backend.domain.geometry import build_geometry
    from backend.infrastructure.su2 import locate_solution_vtu

    mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
    mesh = mesh.point_data_to_cell_data()
    mfn, xN = _channel_field(mesh, cfg)
    geo = build_geometry(cfg.geometry)
    lower = np.asarray(geo["lower"])[:, :2]
    upper = np.asarray(geo["upper"])[:, :2]

    shell_cowl, shell_cb, inlet_ring = _engine_shell(cfg)

    clim = (0.0, 6.0)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    imgs = []
    for i in range(frames):
        xi = xN * 0.98 - (xN * 0.96) * (i / (frames - 1))   # nozzle -> inlet
        ri = np.interp(xi, lower[:, 0], lower[:, 1]) + R0
        ro = np.interp(xi, upper[:, 0], upper[:, 1]) + R0
        cut = _annulus_disc(xi, ri, ro)
        cut.point_data["Mach"] = np.array(
            [mfn(x, np.hypot(float(y), float(z)) - R0)
             for x, y, z in np.asarray(cut.points)])
        blade = _annulus_disc(xi, 0.0, ro + 0.02, n_r=8)

        pl = pv.Plotter(off_screen=True, window_size=resolution)
        pl.enable_anti_aliasing()
        pl.set_background("#eef2f5")
        pl.add_mesh(shell_cowl, color="#c8d4de", opacity=0.55, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(shell_cb, color="#c8d4de", opacity=0.55, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(inlet_ring, color=INLET_RGBA, opacity=1.0, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(blade, color="#b6c2cc", opacity=0.72, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(cut, scalars="Mach", clim=clim, cmap="turbo", opacity=1.0,
                    lighting=True, smooth_shading=True, show_edges=False)
        _cam(pl)
        pl.add_text("ENTRADA DO MOTOR ← (anel vermelho)   |   corte transversal varrendo",
                    position="upper_left", font_size=12, color="#7f1d1d")
        img = np.asarray(pl.screenshot(return_img=True)[:, :, :3]).copy()
        pl.close()
        imgs.append(img)

    from backend.infrastructure.viz import _write_gif
    _write_gif(imgs, out)
    return out


def make_vector_gif(cfg, workdir: Path, out: Path, frames: int = 36,
                    resolution=(1500, 900), n_particles: int = 460) -> Path:
    """Animated tracer particles advected by the mesh velocity field (comet
    streaks) flowing through the translucent engine; colored cold(blue) to
    hot(red) by local temperature."""
    from backend.infrastructure.su2 import locate_solution_vtu

    mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
    mesh = mesh.point_data_to_cell_data()
    _, xN = _channel_field(mesh, cfg)
    shell_cowl, shell_cb, inlet_ring = _engine_shell(cfg)

    from backend.domain.geometry import build_geometry
    geo = build_geometry(cfg.geometry)
    lower = np.asarray(geo["lower"])[:, :2]
    upper = np.asarray(geo["upper"])[:, :2]
    xL = float(lower[-1, 0])
    xp = np.linspace(xL + 0.004, xL + 0.26, 30)
    rplug = (float(lower[-1, 1]) + R0) * (1.0 - ((xp - (xL + 0.004)) / 0.26) ** 1.6)
    plug = _revolve(np.maximum(rplug, 0.0), xp, n=RES)
    rim = _toroid_band(xL - 0.02, float(upper[-1, 1]) + R0 + 0.02, 0.016, n=RES)

    def _ring(xi, dr=0.012):
        return _toroid_band(xi, float(np.interp(xi, upper[:, 0], upper[:, 1])) + R0,
                            dr, n=RES)

    ring_iso = _ring(0.57, 0.011)
    dstr = geo["derived"]
    ring_strut = _toroid_band(float(dstr["x_strut"]),
                              float(np.interp(dstr["x_strut"], lower[:, 0],
                                              lower[:, 1])) + R0 - 0.003, 0.013)
    ring_comb = _ring(1.20, 0.011)

    btn = mesh.bounds
    cc = mesh.cell_centers().points
    zc = 0.5 * (btn[4] + btn[5])
    sel = np.abs(cc[:, 2] - zc) < 0.4 * 0.5 * (btn[5] - btn[4])
    xs0 = cc[sel, 0]
    ys0 = cc[sel, 1]
    Vc = np.asarray(mesh.cell_data["Velocity"], dtype=float)[sel]
    T0 = np.asarray(mesh.cell_data["Temperature"], dtype=float)[sel]

    from scipy.interpolate import griddata
    GX = np.linspace(btn[0], btn[1], 340)
    GY = np.linspace(btn[2] - 1e-3, btn[3] + 1e-3, 52)
    XY = np.asarray(np.meshgrid(GX, GY)).reshape(2, -1).T
    Ux = griddata((xs0, ys0), Vc[:, 0], XY, method="linear",
                  fill_value=1.0).reshape(len(GY), len(GX))
    Uy = griddata((xs0, ys0), Vc[:, 1], XY, method="linear",
                  fill_value=0.0).reshape(len(GY), len(GX))
    Tg = griddata((xs0, ys0), T0, XY, method="linear",
                  fill_value=300.0).reshape(len(GY), len(GX))
    Mach_c = (np.linalg.norm(Vc, axis=1)
              / np.sqrt(cfg.flow.gamma * cfg.flow.R * np.abs(T0)))
    Mg = griddata((xs0, ys0), Mach_c, XY, method="linear",
                  fill_value=0.0).reshape(len(GY), len(GX))
    Mh = float(np.percentile(Mg, 99))
    dx = GX[1] - GX[0]
    dy = GY[1] - GY[0]

    def _colmean(F, xi):
        i = np.clip(np.rint((xi - GX[0]) / dx).astype(int), 0, len(GX) - 1)
        return float(F[:, i].mean())

    UINF = _colmean(Ux, 0.04)                 # freestream entering the inlet
    UEXT = _colmean(Ux, btn[1] - 0.04)        # exhaust leaving the nozzle
    MEXT = _colmean(Mg, btn[1] - 0.04)

    def sample(P):
        ix = np.clip(np.rint((P[:, 0] - GX[0]) / dx).astype(int), 0, len(GX) - 1)
        iy = np.clip(np.rint((P[:, 1] - GY[0]) / dy).astype(int), 0, len(GY) - 1)
        ux = np.array(Ux[iy, ix], copy=True)
        uy = np.array(Uy[iy, ix], copy=True)
        mm = np.array(Mg[iy, ix], copy=True)
        lo = P[:, 0] < GX[0]
        if lo.any():
            ux[lo] = UINF
            uy[lo] = 0.0
            mm[lo] = 0.0
        hi = P[:, 0] > GX[-1]
        if hi.any():
            ux[hi] = UEXT
            uy[hi] = 0.0
            mm[hi] = MEXT
        return ux, uy, mm

    n_strand = 9
    per = int(np.ceil(n_particles / n_strand))
    th_all = ((2.0 * np.pi / n_strand)
              * np.repeat(np.arange(n_strand), per)[:n_particles])
    rng = np.random.default_rng(7)
    nP = n_particles
    x_beg, x_end = -0.55, float(btn[1]) + 0.60
    P = np.zeros((nP, 2))
    P[:, 0] = rng.uniform(x_beg, x_end, nP)   # upstream of inlet -> past nozzle
    P[:, 1] = rng.uniform(0.012, 0.092, nP)
    dt_sub = 1.05e-4                              # per-substep (10x faster)
    NSUB = 24                                     # substeps per frame
    H = NSUB                                      # hist sampled each substep
    hist = np.repeat(P[:, None, :], H, axis=1)    # polyline follows duct curvature
    climM = (0.0, Mh)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    imgs = []
    for i in range(frames):
        for _ in range(NSUB):
            u1x, u1y, _ = sample(P)
            M = np.column_stack([P[:, 0] + 0.5 * dt_sub * u1x,
                                 P[:, 1] + 0.5 * dt_sub * u1y])
            u2x, u2y, _ = sample(M)
            P[:, 0] += dt_sub * u2x
            P[:, 1] += dt_sub * u2y
            wrap = P[:, 0] > x_end
            nw = int(wrap.sum())
            if nw:
                P[wrap, 0] = rng.uniform(x_beg, x_beg + 0.08, nw)
                P[wrap, 1] = rng.uniform(0.012, 0.092, nw)
                hist[wrap] = np.repeat(P[wrap][:, None, :], H, axis=1)
            P[:, 1] = np.clip(P[:, 1], 0.004, 0.096)
            hist[:, 1:] = hist[:, :-1]           # shift history each substep
            hist[:, 0] = P
        Ms_all = sample(np.column_stack([hist[:, :, 0].ravel(),
                                         hist[:, :, 1].ravel()]))[2]
        xp = hist[:, :, 0].ravel()
        yp = hist[:, :, 1].ravel()
        thp = np.repeat(th_all, H)
        rp = R0 + yp
        XYZ = np.column_stack([xp, rp * np.cos(thp), rp * np.sin(thp)])
        cells = []
        for k in range(nP):
            cells += [H] + list(range(k * H, (k + 1) * H))
        lc = pv.PolyData(XYZ, lines=np.asarray(cells, dtype=np.int64))
        lc.point_data["M"] = Ms_all
        lc.set_active_scalars("M")
        head = pv.PolyData(np.column_stack(
            [P[:, 0], (R0 + P[:, 1]) * np.cos(th_all),
             (R0 + P[:, 1]) * np.sin(th_all)]))
        head.point_data["M"] = Ms_all[::H]
        head.set_active_scalars("M")

        pl = pv.Plotter(off_screen=True, window_size=resolution)
        pl.enable_anti_aliasing()
        pl.set_background("#eef2f5")
        pl.add_mesh(shell_cowl, color="#c8d4de", opacity=0.42, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(shell_cb, color="#c8d4de", opacity=0.42, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(plug, color="#aeb9c4", opacity=0.35, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(rim, color="#aeb9c4", opacity=0.50, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(ring_iso, color="#aeb9c4", opacity=0.45, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(ring_strut, color="#aeb9c4", opacity=0.45, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(ring_comb, color="#aeb9c4", opacity=0.45, lighting=True,
                    smooth_shading=True, show_edges=False)
        pl.add_mesh(inlet_ring, color=INLET_RGBA, opacity=1.0, lighting=True,
                    smooth_shading=True, show_edges=False)
        _cam(pl)
        pl.add_mesh(lc, scalars="M", cmap="turbo", clim=climM,
                    opacity=0.95, lighting=True)
        pl.add_mesh(head, scalars="M", cmap="turbo", clim=climM,
                    render_points_as_spheres=True, point_size=12)
        img = np.asarray(pl.screenshot(return_img=True)[:, :, :3]).copy()
        pl.close()
        imgs.append(img)

    from backend.infrastructure.viz import _write_gif
    _write_gif(imgs, out, duration_ms=16)      # ~60 fps
    return out


def main(argv=None):
    from backend.domain.config import load_case
    ap = argparse.ArgumentParser(description="Transverse cross-sections (Mach).")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow_3d.yaml")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--frames", type=int, default=60)
    args = ap.parse_args(argv)

    cfg = load_case(args.case)
    wd = Path(args.workdir)
    od = Path(args.outdir) if args.outdir else wd / "post"
    png = make_montage(cfg, wd, od / "crosssection.png")
    gif = make_sweep_gif(cfg, wd, od / "crosssection_sweep.gif", frames=args.frames)
    vgif = make_vector_gif(cfg, wd, od / "crosssection_vectors.gif", frames=args.frames)
    print(f"[crosssection] wrote {png}\n[crosssection] wrote {gif}"
          f"\n[crosssection] wrote {vgif}")
    return 0


if __name__ == "__main__":
    sys.exit(main())