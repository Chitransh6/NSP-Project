"""Data models and dataset loading for the NEP 2020 timetable generator.

A *Dataset* describes one institution-semester: the time grid, student cohorts,
faculty, rooms, courses and elective baskets.  Courses are described using the
NEP/UGCF credit pattern (L-T-P credits); the number of weekly periods is derived
from the credits using ``config.hours_per_credit``.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# NEP 2020 / UGCF course categories used in multidisciplinary programmes.
CATEGORIES: Dict[str, str] = {
    "MAJOR": "Major (DSC)",
    "MINOR": "Minor (DSM)",
    "MDC": "Multidisciplinary (MDC)",
    "AEC": "Ability Enhancement (AEC)",
    "SEC": "Skill Enhancement (SEC)",
    "VAC": "Value Added (VAC)",
    "OTHER": "Other",
}

DEFAULT_WEIGHTS = {
    "gap": 10,        # idle period between two classes of a cohort on one day
    "balance": 3,     # heaviest day of a cohort (spreads load over the week)
    "day": 1,         # per-period penalty from config.day_penalty (e.g. Saturday)
    "lab_morning": 2, # practical block started before afternoon_start
    "room": 1,        # wasted room capacity (per 10 seats)
}


class DataError(ValueError):
    """Raised when the input dataset is inconsistent."""


@dataclass
class Period:
    label: str
    start: str
    end: str


@dataclass
class Config:
    days: List[str]
    periods: List[Period]
    breaks_after: List[int] = field(default_factory=list)   # 1-based period numbers
    afternoon_start: int = 5                                 # 1-based first afternoon period
    max_cohort_periods_per_day: int = 7
    hours_per_credit: Dict[str, int] = field(default_factory=lambda: {"L": 1, "T": 1, "P": 2})
    day_penalty: Dict[str, int] = field(default_factory=dict)
    weights: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    @property
    def n_days(self) -> int:
        return len(self.days)

    @property
    def n_periods(self) -> int:
        return len(self.periods)

    def block_fits(self, start: int, duration: int) -> bool:
        """True if a block starting at 0-based period ``start`` stays inside the
        day and does not straddle a break."""
        if start + duration > self.n_periods:
            return False
        for b in self.breaks_after:          # break lies between 0-based b-1 and b
            if start <= b - 1 and b <= start + duration - 1:
                return False
        return True


@dataclass
class Cohort:
    id: str
    name: str
    department: str
    semester: int
    size: int


@dataclass
class Faculty:
    id: str
    name: str
    department: str
    max_hours_per_day: int = 5
    max_hours_per_week: int = 18
    unavailable: Set[Tuple[int, int]] = field(default_factory=set)  # (day, period) 0-based


@dataclass
class Room:
    id: str
    name: str
    kind: str            # "classroom" or "lab"
    capacity: int
    tags: List[str] = field(default_factory=list)


@dataclass
class Course:
    id: str
    name: str
    category: str
    department: str
    L: int
    T: int
    P: int
    cohorts: List[str]
    faculty: List[str]
    enrolment: int = 0
    lab_type: Optional[str] = None
    basket: Optional[str] = None

    @property
    def credits(self) -> int:
        return self.L + self.T + self.P


@dataclass
class Basket:
    """An elective basket: students of the listed cohorts pick ONE course.
    All courses of a basket are scheduled in parallel (same slots)."""
    id: str
    name: str
    category: str
    cohorts: List[str]
    course_ids: List[str] = field(default_factory=list)


@dataclass
class Item:
    course: Course
    enrolment: int


@dataclass
class Event:
    """One schedulable slot. A basket event carries several items (one per
    elective course) that all run at the same time."""
    id: str
    kind: str                # theory | tutorial | practical
    duration: int
    cohorts: Tuple[str, ...]
    items: List[Item]
    group: str               # course id or basket id
    basket: Optional[str] = None


class Dataset:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.institution = raw.get("institution", "Institution")
        self.nep: Dict[str, Any] = raw.get("nep", {})
        self.config = self._parse_config(raw.get("config", {}))
        self.cohorts = {c["id"]: Cohort(c["id"], c.get("name", c["id"]), c.get("department", ""),
                                        int(c.get("semester", 1)), int(c["size"]))
                        for c in raw.get("cohorts", [])}
        self.faculty = {f["id"]: self._parse_faculty(f) for f in raw.get("faculty", [])}
        self.rooms = {r["id"]: Room(r["id"], r.get("name", r["id"]), r.get("kind", "classroom"),
                                    int(r["capacity"]), list(r.get("tags", [])))
                      for r in raw.get("rooms", [])}
        self.baskets = {b["id"]: Basket(b["id"], b.get("name", b["id"]), b.get("category", "OTHER"),
                                        list(b["cohorts"])) for b in raw.get("baskets", [])}
        self.courses = self._parse_courses(raw.get("courses", []))
        self._validate()

    # ---------------------------------------------------------------- parsing
    def _parse_config(self, c: Dict[str, Any]) -> Config:
        if not c.get("days") or not c.get("periods"):
            raise DataError("config.days and config.periods are required")
        periods = [Period(p.get("label", f"P{i+1}"), p.get("start", ""), p.get("end", ""))
                   for i, p in enumerate(c["periods"])]
        weights = dict(DEFAULT_WEIGHTS)
        weights.update(c.get("weights", {}))
        return Config(
            days=list(c["days"]), periods=periods,
            breaks_after=list(c.get("breaks_after", [])),
            afternoon_start=int(c.get("afternoon_start", 5)),
            max_cohort_periods_per_day=int(c.get("max_cohort_periods_per_day", 7)),
            hours_per_credit={**{"L": 1, "T": 1, "P": 2}, **c.get("hours_per_credit", {})},
            day_penalty=dict(c.get("day_penalty", {})), weights=weights)

    def _parse_faculty(self, f: Dict[str, Any]) -> Faculty:
        days = self.config.days
        un: Set[Tuple[int, int]] = set()
        for u in f.get("unavailable", []):
            if u["day"] not in days:
                raise DataError(f"Faculty {f['id']}: unknown day '{u['day']}'")
            d = days.index(u["day"])
            periods = u.get("periods") or range(1, self.config.n_periods + 1)
            for p in periods:
                un.add((d, int(p) - 1))
        return Faculty(f["id"], f.get("name", f["id"]), f.get("department", ""),
                       int(f.get("max_hours_per_day", 5)), int(f.get("max_hours_per_week", 18)), un)

    def _parse_courses(self, rows: List[Dict[str, Any]]) -> Dict[str, Course]:
        out: Dict[str, Course] = {}
        for r in rows:
            cr = r.get("credits", {})
            basket = r.get("basket")
            cohorts = list(r.get("cohorts", []))
            if basket:
                if basket not in self.baskets:
                    raise DataError(f"Course {r['id']}: unknown basket '{basket}'")
                cohorts = list(self.baskets[basket].cohorts)
                self.baskets[basket].course_ids.append(r["id"])
            out[r["id"]] = Course(
                id=r["id"], name=r.get("name", r["id"]),
                category=r.get("category", "OTHER").upper(), department=r.get("department", ""),
                L=int(cr.get("L", 0)), T=int(cr.get("T", 0)), P=int(cr.get("P", 0)),
                cohorts=cohorts, faculty=list(r.get("faculty", [])),
                enrolment=int(r.get("enrolment") or 0), lab_type=r.get("lab_type"), basket=basket)
        # default enrolments
        for c in out.values():
            if c.enrolment:
                continue
            total = sum(self.cohorts[x].size for x in c.cohorts if x in self.cohorts)
            if c.basket:
                n = max(1, len(self.baskets[c.basket].course_ids))
                c.enrolment = math.ceil(total / n * 1.1)
            else:
                c.enrolment = total
        return out

    # ------------------------------------------------------------- validation
    def _validate(self) -> None:
        if not self.cohorts:
            raise DataError("At least one cohort is required")
        for c in self.courses.values():
            if c.credits == 0:
                raise DataError(f"Course {c.id} has zero credits")
            if not c.faculty:
                raise DataError(f"Course {c.id} has no eligible faculty")
            for f in c.faculty:
                if f not in self.faculty:
                    raise DataError(f"Course {c.id}: unknown faculty '{f}'")
            for x in c.cohorts:
                if x not in self.cohorts:
                    raise DataError(f"Course {c.id}: unknown cohort '{x}'")
            if not c.cohorts:
                raise DataError(f"Course {c.id} is not assigned to any cohort")
            if c.category not in CATEGORIES:
                raise DataError(f"Course {c.id}: unknown category '{c.category}'")
        for b in self.baskets.values():
            if len(b.course_ids) < 1:
                raise DataError(f"Basket {b.id} has no courses")
            ref = self.courses[b.course_ids[0]]
            for cid in b.course_ids[1:]:
                c = self.courses[cid]
                if (c.L, c.T, c.P) != (ref.L, ref.T, ref.P):
                    raise DataError(f"Basket {b.id}: courses must share the same L-T-P "
                                    f"structure ({ref.id} vs {c.id}) so they can run in parallel")
            for x in b.cohorts:
                if x not in self.cohorts:
                    raise DataError(f"Basket {b.id}: unknown cohort '{x}'")

    # ---------------------------------------------------------------- helpers
    def course_events(self, c: Course) -> List[Tuple[str, int]]:
        """(kind, duration) tuples per week derived from the credit pattern."""
        h = self.config.hours_per_credit
        ev: List[Tuple[str, int]] = []
        ev += [("theory", 1)] * (c.L * h["L"])
        ev += [("tutorial", 1)] * (c.T * h["T"])
        ev += [("practical", h["P"])] * c.P
        return ev

    def weekly_hours(self, c: Course) -> int:
        return sum(d for _, d in self.course_events(c))

    def build_events(self) -> List[Event]:
        events: List[Event] = []
        done_baskets: Set[str] = set()
        for c in self.courses.values():
            if c.basket:
                if c.basket in done_baskets:
                    continue
                done_baskets.add(c.basket)
                b = self.baskets[c.basket]
                items = [Item(self.courses[i], self.courses[i].enrolment) for i in b.course_ids]
                for n, (kind, dur) in enumerate(self.course_events(c)):
                    events.append(Event(f"{b.id}#{n+1}", kind, dur, tuple(b.cohorts), items, b.id, b.id))
            else:
                for n, (kind, dur) in enumerate(self.course_events(c)):
                    events.append(Event(f"{c.id}#{n+1}", kind, dur, tuple(c.cohorts),
                                        [Item(c, c.enrolment)], c.id))
        return events

    def eligible_rooms(self, c: Course, kind: str, enrolment: int) -> List[Room]:
        need = "lab" if kind == "practical" else "classroom"
        out = []
        for r in self.rooms.values():
            if r.kind != need or r.capacity < enrolment:
                continue
            if need == "lab" and c.lab_type and c.lab_type not in r.tags:
                continue
            out.append(r)
        return out


def load_dataset(src: Any) -> Dataset:
    """Load a dataset from a path or an already-parsed dict."""
    if isinstance(src, (str, Path)):
        src = json.loads(Path(src).read_text(encoding="utf-8"))
    if not isinstance(src, dict):
        raise DataError("Dataset must be a JSON object")
    try:
        return Dataset(src)
    except KeyError as e:
        raise DataError(f"Missing required field: {e}") from e
