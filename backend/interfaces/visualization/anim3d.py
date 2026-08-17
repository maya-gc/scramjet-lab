"""3D animated visualization of a solved scramjet case.

Produces a rotating GIF of the extruded (3D) solution volume:

* a clip plane slides from inlet to nozzle, revealing the interior field,
* a translucent iso-surface of the requested scalar adds a volumetric look,
* streamlines seeded at the inflow sweep through the duct,
* the physical engine is shown too: the SU2 wall surface (cowl/body/strut)
  rendered as a translucent pressure-colored skin plus an opaque solid
  strut prism extruded from the real 2D strut cross-section,
* ``--zoom <1`` frames a narrow window around the combustor/strut so the
  engine internals fill the frame instead of a thin 18:1 ribbon,
* ``--mode slice`` swaps the volume reveal for a transverse (y-z) cutting
  plane that sweeps inlet->nozzle, showing the engine cross-section
  (channel walls + central strut) like a CT scan,
* the camera orbits the domain so the (x, y, z) structure is readable.

The solution is steady (SU2 RANS restart output) so the "animation" is a
combination of camera motion + slicing travel rather than a time series.

Usage:
    python -m backend.interfaces.cli viz-anim --case configs/cases/scramjet_coldflow_3d.yaml \
        --workdir runs/meu3d --scalar Mach --level 3.0 --frames 48
    python -m backend.interfaces.cli viz-anim --case configs/cases/scramjet_coldflow_3d.yaml \
        --workdir runs/meu3d --mode slice --zoom 0.22
"""
from __future__ import annotations

import os

os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import pyvista as pv
except ImportError:  # pragma: no cover
    pv = None

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _ensure_offscreen() -> None:
    if pv is None:
        raise ImportError("pyvista is required for 3D animation")


def _is_3d(mesh) -> bool:
    pts = np.asarray(mesh.points)
    return bool(np.any(np.abs(pts[:, 2]) > 1e-9))


def _scale_pts(obj, aspect: float) -> None:
    """Stretch the transverse (y,z) display axes so the 18:1 duct reads as a
    scramjet schematic instead of a thin ribbon (aspect typical 6-10)."""
    pts = np.asarray(obj.points, dtype=float)
    pts[:, 1] *= aspect
    pts[:, 2] *= aspect
    obj.points = pts


def _to_point_data(mesh) -> None:
    """SU2 writes point arrays; if a mesh is cell-only, promote for smooth plots."""
    if mesh.point_data and not mesh.cell_data:
        return
    if not mesh.point_data and mesh.cell_data:
        mesh.point_data_to_cell_data(inplace=True)
        return
    if mesh.cell_data and not mesh.point_data:
        mesh.cell_data_to_point_data(inplace=True)


def _streamlines(mesh, scalar: str, n_seed: int = 14, step: float = 0.0035) -> pv.PolyData:
    """Seed streamlines on a plane at x=0 and trace through the duct."""
    b = mesh.bounds
    seed = pv.Plane(center=(b[0] + 1e-4, 0.05 * (b[3] - b[2]) + b[2],
                            0.5 * (b[5] - b[4]) + b[4]),
                    direction=(1, 0, 0),
                    i_size=0.9 * (b[5] - b[4]), j_size=0.9 * (b[3] - b[2]),
                    i_resolution=n_seed, j_resolution=n_seed)
    sl = mesh.streamlines_from_source(seed, vectors="Velocity",
                                      max_length=4.5 * (b[1] - b[0]),
                                      integration_direction="forward",
                                      surface_streamlines=False)
    try:
        sl = sl.sample(mesh, categorical=False)  # interpolate field (Mach...) onto lines
    except Exception:  # noqa: BLE001  -- keep uncolored lines if sampling fails
        pass
    if scalar not in sl.point_data and scalar not in sl.cell_data:
        sl.point_data[scalar] = np.zeros(sl.n_points)
    return sl


def _engine_layers(cfg, engine: str | None, workdir: Path,
                   b) -> tuple[object | None, object | None]:
    """Build the physical-engine layers: wall skin (surface.vtu) + solid strut.

    Returns ``(skin, strut)``; either may be ``None`` when unavailable.
    """
    if engine == "none":
        return None, None
    skin_path = Path(engine) if engine else Path(workdir) / "run" / "surface.vtu"
    skin = None
    if skin_path.exists():
        try:
            skin = pv.read(str(skin_path))
        except Exception:  # pragma: no cover
            skin = None
        if skin is not None and skin.n_cells:
            _to_point_data(skin)
        else:
            skin = None
    strut = None
    try:
        from backend.domain.geometry import build_geometry
        geo = build_geometry(cfg.geometry)
        pts = geo.get("strut")
        if pts is not None and len(pts) >= 3:
            P = np.asarray(pts, dtype=float)[:, :2]
            P = np.hstack([P, np.zeros((len(P), 1))])
            quad = pv.PolyData(P)
            quad.faces = np.array([len(P), *range(len(P))], dtype=np.int64)
            strut = quad.extrude((0.0, 0.0, float(b[5] - b[4])), capping=True)
    except Exception:  # pragma: no cover -- geometry is optional for animation
        strut = None
    return skin, strut


