"""Constraint-programming timetable solver (Google OR-Tools CP-SAT).

Hard constraints
  H1  every weekly session of every course is placed exactly once
  H2  a block never leaves its day or straddles a break
  H3  no faculty / room / student-cohort double booking (NoOverlap)
  H4  faculty availability, max hours per day and per week
  H5  rooms match type (classroom/lab/lab-tag) and capacity
  H6  elective basket courses run in parallel (same slots) - NEP flexibility
  H7  one faculty per course; a course meets at most ceil(n/days) times a day
  H8  cohort daily load cap

Soft constraints (weighted objective)
  S1  minimise idle gaps in student timetables
  S2  balance daily load of each cohort
  S3  avoid penalised days (e.g. Saturday)
  S4  practical blocks in the afternoon
  S5  avoid wasting room capacity
"""
from __future__ import annotations

import math
import os
from collections import defaultdict
from typing import Any, Dict, List

from ortools.sat.python import cp_model

from .models import Dataset, DataError


def solve(ds: Dataset, time_limit: float = 30.0, workers: int = 0, seed: int = 1,
          log: bool = False) -> Dict[str, Any]:
    cfg = ds.config
    D, P = cfg.n_days, cfg.n_periods
    W = cfg.weights
    events = ds.build_events()
    m = cp_model.CpModel()
    obj: List[Any] = []

    valid = {dur: [p for p in range(P) if cfg.block_fits(p, dur)]
             for dur in {e.duration for e in events}}
    for dur, v in valid.items():
        if not v:
            raise DataError(f"A block of {dur} periods cannot fit in the day without crossing a break")

    # ---- H1/H2: placement variables ------------------------------------------------
    sb: Dict[Any, Any] = {}
    start: Dict[int, Any] = {}
    iv: Dict[int, Any] = {}
    dayexpr: Dict[Any, Any] = {}
    for ei, e in enumerate(events):
        lits = []
        for d in range(D):
            row = []
            for p in valid[e.duration]:
                b = m.NewBoolVar(f"s_{ei}_{d}_{p}")
                sb[ei, d, p] = b
                lits.append(b)
                row.append(b)
            dayexpr[ei, d] = sum(row)
        m.AddExactlyOne(lits)
        st = m.NewIntVar(0, D * P - 1, f"start_{ei}")
        m.Add(st == sum((d * P + p) * sb[ei, d, p] for d in range(D) for p in valid[e.duration]))
        start[ei] = st
        iv[ei] = m.NewFixedSizeIntervalVar(st, e.duration, f"iv_{ei}")

    # ---- H7: faculty choice per course --------------------------------------------
    fac_choice: Dict[Any, Any] = {}
    course_hours: Dict[str, int] = {}
    for c in ds.courses.values():
        course_hours[c.id] = ds.weekly_hours(c)
        lits = []
        for f in c.faculty:
            b = m.NewBoolVar(f"fc_{c.id}_{f}")
            fac_choice[c.id, f] = b
            lits.append(b)
        m.AddExactlyOne(lits)

    # ---- H3/H4: faculty ------------------------------------------------------------
    fac_iv: Dict[str, List[Any]] = defaultdict(list)
    day_load: Dict[Any, List[Any]] = defaultdict(list)
    for ei, e in enumerate(events):
        for it in e.items:
            for f in it.course.faculty:
                pres = fac_choice[it.course.id, f]
                fac_iv[f].append(m.NewOptionalFixedSizeIntervalVar(
                    start[ei], e.duration, pres, f"fiv_{ei}_{it.course.id}_{f}"))
                for d in range(D):
                    L = m.NewBoolVar(f"fl_{ei}_{it.course.id}_{f}_{d}")
                    m.Add(L >= pres + dayexpr[ei, d] - 1)
                    day_load[f, d].append((e.duration, L))
    for f, fac in ds.faculty.items():
        for (d, p) in fac.unavailable:
            fac_iv[f].append(m.NewFixedSizeIntervalVar(d * P + p, 1, f"unav_{f}_{d}_{p}"))
        if fac_iv[f]:
            m.AddNoOverlap(fac_iv[f])
        week = [course_hours[c.id] * fac_choice[c.id, f] for c in ds.courses.values() if f in c.faculty]
        if week:
            m.Add(sum(week) <= fac.max_hours_per_week)
        for d in range(D):
            if day_load[f, d]:
                m.Add(sum(h * L for h, L in day_load[f, d]) <= fac.max_hours_per_day)

    # ---- H5: rooms -----------------------------------------------------------------
    room_iv: Dict[str, List[Any]] = defaultdict(list)
    room_choice: Dict[Any, Any] = {}
    for ei, e in enumerate(events):
        for ii, it in enumerate(e.items):
            elig = ds.eligible_rooms(it.course, e.kind, it.enrolment)
            if not elig:
                raise DataError(f"No room can host {it.course.id} ({e.kind}, {it.enrolment} students)")
            lits = []
            for r in elig:
                y = m.NewBoolVar(f"y_{ei}_{ii}_{r.id}")
                room_choice[ei, ii, r.id] = y
                lits.append(y)
                room_iv[r.id].append(m.NewOptionalFixedSizeIntervalVar(
                    start[ei], e.duration, y, f"riv_{ei}_{ii}_{r.id}"))
                waste = (r.capacity - it.enrolment) // 10
                if waste and W["room"]:
                    obj.append(W["room"] * waste * y)
            m.AddExactlyOne(lits)
    for lst in room_iv.values():
        m.AddNoOverlap(lst)

    # ---- H3: cohorts ---------------------------------------------------------------
    coh_iv: Dict[str, List[Any]] = defaultdict(list)
    for ei, e in enumerate(events):
        for c in e.cohorts:
            coh_iv[c].append(iv[ei])
    for lst in coh_iv.values():
        m.AddNoOverlap(lst)

    # ---- H7: a course does not meet more than ceil(n/days) times a day --------------
    groups: Dict[Any, List[int]] = defaultdict(list)
    for ei, e in enumerate(events):
        groups[e.group, "lab" if e.kind == "practical" else "lec"].append(ei)
    for (_, _), eis in groups.items():
        cap = math.ceil(len(eis) / D)
        for d in range(D):
            m.Add(sum(dayexpr[ei, d] for ei in eis) <= cap)

    # ---- cohort occupancy, H8 and soft terms S1-S3 -------------------------------------
    cover: Dict[Any, List[Any]] = defaultdict(list)
    for ei, e in enumerate(events):
        for d in range(D):
            for p in valid[e.duration]:
                for k in range(e.duration):
                    for c in e.cohorts:
                        cover[c, d, p + k].append(sb[ei, d, p])
    gap_vars: List[Any] = []
    for cid in ds.cohorts:
        occ: Dict[Any, Any] = {}
        for d in range(D):
            for p in range(P):
                o = m.NewBoolVar(f"occ_{cid}_{d}_{p}")
                m.Add(o == sum(cover[cid, d, p]))
                occ[d, p] = o
        mx = m.NewIntVar(0, P, f"max_{cid}")
        for d in range(D):
            load = sum(occ[d, p] for p in range(P))
            m.Add(load <= cfg.max_cohort_periods_per_day)
            m.Add(load <= mx)
            pen = cfg.day_penalty.get(cfg.days[d], 0)
            if pen:
                obj.append(W["day"] * pen * load)
            pre = [m.NewBoolVar(f"pre_{cid}_{d}_{p}") for p in range(P)]
            post = [m.NewBoolVar(f"post_{cid}_{d}_{p}") for p in range(P)]
            for p in range(P):
                m.AddImplication(occ[d, p], pre[p])
                m.AddImplication(occ[d, p], post[p])
                if p > 0:
                    m.AddImplication(pre[p - 1], pre[p])
                if p < P - 1:
                    m.AddImplication(post[p + 1], post[p])
            for p in range(1, P - 1):
                g = m.NewBoolVar(f"gap_{cid}_{d}_{p}")
                m.Add(g >= pre[p - 1] + post[p + 1] - occ[d, p] - 1)
                gap_vars.append(g)
        obj.append(W["balance"] * mx)
    obj.extend(W["gap"] * g for g in gap_vars)

    # ---- S4: practicals in the afternoon ---------------------------------------------
    aft = cfg.afternoon_start - 1
    for ei, e in enumerate(events):
        if e.kind == "practical" and W["lab_morning"]:
            for d in range(D):
                for p in valid[e.duration]:
                    if p < aft:
                        obj.append(W["lab_morning"] * sb[ei, d, p])

    m.Minimize(sum(obj))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = int(workers) or max(1, min(8, os.cpu_count() or 1))
    solver.parameters.random_seed = int(seed)
    solver.parameters.log_search_progress = bool(log)
    status = solver.Solve(m)
    name = solver.StatusName(status)
    result: Dict[str, Any] = {"status": name, "wall_time": round(solver.WallTime(), 2),
                              "n_events": len(events), "sessions": []}
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return result

    result["objective"] = solver.ObjectiveValue()
    result["bound"] = solver.BestObjectiveBound()
    sessions = []
    for ei, e in enumerate(events):
        s = solver.Value(start[ei])
        d, p = divmod(s, P)
        for ii, it in enumerate(e.items):
            fid = next(f for f in it.course.faculty if solver.Value(fac_choice[it.course.id, f]))
            rid = next(r.id for r in ds.eligible_rooms(it.course, e.kind, it.enrolment)
                       if solver.Value(room_choice[ei, ii, r.id]))
            b = ds.baskets.get(e.basket) if e.basket else None
            sessions.append({
                "event_id": e.id, "course_id": it.course.id, "course_name": it.course.name,
                "category": it.course.category, "kind": e.kind,
                "day": d, "day_name": cfg.days[d], "period": p, "duration": e.duration,
                "start_time": cfg.periods[p].start, "end_time": cfg.periods[p + e.duration - 1].end,
                "cohorts": list(e.cohorts), "faculty_id": fid, "faculty_name": ds.faculty[fid].name,
                "room_id": rid, "room_name": ds.rooms[rid].name, "enrolment": it.enrolment,
                "basket_id": e.basket, "basket_name": b.name if b else None,
            })
    sessions.sort(key=lambda x: (x["day"], x["period"], x["course_id"]))
    result["sessions"] = sessions
    return result
