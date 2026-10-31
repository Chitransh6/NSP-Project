#!/usr/bin/env python3
"""Command-line interface.

    python main.py --data data/sample_data.json --out output --time-limit 30
"""
import argparse
import json
import sys
from pathlib import Path

from timetable.exporter import export_xlsx
from timetable.models import DataError, load_dataset
from timetable.pipeline import generate_timetable


def main() -> int:
    ap = argparse.ArgumentParser(description="AI-based NEP 2020 timetable generator")
    ap.add_argument("--data", default="data/sample_data.json", help="dataset JSON")
    ap.add_argument("--out", default="output", help="output folder")
    ap.add_argument("--time-limit", type=float, default=30, help="solver time limit in seconds")
    ap.add_argument("--workers", type=int, default=0, help="0 = auto (CPU count, max 8)")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    try:
        ds = load_dataset(a.data)
    except DataError as e:
        print(f"Invalid dataset: {e}", file=sys.stderr)
        return 2
    print(f"Solving {len(ds.cohorts)} cohorts, {len(ds.courses)} courses, "
          f"{len(ds.faculty)} faculty, {len(ds.rooms)} rooms ...")
    res = generate_timetable(ds, a.time_limit, a.workers, a.seed)

    for i in res["diagnostics"]:
        print(f"  [{i['level']}] {i['message']}")
    print(f"Status: {res['status']}  ({res['wall_time']}s)")
    if not res["ok"]:
        print(res.get("note", ""))
        return 1

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "timetable.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    export_xlsx(ds, res, str(out / "timetable.xlsx"))
    n = res["nep"]["summary"]
    print(f"Sessions: {len(res['sessions'])} | idle gaps: {res['metrics']['total_gaps']} | "
          f"violations: {len(res['violations'])}")
    print(f"NEP checks: {n['PASS']} pass, {n['WARN']} warn, {n['FAIL']} fail")
    print(f"Saved {out/'timetable.xlsx'} and {out/'timetable.json'}")
    return 0 if not res["violations"] else 1


if __name__ == "__main__":
    sys.exit(main())
