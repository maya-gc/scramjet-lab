"""Evaluation functions: the engineering metrics and the scalar objective.

Primary metrics (all computed from the post-processed flow field):

* mass capture / continuity         -- conservation check
* pressure recovery                 -- p0_exit / p0_capture (mass-weighted)
* static pressure rise              -- isolator compression
* thrust proxy / specific thrust    -- control-volume axial momentum balance
* nozzle momentum efficiency        -- exit flux vs ideal isentropic expansion
* mixing/uniformity proxy           -- combustor exit Mach uniformity (cold flow)
* separation fraction               -- near-wall backflow
* operating margin                  -- minimum Mach through the isolator

``score()`` turns the metric vector into a single scalar used by the
simulated-annealing optimizer (maximise).
"""
from __future__ import annotations

import json
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

from backend.domain.geometry import build_geometry


def compute_case_metrics(cfg, workdir, geo=None, post=None) -> dict:
    """Full metric vector for a finished case directory."""
    from backend.application.engineering import postprocess_case, load_solution, station_integrals

    geo = geo or build_geometry(cfg.geometry)
    post = post or postprocess_case(cfg, workdir, geo=geo)

    st = post["stations"]
    g = cfg.flow.gamma
    p_inf = cfg.flow.p_inf
    v_inf = cfg.flow.v_inf()

    m = {"case": cfg.name}
    st_in = st.get("capture")
    st_out = st.get("nozzle_exit")

    if st_in is None or st_out is None:
        m["valid"] = False
        m["error"] = "missing capture or nozzle_exit station data"
        return m
    m["valid"] = True

    # --- conservation / mass capture ------------------------------------
    mdot_in = st_in["mass_flow"]
    mdot_out = st_out["mass_flow"]
    m["mass_capture_per_m"] = mdot_in
    m["continuity_error"] = (mdot_out - mdot_in) / mdot_in

    # --- pressure recovery and compression -------------------------------
    m["pressure_recovery"] = st_out["p0_massavg"] / st_in["p0_massavg"]

    st_iso_out = st.get("isolator_out")
    m["static_pressure_rise"] = (
        st_iso_out["p_massavg"] / st_in["p_massavg"] if st_iso_out else None)

    # --- thrust proxy (control-volume momentum balance, N per span) -------
    # Fx_fluid = (mdot*Vx + p*A)_out - (mdot*Vx + p*A)_in  ;  thrust = -Fx_fluid
    d = geo["derived"]
    span_scale = d.get("B", 0.0) if cfg.dimension == 3 else 1.0
    A_in = d["H_capture"] * span_scale
    A_out = d["H_nozzle_exit"] * span_scale
    f_in = mdot_in * st_in["Vx_massavg"] + st_in["p_massavg"] * A_in
    f_out = mdot_out * st_out["Vx_massavg"] + st_out["p_massavg"] * A_out
    m["net_axial_force_on_fluid"] = f_out - f_in
    m["thrust_proxy"] = -(f_out - f_in)
    m["specific_thrust"] = m["thrust_proxy"] / mdot_in
    m["thrust_normalized"] = m["specific_thrust"] / v_inf

    # --- nozzle efficiency ------------------------------------------------
    st_noz_in = st.get("combustor_out")
    if st_noz_in and st_out and st_out["p_massavg"] > 0:
        pr = st_noz_in["p0_massavg"] / st_out["p_massavg"]
        if pr > 1.0:
            M_ideal = np.sqrt(2.0 / (g - 1.0) * (pr ** ((g - 1.0) / g) - 1.0))
            T0 = st_noz_in["T_massavg"] * (1.0 + 0.5 * (g - 1.0) * st_noz_in["M_massavg"] ** 2)
            T_ideal = T0 / (1.0 + 0.5 * (g - 1.0) * M_ideal**2)
            u_ideal = M_ideal * np.sqrt(cfg.flow.R * max(T_ideal, 0.0)) * np.sqrt(g)
            m["nozzle_momentum_eff"] = st_out["Vx_massavg"] / u_ideal
        else:
            m["nozzle_momentum_eff"] = None
    else:
        m["nozzle_momentum_eff"] = None

    # --- combustor / mixing -----------------------------------------------
    comb = post.get("combustor") or {}
    m["mixing_uniformity"] = comb.get("Mach_uniformity")
    m["M_combustor_out"] = comb.get("M_combustor_out")

    # --- separation --------------------------------------------------------
    sep = post.get("separation") or {}
    m["sep_fraction"] = sep.get("sep_fraction", 0.0)
    m["separated"] = bool(sep.get("separated", False))
    m["sep_xmin"] = sep.get("sep_xmin")
    m["sep_xmax"] = sep.get("sep_xmax")

    # --- operating margin --------------------------------------------------
    st_iso_in = st.get("isolator_in")
    if st_iso_in is not None and st_iso_out is not None:
        m["M_isolator_out"] = st_iso_out["M_massavg"]
        m["operating_margin"] = min(st_iso_in["M_massavg"], st_iso_out["M_massavg"])
        m["unstart_risk"] = bool(m["operating_margin"] < 0.6)
    else:
        m["M_isolator_out"] = None
        m["operating_margin"] = None
        m["unstart_risk"] = None

    m["M_exit"] = st_out["M_massavg"]
    m["p_exit"] = st_out["p_massavg"]

    # --- scalar objective ---------------------------------------------------
    m["score"] = score(m)
    return m


def score(m: dict) -> float:
    """Single scalar to maximise (used by the optimizer)."""
    if not m.get("valid", False):
        return -1e3
    recovery = max(0.0, min(1.0, m.get("pressure_recovery", 0.0)))
    thrust = np.clip(0.5 + 0.5 * m.get("thrust_normalized", 0.0), 0.0, 1.0)
    mixing = np.clip(m.get("mixing_uniformity") or 0.0, 0.0, 1.0)
    sep = np.clip(m.get("sep_fraction", 0.0), 0.0, 1.0)
    cont = np.clip(abs(m.get("continuity_error", 1.0)), 0.0, 1.0)
    unstart = 1.0 if m.get("unstart_risk") else 0.0
    return 100.0 * (0.40 * recovery + 0.30 * thrust + 0.15 * mixing
                    - 0.10 * sep - 0.05 * cont - 0.25 * unstart)


def write_metrics(cfg, workdir, metrics: dict) -> Path:
    out = Path(workdir) / "metrics.json"
    out.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    return out
