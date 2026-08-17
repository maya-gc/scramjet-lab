"""Tabular export: results rows for sweeps / ML / optimization."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

_REPO = Path(__file__).resolve()
while not ((_REPO / "configs").is_dir() and (_REPO / "backend").is_dir()):
    _REPO = _REPO.parent
    if _REPO.parent == _REPO:
        break
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None


def results_row(cfg, metrics: dict, workdir=None) -> dict:
    """Flat feature+target vector for one experiment."""
    row = {"case": cfg.name, "workdir": str(workdir) if workdir else ""}
    for k, v in cfg.to_flat_dict().items():
        row[f"in_{k}"] = v
    for k, v in metrics.items():
        row[f"out_{k}"] = v
    return row


def append_rows(rows: list[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    if path.exists() and path.stat().st_size > 0:
        with open(path, "r", encoding="utf-8") as fh:
            existing = list(csv.DictReader(fh))
        rows = existing + rows
        fields = list(existing[0].keys()) if existing else fields
        for r in rows:
            for k in fields:
                r.setdefault(k, "")
    else:
        for r in rows:
            for k in fields:
                r.setdefault(k, "")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def load_results(path: str | Path):
    path = Path(path)
    if pd is not None:
        return pd.read_csv(path)
    with open(path, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
