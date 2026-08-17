"""Localhost JSON-RPC server (stdlib only) exposing backend.interfaces.api.

The Electron GUI spawns this as a child process::

    python -m backend.interfaces.server

On startup the server prints two handshake lines on stdout::

    SCRAMJET_SERVER_URL=http://127.0.0.1:<port>
    SCRAMJET_TOKEN=<token>

Every request must include ``Authorization: Bearer <token>``. The server
binds loopback only and whitelists methods 1:1 against the application API.

Long-running operations (``run_case``, ``render_*``) run in subprocess
workers so they can be cancelled and polled via ``job_status``.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

MAX_BODY = 1 << 20  # 1 MiB
_POLL_INTERVAL = 0.25

# Weight of each pipeline step relative to a full run (used for progress).
_STEP_WEIGHT = {"geometry": 0.06, "mesh": 0.09, "case": 0.03,
                "run": 0.74, "post": 0.05, "metrics": 0.03}

SYNC_METHODS = {
    "health", "describe_case", "list_cases", "validate",
    "load_report", "load_geometry", "load_stations", "load_metrics",
    "load_outputs", "list_runs", "score_metrics",
    "job_status", "job_list", "job_cancel",
}
JOB_METHODS = {"run_case", "render_schematic", "render_engine3d",
               "render_vehicle", "render_ramjet3d", "render_crosssection",
               "render_anim3d", "render_all"}


def resolve_case(case_path) -> Path:
    """Resolve a user-supplied case identifier to an existing YAML path."""
    p = Path(str(case_path))
    if not p.suffix:
        p = p.with_suffix(".yaml")
    if p.is_absolute():
        cand = p
    elif p.parent == Path("."):
        cand = _REPO / "configs" / "cases" / p.name
    else:
        cand = _REPO / p
    if not cand.exists():
        raise ValueError(f"case not found: {case_path}")
    return cand.resolve()


# ---------------------------------------------------------------------------
# Sync (fast) RPC methods
# ---------------------------------------------------------------------------
def _sync(method: str, params: dict):
    from backend.interfaces import api
    if method == "health":
        from backend.infrastructure.accel import info as _accel_info
        return {
            "ok": True, "service": "scramjet-rpc",
            "repo": str(_REPO),
            "python": sys.version.split()[0],
            "accel": _accel_info(),
            "methods": sorted(SYNC_METHODS | JOB_METHODS),
        }
    if method == "describe_case":
        return api.describe_case(str(resolve_case(params["case_path"])))
    if method == "list_cases":
        return [{"name": p.stem, "file": p.relative_to(_REPO).as_posix()}
                for p in sorted((_REPO / "configs" / "cases").glob("*.yaml"))]
    if method == "validate":
        return _validate(params)
    if method == "load_report":
        return api.load_report(params.get("workdir"))
    if method == "load_geometry":
        return api.load_geometry(params.get("workdir"))
    if method == "load_stations":
        return api.load_stations(params.get("workdir"))
    if method == "load_metrics":
        return api.load_metrics(params.get("workdir"))
    if method == "load_outputs":
        return api.load_outputs(params.get("workdir"))
    if method == "list_runs":
        return api.list_runs(params.get("runs_dir", "runs"),
                             limit=int(params.get("limit", 30)))
    if method == "score_metrics":
        return api.score_metrics(params.get("metrics") or {})
    if method == "job_status":
        return MANAGER.status(params.get("job_id"))
    if method == "job_list":
        return MANAGER.list()
    if method == "job_cancel":
        return MANAGER.cancel(params.get("job_id"))
    raise ValueError(f"unknown method: {method}")


def _validate(params: dict) -> dict:
    """Re-coerce overrides, run backend validation, and return the coerced
    groups so the UI always mirrors what the backend would actually use."""
    from dataclasses import asdict
    from backend.domain.config import apply_overrides, load_case, validate
    from backend.domain.geometry import build_geometry

    cfg = load_case(resolve_case(params.get("case_path")))
    if params.get("overrides"):
        try:
            apply_overrides(cfg, params["overrides"])
        except Exception as exc:  # noqa: BLE001
            return {"valid": False,
                    "errors": [f"override rejected: {exc}"],
                    "groups": None, "flow_derived": None}

    errors = []
    try:
        validate(cfg)
    except ValueError as exc:
        errors.append(str(exc))
    if not errors:
        try:
            build_geometry(cfg.geometry)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"geometry: {exc}")

    return {"valid": not errors, "errors": errors,
            "groups": {g: asdict(getattr(cfg, g))
                       for g in ("flow", "geometry", "mesh", "solver")},
            "flow_derived": cfg.flow_as_dict()}


# ---------------------------------------------------------------------------
# Job manager (subprocess workers so runs can be cancelled)
# ---------------------------------------------------------------------------
@dataclass
class Job:
    job_id: str
    method: str
    params: dict
    jobdir: Path
    proc: subprocess.Popen | None = None
    status: str = "queued"            # queued|running|done|error|cancelled
    stage: str = ""
    message: str = ""
    progress: float | None = None
    error: dict | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._tmp = Path(os.environ.get("SCRAMJET_TMP",
                                        str(Path(_REPO) / "runs" / ".jobs")))
        self._tmp.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        for job in list(self._jobs.values()):
            self.cancel(job.job_id)
        self._thread.join(timeout=2.0)

    # -- lifecycle ----------------------------------------------------------
    def submit(self, method: str, params: dict) -> str:
        params = dict(params or {})
        if params.get("case_path"):
            # Resolve case identifiers here so subprocess workers always
            # receive an absolute, existing YAML path.
            params["case_path"] = str(resolve_case(params["case_path"]))
        job_id = uuid.uuid4().hex[:12]
        jobdir = self._tmp / job_id
        jobdir.mkdir(parents=True, exist_ok=True)
        (jobdir / "params.json").write_text(
            json.dumps(params), encoding="utf-8")
        env = dict(os.environ)
        env.setdefault("SCRAMJET_JOBDIR", str(jobdir))
        proc = subprocess.Popen(
            [sys.executable, "-m", "backend.interfaces._jobworker",
             method, str(jobdir)],
            cwd=str(_REPO), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        job = Job(job_id=job_id, method=method, params=params,
                  jobdir=jobdir, proc=proc, status="running")
        with self._lock:
            self._jobs[job_id] = job
        return job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job or job.status not in ("queued", "running"):
            return False
        self._kill_tree(job.proc.pid if job.proc else None)
        job.status = "cancelled"
        job.finished = time.time()
        return True

    @staticmethod
    def _kill_tree(pid: int | None) -> None:
        if not pid:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=10)
                return
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            os.kill(pid, 9)
        except OSError:
            pass

    def status(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return None
        return self._snapshot(job)

    def list(self) -> list[dict]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [self._snapshot(j) for j in jobs]

    def _snapshot(self, job: Job) -> dict:
        return {
            "job_id": job.job_id, "method": job.method,
            "status": job.status, "stage": job.stage,
            "message": job.message, "progress": job.progress,
            "elapsed": round(time.time() - job.started, 1),
            "error": job.error,
            "started": job.started,
        }

    # -- progress -----------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                jobs = list(self._jobs.values())
            for job in jobs:
                if job.status != "running" or not job.proc:
                    continue
                self._poll(job)
            self._stop.wait(_POLL_INTERVAL)

    def _poll(self, job: Job) -> None:
        ret = job.proc.poll()
        if ret is None:
            # still running -> refresh progress
            stage, message, progress = self._live_progress(job)
            job.stage, job.message, job.progress = stage, message, progress
            return
        result = self._read_result(job)
        job.finished = time.time()
        if result is None:
            job.status = "error"
            job.error = {"type": "WorkerError",
                         "message": "worker produced no result"}
        elif "error" in result:
            job.status = "error"
            err = result["error"]
            job.error = {"type": err.get("type", "Error"),
                         "message": err.get("message", str(err))}
        else:
            job.status = "done"
            job.stage = "done"
            job.message = "complete"
            job.progress = 1.0
            job.result = result.get("result")

    def _read_result(self, job: Job) -> dict | None:
        path = job.jobdir / "result.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _live_progress(self, job: Job):
        if job.method == "run_case":
            return self._run_case_progress(job.params)
        # render jobs: worker writes progress.json
        path = job.jobdir / "progress.json"
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                return (d.get("stage", "render"), d.get("message", ""),
                        d.get("progress"))
            except (OSError, ValueError):
                pass
        return "render", "working", None

    def _run_case_progress(self, params: dict):
        from backend.interfaces import api
        workdir = Path(params.get("workdir", ""))
        steps = params.get("steps") or api.ALL_STEPS
        included = [s for s in api.ALL_STEPS if s in steps]
        if not included:
            return "running", "", None
        weights = {s: _STEP_WEIGHT.get(s, 0.04) for s in included}
        total = sum(weights.values())
        done = 0.0
        if "geometry" in weights and (workdir / "geometry" / "geometry.json").exists():
            done += weights["geometry"]
        if "mesh" in weights and list((workdir / "mesh").glob("*.su2")):
            done += weights["mesh"]
        if "case" in weights and list((workdir / "case").glob("*.cfg")):
            done += weights["case"]
        if "run" in weights:
            logs = sorted((workdir / "run").glob("*.log"))
            if logs:
                frac, msg = self._solver_fraction(logs, workdir)
                done += weights["run"] * frac
            if done == 0.0 and not list((workdir / "run").glob("*.vtu")):
                pass
        if "post" in weights and (workdir / "post" / "stations.json").exists():
            done += weights["post"]
        if "metrics" in weights and (workdir / "metrics.json").exists():
            done += weights["metrics"]

        progress = min(done / total, 0.999) if total else None
        stage = self._run_stage(workdir)
        message = self._run_message(workdir, logs if "run" in weights else [])
        return stage, message, progress

    def _solver_fraction(self, logs: list, workdir: Path):
        # Each SU2 stage log is weighted half of the "run" step. Newest log
        # by mtime is the active stage.
        frac, msg = 0.0, ""
        for log in logs:
            span = 0.5
            base = 0.5 if "stage2" in log.name else 0.0
            iters, maxit, res = _parse_su2_log(log, workdir)
            f = min(iters / maxit, 1.0) if maxit else 0.0
            frac = max(frac, base + span * f)
            if log.stat().st_mtime == max(l.stat().st_mtime for l in logs):
                msg = f"{log.stem}: iter {iters}/{maxit} rms={res}"
        return min(max(frac, 0.001), 1.0), msg

    def _run_stage(self, workdir: Path) -> str:
        if (workdir / "report.json").exists():
            return "done"
        if list((workdir / "run").glob("*.log")):
            return "solver"
        if list((workdir / "case").glob("*.cfg")):
            return "case"
        if list((workdir / "mesh").glob("*.su2")):
            return "mesh"
        if (workdir / "geometry" / "geometry.json").exists():
            return "geometry"
        return "starting"

    def _run_message(self, workdir: Path, logs: list) -> str:
        if (workdir / "report.json").exists():
            return "finalizing report"
        if list((workdir / "run").glob("*.vtu")):
            return "solution written"
        return ""


def _parse_su2_log(log: Path, workdir: Path):
    """Return (last_iteration, max_iter, last_RMS[Rho]) for a SU2 stage log."""
    maxit = 0
    cfg = workdir / "case" / "config" / f"{log.stem}.cfg"
    try:
        if cfg.exists():
            for line in cfg.read_text(encoding="utf-8").splitlines():
                if line.lstrip().upper().startswith("MAX_ITER"):
                    maxit = int(line.split("=", 1)[1].strip())
    except (OSError, ValueError):
        pass
    iters, res = 0, ""
    try:
        with log.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                import re
                m = re.search(r"External iteration:\s*(\d+)", line)
                if m:
                    iters = int(m.group(1))
                m = re.search(r"RMS\[Rho\]\s*=\s*([\d.eE+-]+)", line)
                if m:
                    res = f"{float(m.group(1)):.2e}"
    except OSError:
        pass
    return iters, maxit, res


MANAGER = JobManager()


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------
def _handler_factory(token: str, manager: JobManager):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ScramjetRPC/0.1"
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, obj) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path in ("/healthz", "/health"):
                self._send(200, {"ok": True, "service": "scramjet-rpc"})
            else:
                self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/rpc":
                self._send(404, {"ok": False, "error": "not found"})
                return
            if self.headers.get("Authorization") != f"Bearer {token}":
                self._send(401, {"ok": False,
                                 "error": "unauthorized: bad token"})
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > MAX_BODY:
                self._send(413, {"ok": False, "error": "body too large"})
                return
            try:
                req = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, {"ok": False, "error": "invalid JSON"})
                return
            method = req.get("method")
            params = req.get("params") or {}
            try:
                if method in SYNC_METHODS:
                    result = _sync(method, params)
                    self._send(200, {"ok": True, "result": result})
                elif method in JOB_METHODS:
                    job_id = manager.submit(method, params)
                    self._send(200, {"ok": True,
                                     "result": {"job_id": job_id}})
                else:
                    self._send(404, {"ok": False,
                                     "error": f"unknown method: {method}"})
            except Exception as exc:  # noqa: BLE001
                self._send(200, {"ok": False,
                                 "error": {"type": type(exc).__name__,
                                           "message": str(exc)}})

        def log_message(self, *args):  # silence access logs
            pass

    return Handler


def serve(port: int = 0) -> int:
    token = os.environ.get("SCRAMJET_TOKEN") or secrets.token_urlsafe(24)
    manager = MANAGER
    handler = _handler_factory(token, manager)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    port = httpd.server_address[1]
    print(f"SCRAMJET_SERVER_URL=http://127.0.0.1:{port}", flush=True)
    print(f"SCRAMJET_TOKEN={token}", flush=True)
    manager.start()
    try:
        httpd.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
