"""Subprocess job worker.

The RPC server runs long operations (run_case, render_*) in separate
subprocesses so they can be monitored and cancelled. This module is invoked
as ``python -m backend.interfaces._jobworker <method> <jobdir>`` where
``jobdir`` contains ``params.json`` and receives ``progress.json`` /
``result.json``.

Progress for ``run_case`` is derived by the server from the experiment
workdir (filesystem artifacts + SU2 log parsing), so the worker only writes
progress for the heavy render steps.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _jsonable(obj):
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _make_progress(jobdir: Path):
    path = jobdir / "progress.json"

    def write(stage: str, message: str, progress: float | None = None):
        try:
            path.write_text(
                json.dumps({"stage": stage, "message": message,
                            "progress": progress}),
                encoding="utf-8")
        except OSError:
            pass
    return write


def dispatch(method: str, params: dict, progress) -> object:
    from backend.interfaces import api
    if method == "run_case":
        p = {"case_path": params["case_path"], "workdir": params["workdir"]}
        if params.get("steps") is not None:
            p["steps"] = params["steps"]
        if params.get("overrides"):
            p["overrides"] = params["overrides"]
        if params.get("solver_exe"):
            p["solver_exe"] = params["solver_exe"]
        if params.get("timeout") is not None:
            p["timeout"] = params["timeout"]
        return api.run_case(**p)

    if method.startswith("render_"):
        progress("render", f"rendering {method.split('_', 1)[1]}", None)
        fn = getattr(api, method)
        return _jsonable(fn(**params))

    raise ValueError(f"not a job method: {method}")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m backend.interfaces._jobworker <method> <jobdir>")
        return 2
    method, jobdir_s = sys.argv[1], sys.argv[2]
    jobdir = Path(jobdir_s)
    params = json.loads((jobdir / "params.json").read_text(encoding="utf-8"))
    progress = _make_progress(jobdir)
    try:
        result = dispatch(method, params, progress)
        (jobdir / "result.json").write_text(
            json.dumps({"result": _jsonable(result)}), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - report to caller
        (jobdir / "result.json").write_text(
            json.dumps({"error": {"type": type(exc).__name__,
                                  "message": str(exc),
                                  "traceback": traceback.format_exc()}}),
            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
