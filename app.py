"""Web interface:  python app.py  ->  http://127.0.0.1:5000"""
import io
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from timetable.exporter import export_xlsx
from timetable.models import DataError, load_dataset
from timetable.pipeline import generate_timetable

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "sample_data.json"

app = Flask(__name__)
LAST = {}   # last generated {"ds": Dataset, "result": dict}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/sample")
def sample():
    return jsonify(json.loads(SAMPLE.read_text(encoding="utf-8")))


@app.post("/api/generate")
def generate():
    body = request.get_json(force=True, silent=True) or {}
    try:
        ds = load_dataset(body.get("data"))
    except DataError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    limit = max(5.0, min(float(body.get("time_limit", 20)), 300.0))
    result = generate_timetable(ds, time_limit=limit)
    LAST["ds"], LAST["result"] = ds, result
    return jsonify(result)


@app.get("/api/export/xlsx")
def export_excel():
    if "ds" not in LAST or not LAST["result"]["ok"]:
        return jsonify({"error": "Generate a timetable first."}), 409
    buf = io.BytesIO()
    tmp = ROOT / "output" / "_download.xlsx"
    tmp.parent.mkdir(exist_ok=True)
    export_xlsx(LAST["ds"], LAST["result"], str(tmp))
    buf.write(tmp.read_bytes())
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="timetable.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/export/json")
def export_json():
    if "result" not in LAST:
        return jsonify({"error": "Generate a timetable first."}), 409
    return send_file(io.BytesIO(json.dumps(LAST["result"], indent=2).encode()), as_attachment=True,
                     download_name="timetable.json", mimetype="application/json")


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)
