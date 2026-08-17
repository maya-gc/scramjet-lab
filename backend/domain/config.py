"""Case parameter model: dataclasses, YAML loading (with `include`),
and dotted-path overrides used by the CLI and the sweep/optimizer.

All units are SI. Every value has a technical default so that a case file
can be a thin layer over ``configs/base.yaml``.
"""
from __future__ import annotations

import copy
import sys as _sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in _sys.path:
    _sys.path.insert(0, str(_REPO))
REPO_ROOT = _REPO


# ---------------------------------------------------------------------------
# Parameter groups
# ---------------------------------------------------------------------------
@dataclass
class FlowParams:
    mach: float = 6.0
    p_inf: float = 1188.0
    t_inf: float = 226.5
    gamma: float = 1.4
    R: float = 287.058
    turbulence_intensity: float = 1.0e-3
    turbulence_length_scale: float = 1.0e-3

    def a_inf(self) -> float:
        return (self.gamma * self.R * self.t_inf) ** 0.5

    def v_inf(self) -> float:
        return self.mach * self.a_inf()

    def rho_inf(self) -> float:
        return self.p_inf / (self.R * self.t_inf)

    def mu_sutherland(self, T: float | None = None) -> float:
        T = self.t_inf if T is None else T
        return 1.458e-6 * T ** 1.5 / (T + 110.4)

    def reynolds(self, ref_length: float) -> float:
        rho, v, mu = self.rho_inf(), self.v_inf(), self.mu_sutherland()
        return rho * v * ref_length / mu


@dataclass
class GeometryParams:
    capture_height: float = 0.10
    span: float = 0.10                # engine span / depth [m] (3D only)
    contraction_ratio: float = 2.5
    intake_angle_deg: float = 6.0
    isolator_length: float = 0.40
    combustor_length: float = 0.25
    combustor_divergence_deg: float = 1.0
    nozzle_length: float = 0.60
    nozzle_expansion_ratio: float = 2.0
    strut_enabled: bool = True
    strut_length: float = 0.10
    strut_height: float = 0.010
    strut_pos_frac: float = 0.30


@dataclass
class MeshParams:
    h_far: float = 4.0e-3
    h_inlet: float = 2.5e-3
    h_isolator: float = 1.5e-3
    h_combustor: float = 1.2e-3
    h_nozzle: float = 2.5e-3
    h_wall_n: float = 1.0e-5
    bl_thickness: float = 8.0e-3
    bl_ratio: float = 1.15
    size_scale: float = 1.0


@dataclass
class SolverParams:
    cfl: float = 1.0
    max_iter: int = 5000
    euler_init: bool = True
    residual_target: float = 1.0e-9
    linear_solver_error: float = 1.0e-4


@dataclass
class CaseConfig:
    name: str = "scramjet_coldflow_2d"
    dimension: int = 2
    domain: str = "cold_flow"
    description: str = ""
    flow: FlowParams = field(default_factory=FlowParams)
    geometry: GeometryParams = field(default_factory=GeometryParams)
    mesh: MeshParams = field(default_factory=MeshParams)
    solver: SolverParams = field(default_factory=SolverParams)

    # ------------------------------------------------------------------
    def geometry_as_dict(self) -> dict[str, float]:
        return asdict(self.geometry)

    def flow_as_dict(self) -> dict[str, float]:
        d = asdict(self.flow)
        d["a_inf"] = self.flow.a_inf()
        d["v_inf"] = self.flow.v_inf()
        d["rho_inf"] = self.flow.rho_inf()
        return d

    def to_flat_dict(self) -> dict[str, float]:
        """Flat feature vector (geometry + flow + mesh + solver) for CSV/ML."""
        out: dict[str, float] = {}
        for group in ("flow", "geometry", "mesh", "solver"):
            for k, v in asdict(getattr(self, group)).items():
                out[f"{group}.{k}"] = float(v) if not isinstance(v, bool) else float(v)
        return out


# ---------------------------------------------------------------------------
# YAML loading with `include:` support
# ---------------------------------------------------------------------------
def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_case(path: str | Path) -> CaseConfig:
    """Load a case YAML (optionally including ``configs/base.yaml``)."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    merged: dict[str, Any] = {}
    include = data.pop("include", None)
    if include:
        include_path = (path.parent / include).resolve()
        if not include_path.exists():
            include_path = (REPO_ROOT / include).resolve()
        merged = _deep_merge(merged, yaml.safe_load(include_path.read_text(encoding="utf-8")) or {})
    merged = _deep_merge(merged, data)

    cfg = CaseConfig(
        name=merged.get("case", {}).get("name", CaseConfig().name),
        dimension=merged.get("case", {}).get("dimension", 2),
        domain=merged.get("case", {}).get("domain", "cold_flow"),
        description=merged.get("case", {}).get("description", ""),
        flow=FlowParams(**(merged.get("flow") or {})),
        geometry=GeometryParams(**(merged.get("geometry") or {})),
        mesh=MeshParams(**(merged.get("mesh") or {})),
        solver=SolverParams(**(merged.get("solver") or {})),
    )
    validate(cfg)
    return cfg


def apply_overrides(cfg: CaseConfig, overrides: list[str] | dict[str, Any]) -> CaseConfig:
    """Apply dotted-path overrides, e.g. ``geometry.isolator_length=0.30``."""
    items = overrides if isinstance(overrides, dict) else _parse_dotted(overrides)
    for key, value in items.items():
        group, _, attr = key.partition(".")
        if not hasattr(cfg, group) or not hasattr(getattr(cfg, group), attr):
            raise KeyError(f"Unknown override key: {key}")
        setattr(getattr(cfg, group), attr, value)
    validate(cfg)
    return cfg


def _parse_dotted(overrides: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in overrides:
        key, _, raw = item.partition("=")
        if not key:
            raise ValueError(f"Malformed override: {item!r}")
        out[key.strip()] = _coerce(raw)
    return out


def _coerce(raw: str):
    raw = raw.strip()
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def validate(cfg: CaseConfig) -> None:
    g = cfg.geometry
    f = cfg.flow
    if g.contraction_ratio <= 1.0:
        raise ValueError("contraction_ratio must be > 1")
    if not (1.0 < g.intake_angle_deg < 20.0):
        raise ValueError("intake_angle_deg must be in (1, 20) deg")
    if g.isolator_length <= 0 or g.combustor_length <= 0 or g.nozzle_length <= 0:
        raise ValueError("isolator/combustor/nozzle lengths must be positive")
    if g.nozzle_expansion_ratio < 1.0:
        raise ValueError("nozzle_expansion_ratio must be >= 1")
    if f.mach <= 1.0:
        raise ValueError("freestream must be supersonic (mach > 1)")
    if g.strut_enabled and g.strut_height >= g.capture_height / g.contraction_ratio:
        raise ValueError("strut_height blocks more than the whole channel")
