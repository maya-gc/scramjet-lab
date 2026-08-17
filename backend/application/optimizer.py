"""Simulated annealing / Metropolis exploration of the scramjet design space.

Each evaluation is a full CFD run (geometry -> mesh -> SU2 -> metrics). The
objective is the scalar ``score`` from backend.application.metrics. This is deliberately
derivative-free and robust to noisy/black-box objectives, which makes it a
good first optimizer before moving to gradient methods (SU2 adjoint) or a
surrogate + Bayesian loop.

Design decisions:
* per-parameter step size ~10% of the range, Gaussian proposal;
* geometric temperature schedule T = t0 * (T_final/t0)**(iter/n_iters);
* always keep the best design seen (elitist Metropolis);
* one experiment directory per evaluation for reproducibility.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

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

DEFAULT_STEPS = ["geometry", "mesh", "case", "run", "post", "metrics"]


def parse_ranges(specs: list[str]) -> dict[str, tuple[float, float]]:
    ranges: dict[str, tuple[float, float]] = {}
    for item in specs:
        key, _, raw = item.partition("=")
        lo, hi = (float(x) for x in raw.split(":"))
        ranges[key.strip()] = (lo, hi)
    return ranges


def propose(rng: random.Random, current: dict, ranges: dict,
            step_frac: float = 0.1) -> dict:
    out = {}
    for k, (lo, hi) in ranges.items():
        span = hi - lo
        val = current[k] + rng.gauss(0.0, step_frac * span)
        out[k] = min(hi, max(lo, val))
    return out


def anneal(case_path: str, ranges: dict[str, tuple[float, float]],
           workdir: str = "runs/anneal", n_iters: int = 120,
           t0: float = 10.0, t_final: float = 0.05, seed: int = 0,
           steps: list[str] | None = None,
           solver_exe: str | None = None) -> dict:
    rng = random.Random(seed)
    steps = steps or DEFAULT_STEPS
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    def evaluate(overrides: dict, exp_dir: Path):
        cfg = load_case(case_path)
        apply_overrides(cfg, overrides)
        report = run_experiment(cfg, exp_dir, steps=steps, solver_exe=solver_exe)
        m = report.get("metrics") or {}
        return m.get("score", -1e3), m, cfg

    # initial design = midpoints of the ranges
    current = {k: 0.5 * (lo + hi) for k, (lo, hi) in ranges.items()}
    cur_score, cur_metrics, _ = evaluate(current, workdir / "init")
    best, best_score, best_metrics = current.copy(), cur_score, cur_metrics

    history = []
    for i in range(n_iters):
        T = t_final + (t0 - t_final) * math.exp(-3.0 * i / n_iters)
        candidate = propose(rng, current, ranges)
        cand_score, cand_metrics, _ = evaluate(candidate, workdir / f"iter_{i:04d}")
        delta = cand_score - cur_score
        if delta >= 0 or rng.random() < math.exp(delta / T):
            current, cur_score, cur_metrics = candidate, cand_score, cand_metrics
        if cur_score > best_score:
            best, best_score, best_metrics = current.copy(), cur_score, cur_metrics

        history.append({"iter": i, "T": T, "score": cand_score,
                        "accepted": current == candidate or cand_score == cur_score,
                        "best_score": best_score, **candidate})
        if i % 10 == 0:
            print(f"[anneal] iter {i:4d}  T={T:7.3f}  score={cand_score:8.3f}  "
                  f"best={best_score:8.3f}")

    result = {
        "best_params": best,
        "best_score": best_score,
        "best_metrics": best_metrics,
        "n_evals": n_iters + 1,
    }
    append_rows([{"params": str(best), "score": best_score,
                  "metrics": str(best_metrics)}], workdir / "best.csv")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Simulated annealing over scramjet params.")
    ap.add_argument("--case", default="configs/cases/scramjet_coldflow.yaml")
    ap.add_argument("--params", nargs="*", required=True,
                    help="geometry.isolator_length=0.2:0.6 flow.mach=5.0:7.0")
    ap.add_argument("--workdir", default="runs/anneal")
    ap.add_argument("--iters", type=int, default=60)
    ap.add_argument("--t0", type=float, default=10.0)
    ap.add_argument("--t-final", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--solver-exe", default=None)
    args = ap.parse_args(argv)
    ranges = parse_ranges(args.params)
    result = anneal(args.case, ranges, args.workdir, n_iters=args.iters,
                    t0=args.t0, t_final=args.t_final, seed=args.seed,
                    solver_exe=args.solver_exe)
    print("\n==================== BEST ====================")
    for k, v in result["best_params"].items():
        print(f"{k:32s} = {v:.5f}")
    print(f"score  = {result['best_score']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
