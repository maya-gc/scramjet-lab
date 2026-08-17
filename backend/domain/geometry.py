"""Parametric 2D scramjet geometry (internal-compression channel).

Layout (x increases downstream, y upward, origin at the ramp leading edge):

    cowl  o--------------------------------------------->  (x_total, H)
    inflow|  ramp    |  isolator  |  combustor | nozzle |
    (0,0) o   ...... <>strut<>    ........     \\      o (x_total, y_exit)
          | L_inlet  | L_iso      | L_comb     | L_noz  |

The lower (body) wall carries the internal ramp that compresses the flow
from H down to H_iso = H / contraction_ratio, the constant-area isolator,
a slightly diverging combustor with an optional symmetric wedge strut, and a
single-sided expansion nozzle. The top wall (cowl) is flat.

Everything is returned as a plain dict so the mesher and the SU2 case builder
can reuse the exact same points.
"""
from __future__ import annotations

import json
import math
import sys as _sys
from dataclasses import asdict
from pathlib import Path

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in _sys.path:
    _sys.path.insert(0, str(_REPO))

from backend.domain.config import GeometryParams


def build_geometry(gp: GeometryParams) -> dict:
    H = gp.capture_height
    H_iso = H / gp.contraction_ratio
    y_iso = H - H_iso

    theta_i = math.radians(gp.intake_angle_deg)
    theta_c = math.radians(gp.combustor_divergence_deg)

    L_inlet = (H - H_iso) / math.tan(theta_i)
    x_inlet_end = L_inlet
    x_iso_end = x_inlet_end + gp.isolator_length
    x_comb_end = x_iso_end + gp.combustor_length
    x_total = x_comb_end + gp.nozzle_length

    y_comb_end = y_iso - gp.combustor_length * math.tan(theta_c)  # channel expands
    H_exit = gp.nozzle_expansion_ratio * H_iso
    y_exit = H - H_exit

    lower = [
        (0.0, 0.0),                       # ramp leading edge
        (x_inlet_end, y_iso),             # ramp end / isolator start
        (x_iso_end, y_iso),               # isolator end / combustor start
        (x_comb_end, y_comb_end),         # combustor end / nozzle start
        (x_total, y_exit),                # nozzle exit (lower lip)
    ]
    upper = [
        (0.0, H),
        (x_total, H),
    ]

    strut = None
    x_strut = None
    if gp.strut_enabled:
        x_strut = x_iso_end + gp.strut_pos_frac * gp.combustor_length
        y_comb = y_iso - (x_strut - x_iso_end) * math.tan(theta_c)
        y_mid = (H + y_comb) / 2.0
        hl = gp.strut_length / 2.0
        hh = gp.strut_height / 2.0
        strut = [
            (x_strut - hl, y_mid),
            (x_strut, y_mid + hh),
            (x_strut + hl, y_mid),
            (x_strut, y_mid - hh),
        ]

    derived = {
        "H_capture": H,
        "H_isolator": H_iso,
        "y_isolator": y_iso,
        "L_inlet": L_inlet,
        "x_inlet_end": x_inlet_end,
        "x_isolator_end": x_iso_end,
        "x_combustor_end": x_comb_end,
        "x_total": x_total,
        "H_combustor_exit": H - y_comb_end,
        "H_nozzle_exit": H_exit,
        "x_strut": x_strut,
        "L_total": x_total,
        "B": gp.span,
        "A_capture": H * gp.span,
        "A_isolator": H_iso * gp.span,
        "A_combustor_exit": (H - y_comb_end) * gp.span,
        "A_nozzle_exit": H_exit * gp.span,
    }
    return {"lower": lower, "upper": upper, "strut": strut, "derived": derived}


def station_x(geo: dict, name: str) -> float:
    """Axial location of named measurement stations."""
    d = geo["derived"]
    table = {
        "capture": 0.0,
        "isolator_in": d["x_inlet_end"],
        "isolator_out": d["x_isolator_end"],
        "combustor_in": d["x_isolator_end"],
        "combustor_out": d["x_combustor_end"],
        "nozzle_exit": d["x_total"],
    }
    if name == "strut_mid" and d.get("x_strut") is not None:
        return d["x_strut"]
    if name not in table:
        raise KeyError(f"unknown station: {name}")
    return table[name]


def write_geometry_json(geo: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geo, indent=2), encoding="utf-8")


def summary(gp: GeometryParams, geo: dict) -> str:
    d = geo["derived"]
    return (
        f"geometry: H={gp.capture_height:.3f} m  H_iso={d['H_isolator']:.4f} m  "
        f"CR={gp.contraction_ratio:.2f}  L_total={d['L_total']:.3f} m  "
        f"strut={'yes' if gp.strut_enabled else 'no'}"
    )


def geometry_params_from_geo(geo: dict) -> dict:
    """Parameter vector used for optimization / ML (includes derived values)."""
    d = geo["derived"]
    return {**d}
