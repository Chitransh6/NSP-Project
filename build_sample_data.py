"""Generates data/sample_data.json - a small multidisciplinary university.

Semester 1 and semester 3 cohorts of four departments, with NEP 2020 style
categories: Major, Minor baskets, MDC baskets, AEC, SEC baskets and VAC.
Run:  python scripts/build_sample_data.py
"""
import json
from pathlib import Path

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
PERIODS = [("P1", "09:00", "09:55"), ("P2", "09:55", "10:50"), ("P3", "11:05", "12:00"),
           ("P4", "12:00", "12:55"), ("P5", "13:45", "14:40"), ("P6", "14:40", "15:35"),
           ("P7", "15:50", "16:45"), ("P8", "16:45", "17:40")]

cohorts = [
    ("PHY1", "B.Sc. Physics - Sem 1", "Physics", 1, 40),
    ("CHM1", "B.Sc. Chemistry - Sem 1", "Chemistry", 1, 40),
    ("ECO1", "B.A. Economics - Sem 1", "Economics", 1, 45),
    ("CS1", "B.Sc. Computer Science - Sem 1", "Computer Science", 1, 40),
    ("PHY3", "B.Sc. Physics - Sem 3", "Physics", 3, 38),
    ("CS3", "B.Sc. Computer Science - Sem 3", "Computer Science", 3, 42),
]
S1 = ["PHY1", "CHM1", "ECO1", "CS1"]
S3 = ["PHY3", "CS3"]

# id, name, dept, (max/day, max/week), unavailable
faculty = [
    ("F01", "Dr. Anil Sharma", "Physics"), ("F02", "Dr. Meera Iyer", "Physics"),
    ("F03", "Dr. Rohit Verma", "Physics"), ("F04", "Dr. Kavita Rao", "Chemistry"),
    ("F05", "Dr. Sanjay Gupta", "Chemistry"), ("F06", "Dr. Neha Kapoor", "Economics"),
    ("F07", "Dr. Arvind Menon", "Economics"), ("F08", "Dr. Priya Nair", "Computer Science"),
    ("F09", "Mr. Rahul Jain", "Computer Science"), ("F10", "Dr. Sneha Patel", "Computer Science"),
    ("F11", "Mr. Imran Khan (visiting)", "Computer Science"), ("F12", "Dr. Vikram Singh", "Mathematics"),
    ("F13", "Dr. Anjali Desai", "Mathematics"), ("F14", "Dr. Farah Ahmed", "English"),
    ("F15", "Dr. Mohan Das", "Environmental Science"), ("F16", "Dr. Lata Mishra", "Psychology"),
    ("F17", "Dr. Karan Malhotra", "Political Science"), ("F18", "Ms. Isha Bose", "Music"),
    ("F19", "Dr. Rajeev Sinha", "Humanities"), ("F20", "Dr. Tara Joshi", "Environmental Science"),
    ("F21", "Mr. Sameer Ali (visiting)", "Management"), ("F22", "Dr. Pooja Reddy", "Statistics"),
]
UNAVAILABLE = {
    "F11": [{"day": "Thu"}, {"day": "Fri"}],                     # visiting: Mon-Wed, Sat
    "F21": [{"day": "Thu"}, {"day": "Fri"}, {"day": "Sat"}],      # visiting: Mon-Wed
    "F14": [{"day": "Sat", "periods": [5, 6, 7, 8]}],
}

rooms = [("CR-101", 60), ("CR-102", 60), ("CR-103", 60), ("CR-104", 60),
         ("CR-105", 50), ("CR-106", 50), ("CR-107", 50), ("CR-108", 50)]
room_rows = [{"id": i, "name": f"Classroom {i[3:]}", "kind": "classroom", "capacity": c} for i, c in rooms]
room_rows.append({"id": "SEM-HALL", "name": "Seminar Hall", "kind": "classroom", "capacity": 200, "tags": ["hall"]})
room_rows += [
    {"id": "LAB-PHY", "name": "Physics Lab", "kind": "lab", "capacity": 45, "tags": ["physics"]},
    {"id": "LAB-CHM", "name": "Chemistry Lab", "kind": "lab", "capacity": 45, "tags": ["chemistry"]},
    {"id": "LAB-CS1", "name": "Computer Lab 1", "kind": "lab", "capacity": 60, "tags": ["computer"]},
    {"id": "LAB-CS2", "name": "Computer Lab 2", "kind": "lab", "capacity": 60, "tags": ["computer"]},
]