def make_animation(cfg, workdir: Path, out: Path, *, scalar: str = "Mach",
                   level: float | None = None, frames: int = 48,
                   resolution: tuple[int, int] = (1400, 800),
                   cmap: str = "turbo", op: float = 0.55,
                   engine: str | None = None, mode: str = "orbit",
                   zoom: float = 1.0, focus: float | None = None,
                   aspect: float = 1.0) -> Path:
    _ensure_offscreen()
    from backend.infrastructure.su2 import locate_solution_vtu

    mesh = pv.read(locate_solution_vtu(Path(workdir) / "run"))
    if not _is_3d(mesh):
        raise ValueError("animation requires a 3D (extruded) solution; "
                         f"'{cfg.name}' has z extent ~0")
    if aspect != 1.0:
        _scale_pts(mesh, aspect)
    _to_point_data(mesh)
    if scalar not in mesh.point_data and scalar not in mesh.cell_data:
        raise KeyError(f"scalar '{scalar}' not found in the solution VTU")

    data = mesh.point_data.get(scalar, mesh.cell_data.get(scalar))
    data = np.asarray(data, dtype=float)
    if level is None:
        hi = np.nanpercentile(data, 97.0)
        level = float(0.35 * hi)
    clim = (0.0, float(np.nanpercentile(data, 99.5)))

    b = mesh.bounds
    x0, x1 = b[0], b[1]
    iso = mesh.contour(scalars=scalar, isosurfaces=[level])
    sl = _streamlines(mesh, scalar)
    shell = mesh.extract_surface()

    cy = 0.5 * (b[2] + b[3])
    cz = 0.5 * (b[4] + b[5])
    if zoom < 1.0:
        foc_x = x0 + (x1 - x0) * (focus if focus is not None else 0.6)
        hw = 0.5 * zoom * (x1 - x0)
        wx0, wx1 = max(x0, foc_x - hw), min(x1, foc_x + hw)
        window_box = pv.Box(bounds=(wx0, wx1, b[2], b[3], b[4], b[5]))
    else:
        window_box = None
        wx0, wx1 = x0, x1

    skin, strut = _engine_layers(cfg, engine, workdir, b)
    if aspect != 1.0:
        if skin is not None:
            _scale_pts(skin, aspect)
        if strut is not None:
            _scale_pts(strut, aspect)
    skin_edges = None
    if skin is not None and skin.n_cells:
        try:
            skin_edges = skin.extract_feature_edges(
                boundary_edges=True, feature_edges=False, manifold_edges=True)
        except Exception:  # pragma: no cover
            skin_edges = None
    skin_clim: tuple[float, float] | None = None
    if skin is not None and "Pressure" in skin.point_data:
        pa = np.asarray(skin.point_data["Pressure"], dtype=float)
        skin_clim = (float(np.nanpercentile(pa, 1.0)),
                     float(np.nanpercentile(pa, 99.5)))

    pl = pv.Plotter(off_screen=True, window_size=resolution)
    pl.enable_anti_aliasing()
    pl.set_background("#dfe6ee")
    frames_imgs: list[np.ndarray] = []
    cam_p0: np.ndarray | None = None
    cam_fp: np.ndarray | None = None

    x_frac = np.linspace(0.0, 1.0, frames)
    for i in range(frames):
        az = 2.0 * np.pi * i / frames
        px = wx0 + (wx1 - wx0) * (0.02 + 0.96 * x_frac[i])
        pl.clear()
        if mode == "slice":
            cut = mesh.slice(normal=(1, 0, 0), origin=(px, cy, cz))
            if cut.n_cells:
                pl.add_mesh(cut, scalars=scalar, clim=clim, cmap=cmap,
                            show_edges=True, edge_color="#22303c", lighting=True,
                            smooth_shading=True)
        else:
            clip = mesh.clip("x", origin=(px, b[2], b[4]), invert=True, crinkle=True)
            if clip.n_cells:
                pl.add_mesh(clip, scalars=scalar, clim=clim, cmap=cmap, show_edges=False,
                            lighting=False, smooth_shading=True)
        if shell.n_points:
            pl.add_mesh(shell, color="#22303c", opacity=0.06, lighting=False,
                        label="duct surface")
        if iso.n_points:
            pl.add_mesh(iso, color="#f4f9ff", opacity=op, lighting=True,
                        label=f"iso {scalar} = {level:.2f}", smooth_shading=True)
        if sl.n_points:
            pl.add_mesh(sl, scalars=scalar, clim=clim, cmap=cmap, line_width=3.0,
                        opacity=1.0)
        if skin_edges is not None:
            pl.add_mesh(skin_edges, color="#22303c", line_width=1.6,
                        label="engine body")
        if strut is not None:
            pl.add_mesh(strut, color="#4a5b69", opacity=0.45, lighting=True,
                        smooth_shading=True, label="strut (solid)")
        if window_box is not None:
            pl.add_mesh(window_box, color="#4a5560", line_width=1)
        else:
            pl.add_mesh(mesh.outline(), color="#4a5560", line_width=1)
        if cam_p0 is None:  # auto-fit once, then orbit the fitted camera
            pl.camera_position = "iso"
            cam_p0 = np.asarray(pl.camera_position[0], dtype=float)
            cam_fp = np.asarray(pl.camera_position[1], dtype=float)
            if zoom < 1.0:  # pull the camera toward the focus -> real zoom
                cam_p0 = cam_fp + zoom * (cam_p0 - cam_fp)
        d = cam_p0 - cam_fp
        ca, sa = np.cos(az), np.sin(az)
        rot = np.array([[ca, -sa], [sa, ca]])
        new_xy = rot @ d[:2]
        pos = cam_fp + np.array([new_xy[0], new_xy[1], d[2]])
        pl.camera_position = [(float(pos[0]), float(pos[1]), float(pos[2])),
                              (float(cam_fp[0]), float(cam_fp[1]), float(cam_fp[2])),
                              (0.0, 0.0, 1.0)]
        frames_imgs.append(pl.screenshot(return_img=True)[:, :, :3].copy())
    pl.close()

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in ("", ".png"):
        out = out.with_suffix(".gif")
    _write_gif(frames_imgs, out)
    return out


