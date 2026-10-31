"""NEP 2020 / UGCF compliance checks for multidisciplinary programmes.

Rules live in the dataset (``"nep"`` block) so institutions can adapt them:

    "nep": {
      "credit_range": [18, 26],              # credits per semester
      "max_weekly_contact_hours": 30,
      "required_categories": [               # minimum credits by NEP category
        {"category": "MDC", "min_credits": 3, "semesters": [1, 2, 3]}, ...]
    }

A credit is counted once per elective basket (a student takes one option).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from .models import Dataset

DEFAULT_RULES = {"credit_range": [18, 26], "max_weekly_contact_hours": 30, "required_categories": []}


def _chk(name: str, status: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def check_nep(ds: Dataset, sessions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rules = {**DEFAULT_RULES, **ds.nep}
    lo, hi = rules["credit_range"]
    out: Dict[str, Any] = {"cohorts": {}, "summary": {"PASS": 0, "WARN": 0, "FAIL": 0}}

    slots_by_course: Dict[str, set] = defaultdict(set)
    for s in sessions or []:
        slots_by_course[s["course_id"]].update((s["day"], s["period"] + k) for k in range(s["duration"]))

    for coh in ds.cohorts.values():
        credits: Dict[str, int] = defaultdict(int)
        hours = 0
        seen_baskets = set()
        offered_depts = set()
        for c in ds.courses.values():
            if coh.id not in c.cohorts:
                continue
            offered_depts.add(c.department)
            if c.basket:
                if c.basket in seen_baskets:
                    continue
                seen_baskets.add(c.basket)
            credits[c.category] += c.credits
            hours += ds.weekly_hours(c)
        total = sum(credits.values())
        checks: List[Dict[str, str]] = []

        checks.append(_chk("Credit load", "PASS" if lo <= total <= hi else "FAIL",
                           f"{total} credits (allowed {lo}-{hi} per semester)"))
        mh = rules["max_weekly_contact_hours"]
        checks.append(_chk("Weekly contact hours", "PASS" if hours <= mh else "WARN",
                           f"{hours} h/week (limit {mh})"))
        for r in rules["required_categories"]:
            if coh.semester in r.get("semesters", [coh.semester]):
                got = credits.get(r["category"], 0)
                checks.append(_chk(f"{r['category']} credits", "PASS" if got >= r["min_credits"] else "FAIL",
                                   f"{got} credits (minimum {r['min_credits']} in semester {coh.semester})"))
        outside = sorted(d for d in offered_depts if d and d != coh.department)
        checks.append(_chk("Multidisciplinary exposure", "PASS" if outside else "WARN",
                           ("Courses from " + ", ".join(outside)) if outside
                           else "No course from another department"))
        for bid in sorted(seen_baskets):
            b = ds.baskets[bid]
            n = len(b.course_ids)
            ok = n >= 2
            detail = f"{b.name}: {n} option(s)"
            if sessions:
                ref = None
                parallel = True
                for cid in b.course_ids:
                    ref = slots_by_course[cid] if ref is None else ref
                    parallel &= slots_by_course[cid] == ref
                ok = ok and parallel
                detail += ", all options run in parallel" if parallel else ", options NOT parallel"
            checks.append(_chk("Elective choice", "PASS" if ok else "WARN", detail))

        for c in checks:
            out["summary"][c["status"]] += 1
        out["cohorts"][coh.id] = {"name": coh.name, "semester": coh.semester, "total_credits": total,
                                  "weekly_hours": hours, "credits_by_category": dict(credits),
                                  "checks": checks}
    return out