courses, baskets = [], []


def C(cid, name, cat, dept, ltp, fac, cohorts=None, enrol=None, lab=None, basket=None):
    row = {"id": cid, "name": name, "category": cat, "department": dept,
           "credits": dict(zip("LTP", ltp)), "faculty": fac}
    if basket:
        row["basket"] = basket
    else:
        row["cohorts"] = cohorts
    if enrol:
        row["enrolment"] = enrol
    if lab:
        row["lab_type"] = lab
    courses.append(row)


def B(bid, name, cat, cohorts):
    baskets.append({"id": bid, "name": name, "category": cat, "cohorts": cohorts})


# ---- Semester 1 : Major (DSC) ---------------------------------------------------------
C("PHY101", "Mechanics & Waves", "MAJOR", "Physics", (3, 0, 1), ["F01", "F02"], ["PHY1"], lab="physics")
C("MAT101", "Mathematical Physics I", "MAJOR", "Mathematics", (3, 1, 0), ["F12"], ["PHY1"])
C("CHM101", "Atomic Structure & Bonding", "MAJOR", "Chemistry", (3, 0, 1), ["F04"], ["CHM1"], lab="chemistry")
C("CHM102", "Basic Organic Chemistry", "MAJOR", "Chemistry", (3, 1, 0), ["F05"], ["CHM1"])
C("ECO101", "Microeconomics I", "MAJOR", "Economics", (3, 1, 0), ["F06"], ["ECO1"])
C("ECO102", "Quantitative Methods I", "MAJOR", "Economics", (3, 1, 0), ["F07"], ["ECO1"])
C("CSC101", "Programming Fundamentals", "MAJOR", "Computer Science", (3, 0, 1), ["F08", "F09"], ["CS1"], lab="computer")
C("CSC102", "Discrete Mathematics", "MAJOR", "Mathematics", (3, 1, 0), ["F13"], ["CS1"])

# ---- Semester 1 : Minor baskets, MDC, AEC, VAC, SEC ----------------------------------------
B("BK-MIN-S1-SCI", "Minor Pool - Sciences (Sem 1)", "MINOR", ["PHY1", "CHM1"])
C("MIN101", "Calculus for Sciences", "MINOR", "Mathematics", (3, 1, 0), ["F12"], enrol=45, basket="BK-MIN-S1-SCI")
C("MIN102", "Introductory Statistics", "MINOR", "Statistics", (3, 1, 0), ["F22", "F13"], enrol=45, basket="BK-MIN-S1-SCI")
B("BK-MIN-S1-SOC", "Minor Pool - Social Sciences (Sem 1)", "MINOR", ["ECO1", "CS1"])
C("MIN201", "Introduction to Psychology", "MINOR", "Psychology", (3, 1, 0), ["F16"], enrol=45, basket="BK-MIN-S1-SOC")
C("MIN202", "Political Science Basics", "MINOR", "Political Science", (3, 1, 0), ["F17"], enrol=45, basket="BK-MIN-S1-SOC")
B("BK-MDC-S1", "Multidisciplinary Pool (Sem 1)", "MDC", S1)
C("MDC101", "Sustainable Development", "MDC", "Environmental Science", (3, 0, 0), ["F20"], enrol=45, basket="BK-MDC-S1")
C("MDC102", "Music Appreciation", "MDC", "Music", (3, 0, 0), ["F18"], enrol=45, basket="BK-MDC-S1")
C("MDC103", "Data Literacy", "MDC", "Statistics", (3, 0, 0), ["F22"], enrol=45, basket="BK-MDC-S1")
C("MDC104", "Creative Writing", "MDC", "Humanities", (3, 0, 0), ["F19"], enrol=45, basket="BK-MDC-S1")
C("AEC101", "English Communication", "AEC", "English", (2, 0, 0), ["F14"], S1)
C("VAC101", "Environmental Studies", "VAC", "Environmental Science", (2, 0, 0), ["F15"], S1)
B("BK-SEC-S1", "Skill Pool (Sem 1)", "SEC", S1)
C("SEC101", "Python Programming", "SEC", "Computer Science", (1, 0, 1), ["F09", "F11"], enrol=60, lab="computer", basket="BK-SEC-S1")
C("SEC102", "Spreadsheet & Data Tools", "SEC", "Statistics", (1, 0, 1), ["F22", "F11"], enrol=60, lab="computer", basket="BK-SEC-S1")
C("SEC103", "Electronics Hobby Lab", "SEC", "Physics", (1, 0, 1), ["F03"], enrol=45, lab="physics", basket="BK-SEC-S1")

