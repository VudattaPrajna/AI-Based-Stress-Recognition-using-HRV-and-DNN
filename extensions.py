"""
Extension features for the HRV Stress Detection app.

This module is intentionally kept separate from app.py so the original
prediction pipeline (model / scaler / feature columns / /api/predict) is
never touched. It adds:

  1. Stress History        -> SQLite storage of every prediction
  2. Stress Trend / Dashboard -> today's stats + trend
  3. Daily Stress Summary   -> totals, most frequent state, stress score
  4. Prediction Report      -> downloadable PDF (reportlab)
  5. Stress Calendar        -> month view, dominant level per day
  6. User Profile           -> simple demo profile built from history

Database: stress_history.db (SQLite), table `predictions`.
"""

from __future__ import annotations

import io
import os
import sqlite3
import statistics
from collections import Counter
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Schema / constants
# ---------------------------------------------------------------------------

# Matches feature_columns.pkl exactly (33 HRV features used by the ANN).
FEATURE_COLUMNS: List[str] = [
    "MEAN_RR", "MEDIAN_RR", "SDRR", "RMSSD", "SDSD", "SDRR_RMSSD", "pNN25",
    "pNN50", "KURT", "SKEW", "MEAN_REL_RR", "MEDIAN_REL_RR", "SDRR_REL_RR",
    "RMSSD_REL_RR", "SDSD_REL_RR", "SDRR_RMSSD_REL_RR", "KURT_REL_RR",
    "SKEW_REL_RR", "VLF", "VLF_PCT", "LF", "LF_PCT", "LF_NU", "HF", "HF_PCT",
    "HF_NU", "TP", "LF_HF", "HF_LF", "SD1", "SD2", "sampen", "higuci",
]

# A short "headline" subset shown in compact views (history table, report).
HEADLINE_FEATURES: List[str] = ["MEAN_RR", "RMSSD", "SDRR", "LF", "HF"]

LEVEL_LABELS: Dict[str, str] = {
    "low": "Low Stress",
    "medium": "Medium Stress",
    "high": "High Stress",
    "unknown": "Unknown",
}

# Project-defined weights used ONLY to compute the in-app "Stress Score".
# This is a monitoring score, not a medical measurement.
LEVEL_SCORE: Dict[str, int] = {"low": 20, "medium": 55, "high": 90}
LEVEL_ORDER: Dict[str, int] = {"low": 1, "medium": 2, "high": 3}

DEFAULT_PROFILE_NAME = "Demo User"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stress_history.db")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the predictions table if it doesn't exist yet. Safe to call many times."""
    conn = get_db()
    try:
        feature_cols_sql = ",\n                ".join(f'"{c}" REAL' for c in FEATURE_COLUMNS)
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                stress_level TEXT NOT NULL,
                prediction_class INTEGER,
                prediction_label TEXT,
                {feature_cols_sql}
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_timestamp ON predictions(timestamp)")
        conn.commit()
    finally:
        conn.close()


def record_prediction(
    values: Dict[str, float],
    stress_level: str,
    prediction_class: Optional[int],
    prediction_label: str,
) -> int:
    """Persist one Predict Stress click: date, time, HRV values, level, class, label."""
    conn = get_db()
    try:
        cols = ["timestamp", "stress_level", "prediction_class", "prediction_label"] + FEATURE_COLUMNS
        placeholders = ",".join("?" for _ in cols)
        col_sql = ",".join(f'"{c}"' for c in cols)
        row = [
            datetime.now().isoformat(timespec="seconds"),
            stress_level,
            prediction_class,
            prediction_label,
        ]
        row += [_safe_float(values.get(c)) for c in FEATURE_COLUMNS]
        cur = conn.execute(f"INSERT INTO predictions ({col_sql}) VALUES ({placeholders})", row)
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    ts = d.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            d["date"] = dt.strftime("%d-%b-%Y")
            d["time"] = dt.strftime("%H:%M")
        except ValueError:
            d["date"], d["time"] = ts, ""
    d["stress_level_label"] = LEVEL_LABELS.get(d.get("stress_level"), d.get("stress_level"))
    return d


# ---------------------------------------------------------------------------
# Feature 1 — Stress History
# ---------------------------------------------------------------------------

def fetch_history(limit: int = 200, level: Optional[str] = None, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        query = "SELECT * FROM predictions WHERE 1=1"
        params: List[Any] = []
        if level and level in LEVEL_LABELS:
            query += " AND stress_level = ?"
            params.append(level)
        if date_str:
            query += " AND substr(timestamp, 1, 10) = ?"
            params.append(date_str)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, min(int(limit), 2000)))
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shared: fetch records for a given day
# ---------------------------------------------------------------------------

