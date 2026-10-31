"""High-level entry point: solve -> validate -> score -> NEP report."""
from __future__ import annotations

from typing import Any, Dict

from .diagnostics import diagnose
from .models import CATEGORIES, Dataset, DataError
from .nep import check_nep
from .solver import solve
from .validator import compute_metrics, validate


def meta(ds: Dataset) -> Dict[str, Any]:
    cfg = ds.config
    return {
        "institution": ds.institution,
        "days": cfg.days,
        "periods": [{"label": p.label, "start": p.start, "end": p.end} for p in cfg.periods],
        "breaks_after": cfg.breaks_after,
        "cohorts": [{"id": c.id, "name": c.name, "size": c.size, "semester": c.semester}
                    for c in ds.cohorts.values()],
        "faculty": [{"id": f.id, "name": f.name, "department": f.department} for f in ds.faculty.values()],
        "rooms": [{"id": r.id, "name": r.name, "kind": r.kind, "capacity": r.capacity}
                  for r in ds.rooms.values()],
        "categories": CATEGORIES,
    }


def generate_timetable(ds: Dataset, time_limit: float = 30.0, workers: int = 0,
                       seed: int = 1) -> Dict[str, Any]:
    diagnostics = diagnose(ds)
    result: Dict[str, Any]
    if any(i["level"] == "error" for i in diagnostics):
        result = {"status": "INFEASIBLE", "sessions": [], "wall_time": 0.0, "n_events": 0,
                  "note": "Capacity analysis found blocking problems; see diagnostics."}
    else:
        try:
            result = solve(ds, time_limit=time_limit, workers=workers, seed=seed)
        except DataError as e:
            result = {"status": "INVALID", "sessions": [], "wall_time": 0.0, "n_events": 0, "note": str(e)}
    ok = result["status"] in ("OPTIMAL", "FEASIBLE")
    sessions = result["sessions"]
    result["ok"] = ok
    result["meta"] = meta(ds)
    result["diagnostics"] = diagnostics
    result["violations"] = validate(ds, sessions) if ok else []
    result["metrics"] = compute_metrics(ds, sessions) if ok else {}
    result["nep"] = check_nep(ds, sessions if ok else None)
    if not ok and not any(i["level"] == "error" for i in diagnostics):
        if result["status"] == "UNKNOWN":
            result.setdefault("note", "No timetable was found within the time limit. Increase the solver "
                                      "time limit and try again.")
        else:
            result.setdefault("note", "No feasible timetable exists for the given constraints. Relax faculty "
                                      "availability/limits, add rooms, or allow more periods or days.")
    return result
