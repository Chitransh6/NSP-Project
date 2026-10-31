# AI-Based Timetable Generation System (NEP 2020)

Generates clash-free timetables for **multidisciplinary, credit-based programmes** as described in
the National Education Policy 2020 / UGC curriculum framework (Major, Minor, MDC, AEC, SEC, VAC).
It uses **constraint programming with optimisation** (Google OR-Tools CP-SAT) to find a timetable that
satisfies every hard rule and then improves quality (fewer gaps, balanced days, sensible rooms).

## Quick start

```bash
pip install -r requirements.txt

python main.py --data data/sample_data.json --out output --time-limit 30   # command line
python app.py                                                              # web UI -> http://127.0.0.1:5000
python -m pytest -q                                                        # tests
```

Command-line output: `output/timetable.xlsx` (a grid per student group, faculty and room, a flat session
list, faculty workload and the NEP report) and `output/timetable.json`.

## What makes it NEP 2020 aligned

| NEP 2020 idea | How the system handles it |
|---|---|
| Credit-based courses (L-T-P) | Weekly periods are derived from credits: 1 lecture credit = 1 period, 1 tutorial credit = 1 period, 1 practical credit = one 2-period lab block (`config.hours_per_credit`). |
| Choice of courses / elective baskets | A **basket** holds several courses (Minor pool, MDC pool, SEC pool). Every option is scheduled in **parallel** (same slots), each with its own faculty and room, so a student can pick any option without a clash. |
| Multidisciplinary exposure | Courses carry a `department`; the NEP report checks each student group takes courses from outside its own department. |
| Course categories | MAJOR, MINOR, MDC, AEC, SEC, VAC with per-semester minimum credits (`nep.required_categories`). |
| Credit load per semester | Checked against `nep.credit_range`; weekly contact hours checked against `nep.max_weekly_contact_hours`. |
| Joint classes | A course listed for several groups (e.g. AEC English for all of Semester 1) becomes one session with the combined enrolment and a hall large enough for it. |
| Visiting / part-time faculty | `unavailable` days or periods per faculty member are respected. |

All limits are editable in the dataset, so a university can encode its own ordinances.

## How it works

```
dataset.json -> models.py (validate, credits -> events)
             -> diagnostics.py (capacity pre-check, explains likely infeasibility)
             -> solver.py (CP-SAT model: hard rules + weighted soft goals)
             -> validator.py (independent re-check of every hard rule on the output)
             -> nep.py (compliance report)    -> exporter.py (Excel) / app.py (web)
```

**Hard constraints** - no faculty, room or student-group double booking; room type (classroom/lab/lab tag)
and capacity; faculty availability, hours per day and per week; blocks never cross a break or the end of the
day; basket options run in parallel; one teacher per course; a course meets at most `ceil(n/days)` times a day;
cohort daily load cap.

**Soft goals** (weights in `config.weights`) - fewer idle gaps in student days, balanced daily load,
avoid penalised days (e.g. Saturday), labs in the afternoon, smallest suitable room.

The solver also chooses the teacher when a course lists several eligible faculty.

## Dataset format (`data/sample_data.json`)

```jsonc
{
  "config":  {"days": [...], "periods": [{"label","start","end"}], "breaks_after": [4],
              "afternoon_start": 5, "max_cohort_periods_per_day": 7,
              "hours_per_credit": {"L":1,"T":1,"P":2}, "day_penalty": {"Sat": 2}},
  "nep":     {"credit_range": [18,26], "max_weekly_contact_hours": 30, "required_categories": [...]},
  "cohorts": [{"id","name","department","semester","size"}],
  "faculty": [{"id","name","department","max_hours_per_day","max_hours_per_week",
               "unavailable": [{"day":"Thu"}, {"day":"Sat","periods":[5,6,7,8]}]}],
  "rooms":   [{"id","name","kind":"classroom|lab","capacity","tags":["physics"]}],
  "baskets": [{"id","name","category","cohorts":[...]}],
  "courses": [{"id","name","category","department","credits":{"L":3,"T":1,"P":0},
               "faculty":["F01","F02"], "cohorts":[...], "enrolment":45,
               "lab_type":"physics", "basket":"BK-..."}]
}
```

Courses inside a basket omit `cohorts` (taken from the basket) and must share the same L-T-P pattern.
Rebuild the sample with `python scripts/build_sample_data.py`.

## Project layout

```
app.py                  Flask web app (generate, Excel/JSON download)
main.py                 command-line interface
timetable/              models, solver, validator, nep, diagnostics, pipeline, exporter
templates/index.html    web UI
data/sample_data.json   6 student groups, 35 courses, 7 baskets, 22 faculty, 13 rooms
scripts/                sample data generator
tests/                  pytest suite
output/                 sample generated timetable.xlsx / timetable.json
```

## Notes and limits

- Larger institutions need more solve time: raise `--time-limit` (the solver reports `FEASIBLE` for a good
  solution and `OPTIMAL` when it proves the best one). More CPU cores help.
- `UNKNOWN` means no solution was found in the time limit; `INFEASIBLE` means the rules cannot all hold -
  see the capacity analysis for the likely cause.
- Not included: exam timetables, substitution handling, authentication/multi-user storage.
