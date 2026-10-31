"""Independent verification of a generated timetable.

The validator never looks at the solver model: it re-derives every hard
constraint from the list of sessions, so it also works for hand-edited
timetables.  ``compute_metrics`` reports the soft-quality indicators.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List

from .models import Dataset


def _slots(s: Dict[str, Any]) -> List[tuple]:
    return [(s["day"], s["period"] + k) for k in range(s["duration"])]


def validate(ds: Dataset, sessions: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    cfg = ds.config
    v: List[Dict[str, str]] = []

    def bad(kind: str, msg: str) -> None:
        v.append({"type": kind, "message": msg})

    fac_slots: Dict[Any, set] = defaultdict(set)
    room_slots: Dict[Any, set] = defaultdict(set)
    coh_slots: Dict[Any, set] = defaultdict(set)
    fac_day: Dict[Any, int] = defaultdict(int)
    fac_week: Dict[str, int] = defaultdict(int)
    course_fac: Dict[str, set] = defaultdict(set)
    course_hours: Dict[str, int] = defaultdict(int)
    course_day: Dict[Any, int] = defaultdict(int)
    basket_slots: Dict[Any, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    seen_event_cohort: Dict[Any, set] = defaultdict(set)

    for s in sessions:
        c = ds.courses[s["course_id"]]
        fac = ds.faculty[s["faculty_id"]]
        room = ds.rooms[s["room_id"]]
        slots = _slots(s)
        if s["period"] + s["duration"] > cfg.n_periods:
            bad("day-overflow", f"{s['event_id']} runs past the last period")
        if not cfg.block_fits(s["period"], s["duration"]):
            bad("break-crossing", f"{s['event_id']} straddles a break")
        for sl in slots:
            if (s["day"], sl[1]) in fac.unavailable:
                bad("faculty-unavailable", f"{fac.id} is unavailable {cfg.days[s['day']]} P{sl[1]+1}")
            if sl in fac_slots[fac.id]:
                bad("faculty-clash", f"{fac.id} double-booked {cfg.days[sl[0]]} P{sl[1]+1}")
            fac_slots[fac.id].add(sl)
            if sl in room_slots[room.id]:
                bad("room-clash", f"{room.id} double-booked {cfg.days[sl[0]]} P{sl[1]+1}")
            room_slots[room.id].add(sl)
            for co in s["cohorts"]:
                key = (co, sl)
                seen_event_cohort[key].add(s["event_id"])
                coh_slots[co].add(sl)
        fac_week[fac.id] += s["duration"]
        fac_day[fac.id, s["day"]] += s["duration"]
        course_fac[c.id].add(fac.id)
        course_hours[c.id] += s["duration"]
        course_day[c.id, "lab" if s["kind"] == "practical" else "lec", s["day"]] += 1
        if fac.id not in c.faculty:
            bad("faculty-ineligible", f"{fac.id} is not eligible for {c.id}")
        need = "lab" if s["kind"] == "practical" else "classroom"
        if room.kind != need:
            bad("room-type", f"{c.id} {s['kind']} placed in {room.kind} {room.id}")
        if need == "lab" and c.lab_type and c.lab_type not in room.tags:
            bad("room-type", f"{c.id} needs a {c.lab_type} lab but got {room.id}")
        if room.capacity < s["enrolment"]:
            bad("room-capacity", f"{room.id} ({room.capacity}) too small for {c.id} ({s['enrolment']})")
        if c.basket:
            basket_slots[c.basket][c.id].update(slots)

    for (co, sl), evs in seen_event_cohort.items():
        if len(evs) > 1:
            bad("cohort-clash", f"{co} has overlapping sessions {sorted(evs)} at "
                                f"{cfg.days[sl[0]]} P{sl[1]+1}")
    for cid, c in ds.courses.items():
        if course_hours[cid] != ds.weekly_hours(c):
            bad("credit-hours", f"{cid} scheduled {course_hours[cid]}h, expected {ds.weekly_hours(c)}h "
                                f"from {c.L}-{c.T}-{c.P} credits")
        if len(course_fac[cid]) > 1:
            bad("multiple-faculty", f"{cid} is taught by several faculty: {sorted(course_fac[cid])}")
    for bid, courses in basket_slots.items():
        ref = None
        for cid, sl in courses.items():
            ref = sl if ref is None else ref
            if sl != ref:
                bad("basket-parallel", f"Basket {bid}: {cid} is not parallel with the other options")
    for fid, fac in ds.faculty.items():
        if fac_week[fid] > fac.max_hours_per_week:
            bad("faculty-week", f"{fid} teaches {fac_week[fid]}h > {fac.max_hours_per_week}h per week")
        for d in range(cfg.n_days):
            if fac_day[fid, d] > fac.max_hours_per_day:
                bad("faculty-day", f"{fid} teaches {fac_day[fid, d]}h on {cfg.days[d]} "
                                   f"(max {fac.max_hours_per_day})")
    groups: Dict[str, int] = defaultdict(int)
    for cid, c in ds.courses.items():
        key = c.basket or cid
        groups[key, "lec"] = sum(1 for k, n in ds.course_events(c) if k != "practical")
        groups[key, "lab"] = sum(1 for k, n in ds.course_events(c) if k == "practical")
    for (cid, kind, d), n in course_day.items():
        c = ds.courses[cid]
        total = groups[(c.basket or cid), kind]
        if n > math.ceil(total / cfg.n_days):
            bad("same-day-repeat", f"{cid} meets {n} times ({kind}) on {cfg.days[d]}")
    for co, sl in coh_slots.items():
        per_day: Dict[int, int] = defaultdict(int)
        for d, _ in sl:
            per_day[d] += 1
        for d, n in per_day.items():
            if n > cfg.max_cohort_periods_per_day:
                bad("cohort-day-load", f"{co} has {n} periods on {cfg.days[d]}")
    return v


def compute_metrics(ds: Dataset, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = ds.config
    D, P = cfg.n_days, cfg.n_periods
    coh: Dict[str, Dict[int, set]] = {c: defaultdict(set) for c in ds.cohorts}
    fac_week: Dict[str, int] = defaultdict(int)
    fac_day: Dict[str, List[int]] = {f: [0] * D for f in ds.faculty}
    room_h: Dict[str, int] = defaultdict(int)
    for s in sessions:
        for co in s["cohorts"]:
            for d, p in _slots(s):
                coh[co][d].add(p)
        fac_week[s["faculty_id"]] += s["duration"]
        fac_day[s["faculty_id"]][s["day"]] += s["duration"]
        room_h[s["room_id"]] += s["duration"]
    gaps: Dict[str, int] = {}
    loads: Dict[str, List[int]] = {}
    for co, days in coh.items():
        g = 0
        loads[co] = [len(days.get(d, ())) for d in range(D)]
        for d in range(D):
            ps = sorted(days.get(d, ()))
            if ps:
                g += (ps[-1] - ps[0] + 1) - len(ps)
        gaps[co] = g
    total_slots = D * P
    return {
        "cohort_gaps": gaps, "total_gaps": sum(gaps.values()), "cohort_daily_load": loads,
        "faculty_load": {f: {"week": fac_week.get(f, 0), "per_day": fac_day[f],
                             "max_week": ds.faculty[f].max_hours_per_week} for f in ds.faculty},
        "room_utilisation": {r: round(100 * room_h.get(r, 0) / total_slots, 1) for r in ds.rooms},
    }