# ---- Semester 3 -------------------------------------------------------------------------
C("PHY301", "Thermal Physics", "MAJOR", "Physics", (3, 0, 1), ["F01", "F02"], ["PHY3"], lab="physics")
C("PHY302", "Electromagnetic Theory", "MAJOR", "Physics", (3, 1, 0), ["F03"], ["PHY3"])
C("PHY303", "Quantum Mechanics I", "MAJOR", "Physics", (3, 1, 0), ["F01", "F03"], ["PHY3"])
C("CSC301", "Data Structures", "MAJOR", "Computer Science", (3, 0, 1), ["F08", "F10"], ["CS3"], lab="computer")
C("CSC302", "Database Management Systems", "MAJOR", "Computer Science", (3, 0, 1), ["F09", "F10"], ["CS3"], lab="computer")
C("CSC303", "Computer Organization", "MAJOR", "Computer Science", (3, 1, 0), ["F10"], ["CS3"])
B("BK-MIN-S3", "Minor Pool (Sem 3)", "MINOR", S3)
C("MIN301", "Computational Mathematics", "MINOR", "Mathematics", (3, 1, 0), ["F12"], enrol=40, basket="BK-MIN-S3")
C("MIN302", "Applied Statistics", "MINOR", "Statistics", (3, 1, 0), ["F22", "F13"], enrol=40, basket="BK-MIN-S3")
B("BK-MDC-S3", "Multidisciplinary Pool (Sem 3)", "MDC", S3)
C("MDC301", "Entrepreneurship & Startups", "MDC", "Management", (3, 0, 0), ["F21"], enrol=30, basket="BK-MDC-S3")
C("MDC302", "Film Studies", "MDC", "Humanities", (3, 0, 0), ["F19"], enrol=30, basket="BK-MDC-S3")
C("MDC303", "Yoga & Wellness", "MDC", "Environmental Science", (3, 0, 0), ["F20"], enrol=30, basket="BK-MDC-S3")
C("AEC301", "Professional Communication", "AEC", "English", (2, 0, 0), ["F14"], S3)
B("BK-SEC-S3", "Skill Pool (Sem 3)", "SEC", S3)
C("SEC301", "Web Development Basics", "SEC", "Computer Science", (1, 0, 1), ["F09", "F11"], enrol=45, lab="computer", basket="BK-SEC-S3")
C("SEC302", "Scientific Computing with Python", "SEC", "Computer Science", (1, 0, 1), ["F10", "F22"], enrol=45, lab="computer", basket="BK-SEC-S3")

data = {
    "institution": "Sample Multidisciplinary University",
    "config": {
        "days": DAYS,
        "periods": [{"label": a, "start": b, "end": c} for a, b, c in PERIODS],
        "breaks_after": [4], "afternoon_start": 5, "max_cohort_periods_per_day": 7,
        "hours_per_credit": {"L": 1, "T": 1, "P": 2},
        "day_penalty": {"Sat": 2},
    },
    "nep": {
        "credit_range": [18, 26], "max_weekly_contact_hours": 30,
        "required_categories": [
            {"category": "MAJOR", "min_credits": 8, "semesters": [1, 2, 3, 4, 5, 6, 7, 8]},
            {"category": "MINOR", "min_credits": 4, "semesters": [1, 2, 3, 4]},
            {"category": "MDC", "min_credits": 3, "semesters": [1, 2, 3]},
            {"category": "AEC", "min_credits": 2, "semesters": [1, 2, 3, 4]},
            {"category": "SEC", "min_credits": 2, "semesters": [1, 2, 3]},
            {"category": "VAC", "min_credits": 2, "semesters": [1, 2]},
        ],
    },
    "cohorts": [{"id": i, "name": n, "department": d, "semester": s, "size": z} for i, n, d, s, z in cohorts],
    "faculty": [{"id": i, "name": n, "department": d, "max_hours_per_day": 5, "max_hours_per_week": 18,
                 "unavailable": UNAVAILABLE.get(i, [])} for i, n, d in faculty],
    "rooms": room_rows,
    "baskets": baskets,
    "courses": courses,
}

out = Path(__file__).resolve().parent.parent / "data" / "sample_data.json"
out.write_text(json.dumps(data, indent=2), encoding="utf-8")
print(f"Wrote {out}  ({len(courses)} courses, {len(baskets)} baskets, {len(cohorts)} cohorts)")
