"""Assemble the SU2 input deck(s) from the case parameters.

Two-stage warm start (recommended for hypersonic internal flow):
  stage 1  SOLVER=RANS  RESTART=NO   -- cheap turbulent flowfield from freestream
  stage 2  SOLVER=RANS   RESTART=YES  -- restart the same k-omega SST model

A single direct RANS run is produced when ``solver.euler_init`` is False.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.domain.config import load_case

TEMPLATE = _REPO / "configs" / "templates" / "scramjet.cfg"
REF_LENGTH = 1.0  # per-metre Reynolds reference


def build_values(cfg, solver: str, restart: bool) -> dict[str, float | int | str]:
    flow, geom, solv = cfg.flow, cfg.geometry, cfg.solver
    re_num = flow.reynolds(REF_LENGTH)
    rho = flow.rho_inf()
    v = flow.v_inf()
    nu = flow.mu_sutherland() / rho
    nut = flow.turbulence_length_scale * math.sqrt(1.5) * flow.turbulence_intensity * v
    viscous = solver == "RANS"

    dim3 = cfg.dimension == 3
    walls = "( body, cowl, strut )"
    sides = "( side )" if dim3 else None
    if viscous:
        inviscid = sides if sides is not None else "( NONE )"
        viscous_walls = walls
    else:
        inviscid = walls if sides is None else "( body, cowl, strut, side )"
        viscous_walls = "( NONE )"

    ref_area = geom.capture_height * (geom.span if dim3 else 1.0)
    # Euler cold stages run first order at a modest CFL for a robust hypersonic
    # start; the final RANS stage picks up the full scheme.
    if solver != "RANS":
        muscl = "NO"
        cfl = min(solv.cfl, 1.0)
    else:
        muscl = "NO" if not restart else "YES"
        cfl = min(solv.cfl, 0.1) if not restart else solv.cfl
    values = {
        "SOLVER": solver,
        "RESTART": "YES" if restart else "NO",
        "SOLUTION_FILE": "restart_flow" if restart else "none",
        "MACH": f"{flow.mach:.6f}",
        "P_INF": f"{flow.p_inf:.6f}",
        "T_INF": f"{flow.t_inf:.6f}",
        "GAMMA": f"{flow.gamma:.6f}",
        "R_GAS": f"{flow.R:.6f}",
        "REYNOLDS": f"{re_num:.5e}",
        "REF_LENGTH": f"{REF_LENGTH:.6f}",
        "REF_AREA": f"{ref_area:.6f}",
        "TURB_INT": f"{flow.turbulence_intensity:.6e}",
        "TURB_VR": f"{nut / nu:.6e}",
        "V_INF_X": f"{v:.6f}",
        "MESH_FILE": f"../mesh/{cfg.name}.su2",
        "INVISCID_WALL": inviscid,
        "VISCOUS_WALL": viscous_walls,
        "MUSCL": muscl,
        "CFL": f"{cfl:.3f}",
        "LINEAR_ERROR": f"{solv.linear_solver_error:.1e}",
        "RESIDUAL_TARGET": f"{math.log10(solv.residual_target):.3f}",
        "MAX_ITER": int(solv.max_iter),
    }
    return values


def render_config(cfg, solver: str = "RANS", restart: bool = False,
                  template: Path = TEMPLATE) -> str:
    """Render the .cfg text; raises if any @TOKEN@ is left unfilled."""
    text = template.read_text(encoding="utf-8")
    values = build_values(cfg, solver, restart)
    for key, val in values.items():
        text = text.replace(f"@{key}@", str(val))
    leftover = re.findall(r"@([A-Z_0-9]+)@", text)
    if leftover:
        raise ValueError(f"template tokens not filled: {sorted(set(leftover))}")
    return text


def write_case_configs(cfg, case_dir: Path) -> list[Path]:
    """Write the SU2 config(s) into case_dir/config and return the run order.

    Stale ``*.cfg`` files are removed first so previously generated (e.g.
    renamed) stages are never picked up by the runner again.
    """
    case_dir.mkdir(parents=True, exist_ok=True)
    config_dir = case_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    for stale in config_dir.glob("*.cfg"):
        stale.unlink()

    files: list[Path] = []
    if cfg.solver.euler_init:
        cfg1 = config_dir / f"{cfg.name}_stage1_warm.cfg"
        cfg1.write_text(render_config(cfg, solver="RANS", restart=False), encoding="utf-8")
        files.append(cfg1)

        cfg2 = config_dir / f"{cfg.name}_stage2_rans.cfg"
        cfg2.write_text(render_config(cfg, solver="RANS", restart=True), encoding="utf-8")
        files.append(cfg2)
    else:
        cfg1 = config_dir / f"{cfg.name}_rans.cfg"
        cfg1.write_text(render_config(cfg, solver="RANS", restart=False), encoding="utf-8")
        files.append(cfg1)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render the SU2 configuration files.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow.yaml")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    cfg = load_case(args.case)
    out = Path(args.out) if args.out else Path("runs") / cfg.name / "case"
    for f in write_case_configs(cfg, out):
        print(f"[case] wrote {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
