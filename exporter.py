"""Excel export: summary, one grid per cohort / faculty / room, flat session list."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import Dataset

FILL = {"MAJOR": "D6E4FF", "MINOR": "D9F2E1", "MDC": "FFE8C2", "AEC": "F4D9F0",
        "SEC": "D5F0F5", "VAC": "FFF3B8", "OTHER": "E6E6E6"}
THIN = Side(style="thin", color="B8C0CC")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _safe(name: str) -> str:
    return re.sub(r"[\[\]\*\?/\\:]", "-", name)[:31]


def _cell_text(group: List[Dict[str, Any]], view: str) -> str:
    def line(s: Dict[str, Any]) -> str:
        if view == "cohort":
            tail = f"{s['faculty_name']} | {s['room_id']}"
        elif view == "faculty":
            tail = f"{', '.join(s['cohorts'])} | {s['room_id']}"
        else:
            tail = f"{s['faculty_name']} | {', '.join(s['cohorts'])}"
        tag = " (Lab)" if s["kind"] == "practical" else " (Tut)" if s["kind"] == "tutorial" else ""
        return f"{s['course_id']} {s['course_name']}{tag}\n{tail}"
    if len(group) == 1 or view != "cohort":
        return "\n".join(line(s) for s in group)
    head = group[0].get("basket_name") or "Elective basket"
    return f"[{head} - choose one]\n" + "\n".join("- " + line(s).replace("\n", " | ") for s in group)


def _grid(wb: Workbook, ds: Dataset, title: str, sub: str, sessions: List[Dict[str, Any]], view: str) -> None:
    cfg = ds.config
    ws = wb.create_sheet(_safe(title))
    ws["A1"] = f"{title}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = sub
    ws["A2"].font = Font(italic=True, color="555555")
    ws.cell(row=4, column=1, value="Period").font = Font(bold=True)
    for d, name in enumerate(cfg.days):
        c = ws.cell(row=4, column=2 + d, value=name)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="22313F")
        c.alignment = Alignment(horizontal="center")
    ws.cell(row=4, column=1).fill = PatternFill("solid", fgColor="22313F")
    ws.cell(row=4, column=1).font = Font(bold=True, color="FFFFFF")
    row_of, row = {}, 5
    for p, per in enumerate(cfg.periods):
        row_of[p] = row
        c = ws.cell(row=row, column=1, value=f"{per.label}\n{per.start}-{per.end}")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.font = Font(bold=True)
        ws.row_dimensions[row].height = 52
        row += 1
        if (p + 1) in cfg.breaks_after:
            ws.cell(row=row, column=1, value="Break").font = Font(italic=True, color="777777")
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=1 + cfg.n_days)
            ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="EEEEEE")
            row += 1
    groups: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for s in sessions:
        groups[s["day"], s["period"], s["duration"]].append(s)
    for (d, p, dur), grp in groups.items():
        r1, r2, col = row_of[p], row_of[p + dur - 1], 2 + d
        cell = ws.cell(row=r1, column=col, value=_cell_text(grp, view))
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.fill = PatternFill("solid", fgColor=FILL.get(grp[0]["category"], "FFFFFF"))
        if r2 > r1:
            ws.merge_cells(start_row=r1, start_column=col, end_row=r2, end_column=col)
    for r in range(5, row):
        for c in range(1, 2 + cfg.n_days):
            ws.cell(row=r, column=c).border = BORDER
    ws.column_dimensions["A"].width = 14
    for d in range(cfg.n_days):
        ws.column_dimensions[get_column_letter(2 + d)].width = 34


def export_xlsx(ds: Dataset, result: Dict[str, Any], path: str) -> str:
    sessions = result["sessions"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"{ds.institution} - NEP 2020 Timetable"
    ws["A1"].font = Font(bold=True, size=16)
    rows = [("Solver status", result["status"]), ("Sessions scheduled", len(sessions)),
            ("Solve time (s)", result.get("wall_time")), ("Total idle gaps (students)",
                                                           result.get("metrics", {}).get("total_gaps", "-")),
            ("Constraint violations", len(result.get("violations", []))),
            ("NEP checks passed", result["nep"]["summary"]["PASS"]),
            ("NEP warnings", result["nep"]["summary"]["WARN"]),
            ("NEP failures", result["nep"]["summary"]["FAIL"])]
    for i, (k, v) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=i, column=2, value=v)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 22

    for coh in ds.cohorts.values():
        _grid(wb, ds, f"C-{coh.id}", f"{coh.name} | semester {coh.semester} | {coh.size} students",
              [s for s in sessions if coh.id in s["cohorts"]], "cohort")
    for f in ds.faculty.values():
        _grid(wb, ds, f"F-{f.id}", f"{f.name} | {f.department}",
              [s for s in sessions if s["faculty_id"] == f.id], "faculty")
    for r in ds.rooms.values():
        _grid(wb, ds, f"R-{r.id}", f"{r.name} | {r.kind} | capacity {r.capacity}",
              [s for s in sessions if s["room_id"] == r.id], "room")

    ws = wb.create_sheet("All Sessions")
    head = ["Day", "Start", "End", "Course", "Name", "Category", "Type", "Cohorts", "Faculty", "Room", "Basket"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for s in sorted(sessions, key=lambda x: (x["day"], x["period"], x["course_id"])):
        ws.append([s["day_name"], s["start_time"], s["end_time"], s["course_id"], s["course_name"],
                   s["category"], s["kind"], ", ".join(s["cohorts"]), s["faculty_name"], s["room_id"],
                   s["basket_name"] or ""])
    for i, w in enumerate([8, 8, 8, 10, 36, 10, 10, 20, 24, 12, 28], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws = wb.create_sheet("Faculty Workload")
    ws.append(["Faculty", "Name", "Hours/week", "Max/week"] + ds.config.days)
    for c in ws[1]:
        c.font = Font(bold=True)
    for fid, m in result.get("metrics", {}).get("faculty_load", {}).items():
        ws.append([fid, ds.faculty[fid].name, m["week"], m["max_week"]] + m["per_day"])
    ws.column_dimensions["B"].width = 26

    ws = wb.create_sheet("NEP Compliance")
    ws.append(["Cohort", "Check", "Status", "Detail"])
    for c in ws[1]:
        c.font = Font(bold=True)
    colour = {"PASS": "C6EFCE", "WARN": "FFEB9C", "FAIL": "FFC7CE"}
    for cid, info in result["nep"]["cohorts"].items():
        for ch in info["checks"]:
            ws.append([cid, ch["name"], ch["status"], ch["detail"]])
            ws.cell(row=ws.max_row, column=3).fill = PatternFill("solid", fgColor=colour[ch["status"]])
    for i, w in enumerate([14, 28, 10, 70], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    wb.save(path)
    return path
