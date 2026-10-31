"""Pre-solve capacity analysis.

Cheap necessary-condition checks that explain *why* a dataset is likely to be
infeasible (or tight) before / after the solver runs.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .models import Dataset


def diagnose(ds: Dataset) -> List[Dict[str, str]]:
    cfg = ds.config
    D, P = cfg.n_days, cfg.n_periods
    total_slots = D * P
    issues: List[Dict[str, str]] = []

    def add(level: str, msg: str) -> None:
        issues.append({"level": level, "message": msg})

    # cohort load
    events = ds.build_events()
    coh_hours: Dict[str, int] = defaultdict(int)
    for e in events:
        for c in e.cohorts:
            coh_hours[c] += e.duration
    for cid, h in coh_hours.items():
        cap = min(total_slots, D * cfg.max_cohort_periods_per_day)
        if h > cap:
            add("error", f"Cohort {cid} needs {h} periods/week but only {cap} are available")
        elif h > 0.85 * cap:
            add("warning", f"Cohort {cid} is very full: {h} of {cap} periods")

    # faculty that are the only option for their courses
    forced: Dict[str, int] = defaultdict(int)
    for c in ds.courses.values():
        if len(c.faculty) == 1:
            forced[c.faculty[0]] += ds.weekly_hours(c)
    for fid, h in forced.items():
        f = ds.faculty[fid]
        avail = total_slots - len(f.unavailable)
        if h > f.max_hours_per_week:
            add("error", f"{f.name} must teach {h}h/week but the weekly limit is {f.max_hours_per_week}h")
        if h > avail:
            add("error", f"{f.name} must teach {h}h/week but only {avail} slots are available")
        elif h > 0.8 * min(avail, f.max_hours_per_week):
            add("warning", f"{f.name} is heavily loaded: {h}h/week of forced teaching")

    # lab capacity by type
    lab_demand: Dict[str, int] = defaultdict(int)
    for e in events:
        if e.kind == "practical":
            for it in e.items:
                lab_demand[it.course.lab_type or "any"] += e.duration
    for lt, h in lab_demand.items():
        rooms = [r for r in ds.rooms.values() if r.kind == "lab" and (lt == "any" or lt in r.tags)]
        supply = len(rooms) * total_slots
        if not rooms:
            add("error", f"No lab with tag '{lt}' exists but {h}h of practicals need one")
        elif h > supply:
            add("error", f"'{lt}' labs: {h}h demanded, only {supply}h available")
        elif h > 0.7 * supply:
            add("warning", f"'{lt}' labs are tight: {h} of {supply} lab-hours")

    # rooms for every item
    for e in events:
        for it in e.items:
            if not ds.eligible_rooms(it.course, e.kind, it.enrolment):
                add("error", f"No room fits {it.course.id} ({e.kind}, {it.enrolment} students)")
                break

    # peak parallel demand from baskets
    n_class = sum(1 for r in ds.rooms.values() if r.kind == "classroom")
    n_lab = sum(1 for r in ds.rooms.values() if r.kind == "lab")
    for b in ds.baskets.values():
        n = len(b.course_ids)
        ref = ds.courses[b.course_ids[0]]
        if (ref.L or ref.T) and n > n_class:
            add("error", f"Basket {b.id} needs {n} classrooms at the same time but only {n_class} exist")
        if ref.P and n > n_lab:
            add("error", f"Basket {b.id} needs {n} labs at the same time but only {n_lab} exist")
    return issues
