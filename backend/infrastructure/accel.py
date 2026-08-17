"""Optional CUDA acceleration (CuPy) for the post-processing kernels.

Every kernel exposed here takes and returns *numpy* arrays, so the rest of the
pipeline never imports CuPy directly. When CuPy is importable (CUDA driver +
``cupy-cuda12x`` installed) the heavy scatter / nearest-segment work runs on
the GPU and the result is copied back to host memory; otherwise the same
vectorised numpy path is used. The numpy fallback avoids ``np.minimum.at``
(a notoriously slow Python-level scatter) in favour of a sort + ``reduceat``
reduction, which is faster even without a GPU.

Report status to the UI with :func:`info`.
"""
from __future__ import annotations

import numpy as np

try:  # pragma: no cover - depends on CUDA being installed
    import cupy as cp  # type: ignore

    _CUPY = True
    _CUPY_VERSION = getattr(cp, "__version__", "?")
    _CUPY_NAME = "cuPy"
    del cp
except Exception:  # pragma: no cover - CUDA not available
    _CUPY = False
    _CUPY_VERSION = ""
    _CUPY_NAME = ""


def available() -> bool:
    return _CUPY


def backend_name() -> str:
    return f"cupy {_CUPY_VERSION}" if _CUPY else "numpy (CPU fallback)"


def info() -> dict:
    return {
        "backend": backend_name(),
        "gpu": _CUPY,
        "cupy_version": _CUPY_VERSION if _CUPY else None,
    }


# ---------------------------------------------------------------------------
# Per-cell bounding boxes (used by the station integrals)
# ---------------------------------------------------------------------------
def _scatter_minmax_np(values: np.ndarray, ids: np.ndarray,
                       n: int, inf: float) -> tuple[np.ndarray, np.ndarray]:
    """Per-group (per id) min/max of ``values`` keyed by ``ids``.

    Faster than ``np.minimum.at``: sort by id, then reduce contiguous runs
    with ``reduceat``. Empty groups keep +/-inf.
    """
    order = np.argsort(ids, kind="stable")
    s_ids = ids[order]
    s_vals = values[order]
    bounds = np.flatnonzero(s_ids[1:] != s_ids[:-1]) + 1
    starts = np.concatenate(([0], bounds))
    ends = np.concatenate((bounds, [len(s_ids)]))
    lo = np.minimum.reduceat(s_vals, starts)
    hi = np.maximum.reduceat(s_vals, starts)
    lo_out = np.full(n, inf)
    hi_out = np.full(n, -inf)
    lo_out[s_ids[starts]] = lo
    hi_out[s_ids[starts]] = hi
    return lo_out, hi_out


def cell_extents(x: np.ndarray, y: np.ndarray, conn: np.ndarray,
                 cell_id: np.ndarray, n: int) -> tuple[np.ndarray, ...]:
    """Per-cell [xmin, xmax, ymin, ymax] from point coords + connectivity."""
    if _CUPY:  # pragma: no cover - exercised on CUDA machines
        import cupy as cp

        gx = cp.asarray(x)
        gy = cp.asarray(y)
        gid = cp.asarray(cell_id)
        gconn = cp.asarray(conn)
        xmin = cp.full(n, cp.inf)
        xmax = cp.full(n, -cp.inf)
        ymin = cp.full(n, cp.inf)
        ymax = cp.full(n, -cp.inf)
        cp.minimum.at(xmin, gid, gx[gconn])
        cp.maximum.at(xmax, gid, gx[gconn])
        cp.minimum.at(ymin, gid, gy[gconn])
        cp.maximum.at(ymax, gid, gy[gconn])
        return (cp.asnumpy(xmin), cp.asnumpy(xmax),
                cp.asnumpy(ymin), cp.asnumpy(ymax))

    xmin, xmax = _scatter_minmax_np(x[conn], cell_id, n, np.inf)
    ymin, ymax = _scatter_minmax_np(y[conn], cell_id, n, np.inf)
    return xmin, xmax, ymin, ymax


# ---------------------------------------------------------------------------
# Distance from points to the closest segment of a set of polylines (2D)
# ---------------------------------------------------------------------------
def _segments(poly: list) -> np.ndarray:
    pts = np.asarray(poly, dtype=float)
    return np.stack([pts[:-1], pts[1:]], axis=1)


def min_dist_to_polylines(pts: np.ndarray, polylines: list[list]) -> np.ndarray:
    """Distance from each point to the closest segment of any polyline."""
    pts = np.asarray(pts, dtype=float)[:, :2]
    best = np.full(len(pts), np.inf)

    if _CUPY:  # pragma: no cover - exercised on CUDA machines
        import cupy as cp

        gp = cp.asarray(pts)
        gbest = cp.full(len(pts), cp.inf)
        for poly in polylines:
            segs = _segments(poly)
            a = cp.asarray(segs[:, 0])[None, :, :]
            b = cp.asarray(segs[:, 1])[None, :, :]
            ab = b - a
            d = gp[:, None, :] - a
            t = cp.clip(
                cp.sum(d * ab, axis=2)
                / cp.maximum(cp.sum(ab * ab, axis=2), 1e-30),
                0.0, 1.0)
            proj = a + t[:, :, None] * ab
            dist = cp.linalg.norm(gp[:, None, :] - proj, axis=2)
            cp.minimum(gbest, dist.min(axis=1), out=gbest)
        return cp.asnumpy(gbest)

    for poly in polylines:
        segs = _segments(poly)
        p = np.tile(pts[:, None, :], (1, segs.shape[0], 1))
        a = segs[None, :, 0, :]
        b = segs[None, :, 1, :]
        ab = b - a
        t = np.clip(
            np.einsum("nij,nij->ni", p - a, ab)
            / np.maximum(np.einsum("nij,nij->ni", ab, ab), 1e-30),
            0.0, 1.0)
        d = np.linalg.norm(p - (a + t[..., None] * ab), axis=2)
        best = np.minimum(best, d.min(axis=1))
    return best
