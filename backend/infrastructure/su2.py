"""Execute SU2_CFD and parse the printed residual history."""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def find_solver(exe: str | None = None) -> str:
    """Locate the SU2_CFD executable (env SU2_CFD, PATH, or explicit)."""
    if exe:
        found = shutil.which(exe) or exe
        return found
    env = os.environ.get("SU2_CFD")
    if env:
        return env
    found = shutil.which("SU2_CFD")
    if found:
        return found
    raise FileNotFoundError(
        "SU2_CFD not found. Install SU2 (https://su2code.github.io) and either "
        "add its bin/ folder to PATH or set the SU2_CFD environment variable."
    )


def run_solver_subprocess(exe: str, config_path: Path, run_dir: Path,
                          log_path: Path, verbose: bool = False,
                          timeout: float | None = None) -> int:
    """Run SU2_CFD with config_path from run_dir, streaming to log_path."""
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, str(config_path)]
    if verbose:
        print(f"[run] {' '.join(cmd)}")
    with open(log_path, "w", encoding="utf-8", errors="ignore") as out:
        proc = subprocess.run(cmd, cwd=str(run_dir), stdout=out,
                              stderr=subprocess.STDOUT, timeout=timeout)
    return proc.returncode


_RMS_COLS = re.compile(r"(rms\[[^\]]+\])", re.IGNORECASE)


def _classify_header(line: str):
    """Return (kind, header_cells) if the line is a history header, else None."""
    low = line.lower()
    if "rms[" not in low:
        return None
    if "|" in low:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        return "pipe", cells
    tokens = line.split()
    while tokens and re.match(r"^\d+:$", tokens[0]):
        tokens.pop(0)
    if not tokens:
        return None
    return "mon", tokens


def parse_su2_log(log_path: Path) -> list[dict]:
    """Parse SU2 screen history into a list of per-iteration dicts.

    Tolerant of the table layouts seen across SU2 versions:
      * classic pipe table:  ``|  Inner_Iter|  rms[Rho]| ... |``
      * v7 space table:      ``Iteration  rms[Rho] ...``
      * v8.5 monitor table:  ``NN: Outer_Iter ... rms[0] ...``
    Every row carries an ``iter`` key (the first column) plus one entry per
    parsed residual column.  Rows that fail to parse are skipped.
    """
    if not Path(log_path).exists():
        return []
    lines = Path(log_path).read_text(encoding="utf-8", errors="ignore").splitlines()
    results: list[dict] = []
    kind = None
    header: dict[str, int] = {}
    for line in lines:
        info = _classify_header(line)
        if info is not None:
            kind, cells = info
            header = {}
            for k, name in enumerate(cells):
                if "rms[" in name.lower():
                    header[name] = k
            continue
        if not header:
            continue
        if kind == "pipe":
            vals = [c.strip() for c in line.strip().strip("|").split("|")]
        else:
            vals = line.split()
            if vals and re.match(r"^\d+:$", vals[0]):
                vals = vals[1:]
            if vals and vals[0] in ("Outer_Iter", "Time_Iter", "Iteration", "Output"):
                continue
        if not vals or vals[0].startswith("+"):
            continue
        try:
            it = int(float(vals[0].replace("Iter", "").strip()))
        except ValueError:
            continue
        out = {"iter": it}
        ok = True
        for name, k in header.items():
            if k >= len(vals):
                ok = False
                break
            try:
                out[name] = float(vals[k])
            except ValueError:
                ok = False
                break
        if ok and all(v == v for v in out.values()):
            results.append(out)
    return results


def convergence_status(rows: list[dict], target: float, max_iter: int,
                       start_iter: int = 200) -> dict:
    """Summarize the run: converged / max_iter / diverged / no_history."""
    if not rows:
        return {"status": "no_history", "final_rms_density": None}
    last = rows[-1]
    rms_keys = [k for k in last if k.lower().startswith("rms[") and "rho]" in k.lower()]
    dens_key = None
    for k in rms_keys:
        if "rho]" in k.lower() and "rhou" not in k.lower() and "rhov" not in k.lower():
            dens_key = k
            break
    dens = float(last[dens_key]) if dens_key else None
    if dens is not None and (math.isnan(dens) or dens > 1e10):
        return {"status": "diverged", "final_rms_density": dens}
    late = [r for r in rows if r["iter"] >= start_iter]
    if late and dens is not None and dens < target:
        return {"status": "converged", "final_rms_density": dens}
    if last["iter"] >= max_iter:
        return {"status": "max_iter", "final_rms_density": dens}
    return {"status": "running", "final_rms_density": dens}


def run_case_stages(cfg, run_dir: Path, solver_exe: str | None = None,
                    verbose: bool = False, timeout: float | None = None) -> dict:
    """Run every generated SU2 stage sequentially in run_dir (same working
    dir so the stage-1 restart file is picked up by stage 2)."""
    from backend.infrastructure.casewriter import write_case_configs

    config_dir = run_dir.parent / "case" / "config"
    configs = sorted(config_dir.glob("*.cfg")) if config_dir.exists() else []
    if not configs:
        configs = write_case_configs(cfg, run_dir.parent / "case")

    exe = find_solver(solver_exe)
    log_summary: dict = {}
    for cfg_path in configs:
        log_file = run_dir / f"{cfg_path.stem}.log"
        rc = run_solver_subprocess(exe, cfg_path.resolve(), run_dir, log_file,
                                   verbose=verbose, timeout=timeout)
        rows = parse_su2_log(log_file)
        status = convergence_status(rows, cfg.solver.residual_target, cfg.solver.max_iter)
        log_summary[cfg_path.stem] = {
            "returncode": rc,
            "status": status["status"],
            "final_rms_density": status["final_rms_density"],
            "n_iterations": len(rows),
            "log": str(log_file),
        }
        if rc != 0:
            break
    return log_summary


def locate_solution_vtu(run_dir: Path) -> Path:
    """Find the volume solution written by SU2 in run_dir.

    SU2 writes both a volume VTK/VTU (e.g. ``vol_solution.vtk``) and a
    surface file (``surface.vtk``); only the former carries the
    cell-resolved flow field.  Prefer any ``vol*`` file, then the newest
    non-surface VTK/VTU.
    """
    candidates = sorted(run_dir.glob("*.vt*"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no *.vtk/*.vtu solution found in {run_dir}")
    for p in candidates:
        if "surface" not in p.name.lower():
            return p
    return candidates[0]