def _write_gif(frames: list[np.ndarray], out: Path, duration_ms: int = 110) -> None:
    try:
        from PIL import Image
    except ImportError:
        # Pillow is the only GIF writer pulled in by matplotlib/pyvista.
        raise ImportError("Pillow is required to assemble the GIF "
                          "(pip install pillow)")
    imgs = [Image.fromarray(f) for f in frames]
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=duration_ms,
                 loop=0, optimize=True)


def main(argv=None):
    from backend.domain.config import load_case
    ap = argparse.ArgumentParser(description="Render a rotating 3D animation of a case.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow_3d.yaml")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--scalar", default="Mach")
    ap.add_argument("--level", type=float, default=None,
                    help="iso-surface value (default: 35% of the P97 field)")
    ap.add_argument("--frames", type=int, default=48)
    ap.add_argument("--opacity", type=float, default=0.55)
    ap.add_argument("--engine", default=None,
                    help="wall-surface VTU for the physical engine skin "
                         "(default: <workdir>/run/surface.vtu; 'none' to disable)")
    ap.add_argument("--mode", choices=("orbit", "slice"), default="orbit",
                    help="'orbit' reveals the volume with a sliding clip; "
                         "'slice' sweeps a transverse cross-section plane")
    ap.add_argument("--zoom", type=float, default=1.0,
                    help="fraction of the duct length framed by the camera "
                         "(<1 zooms into the window; default 1.0 = full duct)")
    ap.add_argument("--focus", type=float, default=None,
                    help="zoom focus as a fraction of duct length "
                         "(default 0.6 = combustor/strut region)")
    ap.add_argument("--aspect", type=float, default=1.0,
                    help="stretch the transverse (y,z) display axes so the "
                         "18:1 duct reads as a scramjet schematic "
                         "(typical 6-10; 1 = physical proportions)")
    args = ap.parse_args(argv)

    cfg = load_case(args.case)
    wd = Path(args.workdir)
    out = Path(args.out) if args.out else wd / "post" / "anim3d.gif"
    gif = make_animation(cfg, wd, out, scalar=args.scalar, level=args.level,
                         frames=args.frames, op=args.opacity, engine=args.engine,
                         mode=args.mode, zoom=args.zoom, focus=args.focus,
                         aspect=args.aspect)
    print(f"[anim3d] wrote {gif}")
    return 0


if __name__ == "__main__":
    sys.exit(main())