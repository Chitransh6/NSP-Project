import copy
import json
from pathlib import Path

import pytest

from timetable.models import DataError, load_dataset
from timetable.nep import check_nep
from timetable.pipeline import generate_timetable
from timetable.validator import validate

DATA = Path(__file__).resolve().parent.parent / "data" / "sample_data.json"


@pytest.fixture(scope="module")
def raw():
    return json.loads(DATA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def solved(raw):
    ds = load_dataset(copy.deepcopy(raw))
    return ds, generate_timetable(ds, time_limit=15)


def test_sample_is_solved(solved):
    _, res = solved
    assert res["ok"], res.get("note")
    assert len(res["sessions"]) > 100


def test_no_hard_constraint_violations(solved):
    ds, res = solved
    assert validate(ds, res["sessions"]) == []


def test_nep_rules_pass(solved):
    _, res = solved
    assert res["nep"]["summary"]["FAIL"] == 0


def test_credit_to_hours_mapping(raw):
    ds = load_dataset(copy.deepcopy(raw))
    c = ds.courses["PHY101"]               # 3-0-1 -> 3 lecture periods + one 2-period lab block
    assert sorted(ds.course_events(c)) == [("practical", 2), ("theory", 1), ("theory", 1), ("theory", 1)]
    assert ds.weekly_hours(c) == 5


def test_basket_options_run_in_parallel(solved):
    ds, res = solved
    for b in ds.baskets.values():
        slots = {cid: {(s["day"], s["period"]) for s in res["sessions"] if s["course_id"] == cid}
                 for cid in b.course_ids}
        assert len({frozenset(v) for v in slots.values()}) == 1


def test_validator_detects_injected_clash(solved):
    ds, res = solved
    sessions = copy.deepcopy(res["sessions"])
    victim = sessions[0]
    clone = copy.deepcopy(victim)
    clone["event_id"] = "FAKE#1"
    sessions.append(clone)
    kinds = {v["type"] for v in validate(ds, sessions)}
    assert {"faculty-clash", "room-clash"} <= kinds


def test_infeasible_when_faculty_never_available(raw):
    bad = copy.deepcopy(raw)
    for f in bad["faculty"]:
        if f["id"] == "F14":               # only English teacher
            f["unavailable"] = [{"day": d} for d in bad["config"]["days"]]
    res = generate_timetable(load_dataset(bad), time_limit=10)
    assert not res["ok"]


def test_diagnostics_flag_overloaded_faculty(raw):
    bad = copy.deepcopy(raw)
    for f in bad["faculty"]:
        if f["id"] == "F14":
            f["max_hours_per_week"] = 2
    res = generate_timetable(load_dataset(bad), time_limit=5)
    assert not res["ok"]
    assert any(i["level"] == "error" for i in res["diagnostics"])


def test_bad_dataset_rejected(raw):
    bad = copy.deepcopy(raw)
    bad["courses"][0]["faculty"] = ["NOBODY"]
    with pytest.raises(DataError):
        load_dataset(bad)


def test_nep_credit_failure_is_reported(raw):
    bad = copy.deepcopy(raw)
    bad["nep"]["credit_range"] = [30, 40]
    rep = check_nep(load_dataset(bad))
    assert rep["summary"]["FAIL"] > 0
