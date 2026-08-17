"""Cylindrical (axisymmetric) ramjet-style scramjet, detailed + animated.

The rectangular CFD flowpath is revolved around the x-axis into a nacelle
(J58/SR-71-like). The Mach field is mapped ONTO the 3D surfaces. Detailing
makes it read as a ramjet nacelle while keeping the scramjet flowpath:
spike centerbody (forebody), cowl lip ring, cowl shell, fuel-injection strut
ring, nozzle plug + colored exit disc, rear flange, and a mounting pylon
under a wing stub.

Outputs (PNG + rotating GIF, colors preserved via adaptive palette):
    ramjet_cylinder.png  - detailed static 3/4 view
    ramjet_cylinder.gif  - camera rotation animation

Usage:
    python -m backend.interfaces.cli viz-ramjet --case configs/cases/scramjet_coldflow_3d.yaml \
        --workdir runs/meu3d --frames 36
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
                                        _revolve, _toroid_band, _write_gif)


def build_scene(cfg, mesh):
    from backend.domain.geometry import build_geometry
    geo = build_geometry(cfg.geometry)
    lower = np.asarray(geo["lower"])[:, :2]
    upper = np.asarray(geo["upper"])[:, :2]
    xN = lower[-1, 0]
    d = geo["derived"]
    M, _ = _channel_field(mesh, cfg)

    def mach_on(surf):
        pts = np.asarray(surf.points)
        return np.array([M(x, np.hypot(y, z) - R0)
                         for x, y, z in pts])

    # --- spike centerbody: smooth pointed nose (forebody integrated) ---
    x_spk = np.linspace(-0.18, 0.0, 40)
    t = (x_spk + 0.18) / 0.18
    r_spk = R0 * t ** 1.75
    xs = np.concatenate([x_spk[:-1], lower[1:, 0]])
    rs = np.concatenate([r_spk[:-1], lower[1:, 1] + R0])
    cb = _revolve(rs, xs)
    cb.point_data["Mach"] = mach_on(cb)

    # --- cowl shell + cowl lip ring at the inlet ---
    xc = upper[:, 0]
    rc = upper[:, 1] + R0
    cowl = _revolve(rc, xc)
    cowl.point_data["Mach"] = mach_on(cowl)
    lip = _toroid_band(0.0, float(rc[0]), 0.012, n=RES)   # inlet cowl lip

    # --- through-flow stream surface (Mach in the duct core) ---
    xm = np.linspace(0.0, xN, 220)
    ym = 0.5 * (np.interp(xm, lower[:, 0], lower[:, 1]) +
                np.interp(xm, upper[:, 0], upper[:, 1]))
    stra = _revolve(ym + R0, xm)
    stra.point_data["Mach"] = mach_on(stra)

    # --- station annular discs ---
    x_st = [0.57, float(d.get("x_strut") or 1.05), 1.20]
    discs = []
    for xx in x_st:
        ri = np.interp(xx, lower[:, 0], lower[:, 1]) + R0
        ro = np.interp(xx, upper[:, 0], upper[:, 1]) + R0
        dsc = _annulus_disc(xx, ri, ro)
        dsc.point_data["Mach"] = mach_on(dsc)
        discs.append(dsc)

    # --- nozzle: exit annulus disc (flow) + center plug + rear flange ---
    riN = float(lower[-1, 1]) + R0
    roN = float(upper[-1, 1]) + R0
    exit_disc = _annulus_disc(xN + 0.002, riN, roN)
    exit_disc.point_data["Mach"] = mach_on(exit_disc)
    x_plug = np.linspace(xN + 0.002, xN + 0.22, 26)
    r_plug = np.linspace(riN, 0.0, 26) * 0.92
    plug = _revolve(r_plug, x_plug, n=RES)
    # rear flange on the cowl
    x_fl = np.array([xN + 0.002, xN + 0.030])
    r_fl = np.array([roN, roN + 0.010])
    flange = _revolve(r_fl, x_fl, n=RES)

    # --- fuel-injection strut ring (on the centerbody) ---
    band = None
    if d.get("x_strut"):
        x_s = float(d["x_strut"])
        ri_s = float(np.interp(x_s, lower[:, 0], lower[:, 1]) + R0)
        band = _toroid_band(x_s, ri_s, 0.006, n=RES)

    # --- engine pod context: compact dorsal pylon (ramjet nacelle mount) ---
    pylon = pv.Box(bounds=(0.55, 1.05, roN - 0.002, roN + 0.08, -0.012, 0.012))
    wing = None

    scene = {
        "centerbody": cb, "cowl": cowl, "lip": lip, "stream": stra,
        "discs": discs, "exit_disc": exit_disc, "plug": plug, "flange": flange,
        "band": band, "pylon": pylon, "wing": wing,
        "xN": xN, "lower": lower, "upper": upper, "R0": R0,
    }
    return scene


def _render_frame(scene, az, resolution, clim, text=None, zoom: float = 0.85):
    pl = pv.Plotter(off_screen=True, window_size=resolution)
    pl.enable_anti_aliasing()
    pl.set_background("#eef2f5")
    kw = dict(scalars="Mach", clim=clim, cmap="turbo",
              smooth_shading=True, show_edges=False)
    pl.add_mesh(scene["centerbody"], opacity=1.0, lighting=True, specular=0.55,
                specular_power=40, **kw)
    pl.add_mesh(scene["stream"], opacity=0.85, lighting=False, **kw)
    pl.add_mesh(scene["cowl"], opacity=0.92, lighting=True, specular=0.4,
                specular_power=20, **kw)
    for dsc in scene["discs"]:
        pl.add_mesh(dsc, opacity=0.9, **kw)
    pl.add_mesh(scene["exit_disc"], opacity=1.0, **kw)
    metal = dict(color="#6f8294", lighting=True, smooth_shading=True,
                 show_edges=False)
    for part in (scene["lip"], scene["flange"], scene["pylon"]):
        pl.add_mesh(part, opacity=1.0, specular=0.6, specular_power=40, **metal)
    if scene["band"] is not None:
        pl.add_mesh(scene["band"], color="#46525e", opacity=1.0, lighting=True,
                    smooth_shading=True, show_edges=False)
    pl.add_mesh(scene["plug"], color="#46525e", opacity=1.0, lighting=True,
                smooth_shading=True, show_edges=False)
    pl.add_mesh(pv.Line([-0.18, 0, 0], [scene["xN"] + 0.24, 0, 0]),
                color="#5a6b7a", line_width=2)

    pl.camera_position = "iso"
    try:
        pos = np.asarray(pl.camera_position[0], dtype=float)
        foc = np.asarray(pl.camera_position[1], dtype=float)
        pos = foc + zoom * (pos - foc)          # pull in -> engine fills frame
        ca, sa = np.cos(np.radians(az)), np.sin(np.radians(az))
        d0 = pos - foc
        new_xy = np.array([[ca, -sa], [sa, ca]]) @ d0[:2]
        pl.camera_position = [(float(foc[0] + new_xy[0]), float(foc[1] + new_xy[1]),
                               float(d0[2])), (float(foc[0]), float(foc[1]), float(foc[2])),
                              (0.0, 0.0, 1.0)]
    except Exception:  # pragma: no cover
        pass
    if text:
        pl.add_text(text, position="upper_left", font_size=12, color="#22303c")
    img = pl.screenshot(return_img=True)[:, :, :3]
    img = np.asarray(img).copy()
    pl.close()
    return img


def render_static(cfg, workdir: Path, out: Path, az: float = 40.0,
                  resolution=(1680, 1050)) -> Path:
    mesh = _load_mesh(Path(workdir), cfg)
    scene = build_scene(cfg, mesh)
    ci = np.asarray(scene["centerbody"].point_data["Mach"], dtype=float)
    clim = (0.0, float(np.percentile(ci, 99.0)))
    img = _render_frame(scene, az, resolution, clim,
                        text="Scramjet em nacela de ramjet — Mach sobre o corpo")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.fromarray(img).save(out)
    return out


def render_gif(cfg, workdir: Path, out: Path, frames: int = 36,
               resolution=(1500, 900)) -> Path:
    mesh = _load_mesh(Path(workdir), cfg)
    scene = build_scene(cfg, mesh)
    ci = np.asarray(scene["centerbody"].point_data["Mach"], dtype=float)
    clim = (0.0, float(np.percentile(ci, 99.0)))
    imgs = [_render_frame(scene, -40 + 360.0 * i / frames, resolution, clim,
                          text="Scramjet em nacela de ramjet — rotação") 
            for i in range(frames)]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_gif(imgs, out)
    return out


def _vtu(workdir: Path) -> str:
    from backend.infrastructure.su2 import locate_solution_vtu
    return str(locate_solution_vtu(workdir / "run"))


def _load_mesh(workdir: Path, cfg=None):
    m = pv.read(_vtu(Path(workdir)))
    if m.cell_data and not m.point_data:
        return m
    m = m.point_data_to_cell_data()
    if cfg is not None and "Mach" not in m.cell_data:
        g, R = cfg.flow.gamma, cfg.flow.R
        T = np.asarray(m.cell_data["Temperature"], dtype=float)
        v = np.asarray(m.cell_data["Velocity"], dtype=float)
        m.cell_data["Mach"] = np.linalg.norm(v, axis=1) / np.sqrt(g * R * np.abs(T))
    return m


def main(argv=None):
    from backend.domain.config import load_case
    from backend.infrastructure.su2 import locate_solution_vtu  # noqa: F401
    ap = argparse.ArgumentParser(description="Detailed cylindrical ramjet-scramjet.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow_3d.yaml")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--frames", type=int, default=36)
    args = ap.parse_args(argv)

    cfg = load_case(args.case)
    wd = Path(args.workdir)
    od = Path(args.outdir) if args.outdir else wd / "post"
    png = render_static(cfg, wd, od / "ramjet_cylinder.png")
    gif = render_gif(cfg, wd, od / "ramjet_cylinder.gif", frames=args.frames)
    print(f"[ramjet3d] wrote {png}\n[ramjet3d] wrote {gif}")
    return 0


if __name__ == "__main__":
    sys.exit(main())