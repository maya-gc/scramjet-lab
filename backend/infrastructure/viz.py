"""Shared visualization building blocks reused by the renderers.

Pure helpers shared across ``backend.interfaces.visualization``:

* ``_revolve`` / ``_annulus_disc`` / ``_toroid_band`` - revolve a 2D channel
  profile into a polygonal surface of revolution (nacelle / engine geometry);
* ``_channel_field`` - map the mid-span Mach field of an extruded 3D solution
  onto a rectangular (x, y) grid and return a point sampler;
* ``_write_gif`` - save numpy RGB frames as an animated GIF (adaptive palette);
* ``R0`` / ``RES`` - shared nacelle inner radius (m) and circumferential
  resolution for the revolved geometry.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in _sys.path:
    _sys.path.insert(0, str(_REPO))

from pathlib import Path

import numpy as np
import pyvista as pv

R0 = 0.05          # nacelle inner offset (m) -- annular duct sits on this radius
RES = 110          # circumferential resolution


def _channel_field(mesh, cfg):
    from scipy.interpolate import griddata
    cc = mesh.cell_centers().points
    b = mesh.bounds
    zc = 0.5 * (b[4] + b[5])
    sel = np.abs(cc[:, 2] - zc) < 0.4 * 0.5 * (b[5] - b[4])
    x, y = cc[sel, 0], cc[sel, 1]
    m = mesh.cell_data.get("Mach")
    if m is None:
        g, R = cfg.flow.gamma, cfg.flow.R
        T = np.asarray(mesh.cell_data["Temperature"], dtype=float)
        v = np.asarray(mesh.cell_data["Velocity"], dtype=float)
        m = np.linalg.norm(v, axis=1) / np.sqrt(g * R * np.abs(T))
    val = np.asarray(m, dtype=float)[sel]
    GX = np.linspace(b[0], b[1], 280)
    GY = np.linspace(b[2] - 1e-3, b[3] + 1e-3, 60)
    F = griddata((x, y), val, np.asarray(np.meshgrid(GX, GY)).reshape(2, -1).T,
                 method="linear", fill_value=0.0).reshape(len(GY), len(GX))

    def M(xq, yq):
        i = np.clip(np.rint((xq - b[0]) / (b[1] - b[0]) * (len(GX) - 1)).astype(int),
                    0, len(GX) - 1)
        j = np.clip(np.rint((yq - GY[0]) / (GY[-1] - GY[0]) * (len(GY) - 1)).astype(int),
                    0, len(GY) - 1)
        return float(F[j, i])

    return M, float(b[1])


def _revolve(r, xc, n: int = RES):
    xc = np.asarray(xc, dtype=float)
    r = np.asarray(r, dtype=float)
    m = len(xc)
    pts = np.empty((n * m, 3))
    for i in range(n):
        th = 2.0 * np.pi * i / n
        c, s = np.cos(th), np.sin(th)
        pts[i * m:(i + 1) * m, 0] = xc
        pts[i * m:(i + 1) * m, 1] = r * c
        pts[i * m:(i + 1) * m, 2] = r * s
    faces = []
    for i in range(n):
        for k in range(m - 1):
            a = i * m + k
            b = i * m + k + 1
            c = ((i + 1) % n) * m + k
            d = ((i + 1) % n) * m + k + 1
            faces += [4, a, b, d, c]
    pd = pv.PolyData(pts)
    pd.faces = np.asarray(faces, dtype=np.int64)
    return pd


def _annulus_disc(xi, r_in, r_out, n_r: int = 30):
    th = np.linspace(0.0, 2.0 * np.pi, RES, endpoint=False)
    r = np.linspace(r_in, r_out, n_r)
    pts = []
    for rr in r:
        for tt in th:
            pts.append([xi, rr * np.cos(tt), rr * np.sin(tt)])
    pts = np.asarray(pts)
    faces = []
    for i in range(n_r - 1):
        for j in range(RES):
            a = i * RES + j
            b = i * RES + (j + 1) % RES
            c = (i + 1) * RES + j
            d = (i + 1) * RES + (j + 1) % RES
            faces += [3, a, c, b, 3, b, c, d]
    pd = pv.PolyData(pts)
    pd.faces = np.asarray(faces, dtype=np.int64)
    return pd


def _toroid_band(xc0, r, dr, n: int = RES):
    """Raised metallic ring band on a surface (e.g. strut injection ring)."""
    x = np.array([xc0 - 0.018, xc0 - 0.006, xc0 + 0.006, xc0 + 0.018])
    rr = np.array([r, r + dr, r + dr, r])
    return _revolve(rr, x, n=n)


def _write_gif(frames, out: Path, duration_ms: int = 90):
    from PIL import Image as PImage
    pals = [PImage.fromarray(f).convert("P", palette=PImage.ADAPTIVE, colors=256)
            for f in frames]
    pals[0].save(out, save_all=True, append_images=pals[1:], duration=duration_ms,
                 loop=0, optimize=False)