def _records_for_date(date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    d = date_str or date.today().isoformat()
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE substr(timestamp,1,10) = ? ORDER BY timestamp ASC",
            (d,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _trend_label(records: List[Dict[str, Any]]) -> str:
    """Compare first half vs second half of the day's stress levels."""
    if len(records) < 2:
        return "Stable"
    orders = [LEVEL_ORDER.get(r["stress_level"], 2) for r in records]
    mid = len(orders) // 2
    first_half = orders[:mid] or orders[:1]
    second_half = orders[mid:] or orders[-1:]
    a, b = statistics.mean(first_half), statistics.mean(second_half)
    if b - a > 0.15:
        return "Increasing"
    if a - b > 0.15:
        return "Decreasing"
    return "Stable"


def _overall_trend_label(records: List[Dict[str, Any]]) -> str:
    """Same comparison, phrased for the daily summary ('Improving' = trending down)."""
    trend = _trend_label(records)
    return {"Increasing": "Worsening", "Decreasing": "Improving", "Stable": "Stable"}[trend]


# ---------------------------------------------------------------------------
# Feature 2 — Stress Trend Graph / Dashboard
# ---------------------------------------------------------------------------

def trend_series(date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    records = _records_for_date(date_str)
    return [
        {
            "time": r["time"],
            "timestamp": r["timestamp"],
            "stress_level": r["stress_level"],
            "level_order": LEVEL_ORDER.get(r["stress_level"], 2),
        }
        for r in records
    ]


def dashboard_summary() -> Dict[str, Any]:
    records = _records_for_date(None)
    counts = Counter(r["stress_level"] for r in records)

    rmssd_values = [r["RMSSD"] for r in records if r.get("RMSSD") is not None]
    average_hrv = round(statistics.mean(rmssd_values), 3) if rmssd_values else None

    current = records[-1] if records else None

    return {
        "current_stress": current["stress_level"] if current else None,
        "current_stress_label": LEVEL_LABELS.get(current["stress_level"]) if current else "No predictions yet",
        "today_total": len(records),
        "low_count": counts.get("low", 0),
        "medium_count": counts.get("medium", 0),
        "high_count": counts.get("high", 0),
        "average_hrv": average_hrv,
        "average_hrv_metric": "RMSSD (ms)",
        "stress_trend": _trend_label(records),
        "date": date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# Feature 3 — Daily Stress Summary
# ---------------------------------------------------------------------------

def daily_summary(date_str: Optional[str] = None) -> Dict[str, Any]:
    d = date_str or date.today().isoformat()
    records = _records_for_date(d)
    counts = Counter(r["stress_level"] for r in records)

    total = len(records)
    most_frequent = counts.most_common(1)[0][0] if counts else None

    if total:
        score = round(sum(LEVEL_SCORE.get(r["stress_level"], 50) for r in records) / total)
    else:
        score = None

    return {
        "date": d,
        "total_predictions": total,
        "low_count": counts.get("low", 0),
        "medium_count": counts.get("medium", 0),
        "high_count": counts.get("high", 0),
        "most_frequent_state": LEVEL_LABELS.get(most_frequent) if most_frequent else "No data",
        "overall_trend": _overall_trend_label(records) if total else "No data",
        "stress_score": score,
        "stress_score_note": "Project-defined monitoring score (0-100), not a medical measurement.",
    }


# ---------------------------------------------------------------------------
# Feature 8 — Stress Calendar
# ---------------------------------------------------------------------------

def calendar_month(year: Optional[int] = None, month: Optional[int] = None) -> Dict[str, Any]:
    today = date.today()
    year = year or today.year
    month = month or today.month

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT substr(timestamp,1,10) AS d, stress_level FROM predictions "
            "WHERE substr(timestamp,1,10) >= ? AND substr(timestamp,1,10) < ?",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    by_day: Dict[str, Counter] = {}
    for r in rows:
        by_day.setdefault(r["d"], Counter())[r["stress_level"]] += 1

    days: Dict[str, Optional[str]] = {}
    cur = start
    while cur < end:
        key = cur.isoformat()
        c = by_day.get(key)
        days[key] = c.most_common(1)[0][0] if c else None
        cur += timedelta(days=1)

    return {"year": year, "month": month, "days": days}


# ---------------------------------------------------------------------------
# Feature 9 — User Profile
# ---------------------------------------------------------------------------

def profile_stats(name: str = DEFAULT_PROFILE_NAME) -> Dict[str, Any]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts "
            "FROM predictions"
        ).fetchone()
        level_rows = conn.execute(
            "SELECT stress_level, COUNT(*) AS c FROM predictions GROUP BY stress_level"
        ).fetchall()
        high_count = conn.execute(
            "SELECT COUNT(*) AS c FROM predictions WHERE stress_level = 'high'"
        ).fetchone()["c"]
    finally:
        conn.close()

    counts = {r["stress_level"]: r["c"] for r in level_rows}
    most_frequent = max(counts, key=counts.get) if counts else None

    def _fmt(ts: Optional[str]) -> Optional[str]:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts).strftime("%d %b %Y")
        except ValueError:
            return ts

    return {
        "name": name,
        "monitoring_start": _fmt(row["first_ts"]),
        "monitoring_end": _fmt(row["last_ts"]),
        "total_measurements": row["total"] or 0,
        "most_frequent_stress": LEVEL_LABELS.get(most_frequent) if most_frequent else "No data",
        "high_stress_episodes": high_count or 0,
    }


# ---------------------------------------------------------------------------
# Feature 5 — Prediction Report (PDF)
# ---------------------------------------------------------------------------

def build_report_pdf(date_str: Optional[str] = None, user_name: str = DEFAULT_PROFILE_NAME) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.legends import Legend

    d = date_str or date.today().isoformat()
    records = _records_for_date(d)
    summary = daily_summary(d)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6)
    body = styles["BodyText"]
    muted = ParagraphStyle("Muted", parent=styles["BodyText"], textColor=colors.HexColor("#555555"))

    story: List[Any] = []
    story.append(Paragraph("HRV STRESS ANALYSIS REPORT", title_style))
    story.append(Paragraph(f"User: {user_name}", body))
    story.append(Paragraph(f"Period: {_pretty_date(d)}", body))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#CCCCCC")))

    # Prediction Summary
    story.append(Paragraph("Prediction Summary", h2))
    summary_table = Table(
        [
            ["Stress Level", "Count"],
            ["Low Stress", str(summary["low_count"])],
            ["Medium Stress", str(summary["medium_count"])],
            ["High Stress", str(summary["high_count"])],
            ["Total", str(summary["total_predictions"])],
        ],
        colWidths=[8 * cm, 4 * cm],
    )
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEFF")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
    ]))
    story.append(summary_table)

    story.append(Paragraph(
        f"Most Frequent State: {summary['most_frequent_state']} &nbsp;&nbsp; "
        f"Overall Trend: {summary['overall_trend']}", body,
    ))
    if summary["stress_score"] is not None:
        story.append(Paragraph(f"Stress Score: {summary['stress_score']}/100", body))
        story.append(Paragraph(summary["stress_score_note"], muted))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#CCCCCC")))

    # Stress Trend chart
    story.append(Paragraph("Stress Trend", h2))
    if records:
        drawing = Drawing(420, 170)
        chart = HorizontalLineChart()
        chart.x, chart.y = 40, 30
        chart.width, chart.height = 350, 120
        levels = [LEVEL_ORDER.get(r["stress_level"], 2) for r in records]
        chart.data = [levels]
        chart.categoryAxis.categoryNames = [r["time"] for r in records]
        chart.categoryAxis.labels.angle = 45
        chart.categoryAxis.labels.dy = -12
        chart.categoryAxis.labels.fontSize = 6
        chart.valueAxis.valueMin = 0.5
        chart.valueAxis.valueMax = 3.5
        chart.valueAxis.valueStep = 1
        chart.lines[0].strokeColor = colors.HexColor("#7C5CFF")
        chart.lines[0].strokeWidth = 2
        drawing.add(chart)
        story.append(drawing)
        story.append(Paragraph("Y axis: 1 = Low, 2 = Medium, 3 = High.", muted))
    else:
        story.append(Paragraph("No predictions recorded for this date.", muted))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#CCCCCC")))

    # HRV Analysis (averages across the day's records)
    story.append(Paragraph("HRV Analysis (daily averages)", h2))
    if records:
        hrv_rows = [["Feature", "Average Value"]]
        for feat in HEADLINE_FEATURES + [f for f in FEATURE_COLUMNS if f not in HEADLINE_FEATURES]:
            vals = [r.get(feat) for r in records if r.get(feat) is not None]
            if vals:
                hrv_rows.append([feat, f"{statistics.mean(vals):.4f}"])
        hrv_table = Table(hrv_rows, colWidths=[6 * cm, 6 * cm], repeatRows=1)
        hrv_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
        ]))
        story.append(hrv_table)
    else:
        story.append(Paragraph("No HRV data available for this date.", muted))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#CCCCCC")))

    # Recommendations
    story.append(Paragraph("Recommendations", h2))
    recs = _recommendations_for(summary["most_frequent_state"])
    for i, r in enumerate(recs, start=1):
        story.append(Paragraph(f"{i}. {r}", body))

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This report is generated for project demonstration purposes and does not "
        "constitute a medical diagnosis.", muted,
    ))

    doc.build(story)
    return buf.getvalue()


def _pretty_date(date_str: str) -> str:
    try:
        return datetime.fromisoformat(date_str).strftime("%d %B %Y")
    except ValueError:
        return date_str


def _recommendations_for(most_frequent_label: str) -> List[str]:
    if most_frequent_label == LEVEL_LABELS["high"]:
        return [
            "Practice relaxation and slow breathing exercises.",
            "Take regular breaks throughout the day.",
            "Maintain physical activity and consider professional support if this persists.",
        ]
    if most_frequent_label == LEVEL_LABELS["medium"]:
        return [
            "Take short breaks between focused work sessions.",
            "Try a brief mindfulness or breathing exercise.",
            "Keep an eye on workload and prioritize one task at a time.",
        ]
    if most_frequent_label == LEVEL_LABELS["low"]:
        return [
            "Maintain your current routine and regular breaks.",
            "Keep up consistent sleep and physical activity.",
            "Continue periodic monitoring to catch early changes.",
        ]
    return [
        "Practice relaxation techniques.",
        "Take regular breaks.",
        "Maintain physical activity.",
    ]
