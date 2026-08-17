"""Parametric sweeps: run a batch of experiments over a parameter grid."""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backend.application.pipeline import run_experiment
from backend.domain.config import apply_overrides, load_case
from backend.infrastructure.export import append_rows, results_row

STEPS = ("geometry", "mesh", "case", "run", "post", "metrics")


def load_sweep_spec(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    base = data["base"]
    if not Path(base).exists():
        base = str(Path(path).parent / base)
    return {"base": base, **data}


def run_sweep(spec: dict, solver_exe: str | None = None, verbose: bool = False) -> Path:
    base_path = spec["base"]
    parameters: dict = spec["parameters"]
    steps = spec.get("steps", list(STEPS))
    workroot = Path(spec.get("workdir", "runs/sweep"))
    workroot.mkdir(parents=True, exist_ok=True)

    keys = list(parameters.keys())
    combos = list(itertools.product(*(parameters[k] for k in keys)))
    print(f"[sweep] {len(combos)} combinations over {keys}")

    rows = []
    for i, combo in enumerate(combos):
        overrides = dict(zip(keys, combo))
        cfg = load_case(base_path)
        apply_overrides(cfg, overrides)
        exp_dir = workroot / f"exp_{i:04d}_" + "_".join(f"{k.split('.')[-1]}={v}" for k, v in overrides.items())
        print(f"[sweep] {i + 1}/{len(combos)} -> {exp_dir.name}")
        report = run_experiment(cfg, exp_dir, steps=steps, solver_exe=solver_exe, verbose=verbose)
        metrics = report.get("metrics") or {}
        rows.append(results_row(cfg, metrics, exp_dir))

    results_csv = workroot / "results.csv"
    append_rows(rows, results_csv)
    print(f"[sweep] wrote {results_csv} ({len(rows)} rows)")
    return results_csv


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a parametric sweep of scramjet cases.")
    ap.add_argument("--config", default="configs/sweeps/sweep_isolator.yaml")
    ap.add_argument("--solver-exe", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    spec = load_sweep_spec(args.config)
    run_sweep(spec, solver_exe=args.solver_exe, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
