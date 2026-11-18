# HRV-based Stress Detection (Flask)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Required model artifacts

Place these files in the same folder as `app.py`:

- `stress_ann_model.h5`
- `scaler.pkl`
- `feature_columns.pkl`

These are the same artifacts used by your Gradio demo in `Stress_heartrate_full.ipynb`.

## Run

```bash
python app.py
```

Then open `http://127.0.0.1:5000`.

## Extension features

Added on top of the original prediction pipeline (nothing above was changed):

- **Stress History** — every "Predict Stress" click is saved to `stress_history.db`
  (SQLite, created automatically on first run) with date, time, the full HRV
  feature vector, predicted class/level and label. View it at `/history`.
- **Dashboard** (`/dashboard`) — current stress, today's Low/Medium/High counts,
  average HRV (RMSSD), and a live stress-trend chart (Chart.js).
- **Daily Stress Summary** — totals, most frequent state, overall trend, and a
  project-defined **Stress Score (0-100)**. This score is a monitoring aid only,
  not a medical measurement. See `/report` or `GET /api/daily-summary`.
- **Prediction Report** (`/report`) — "Generate Report" downloads a PDF
  (via `GET /api/report.pdf?date=YYYY-MM-DD`) with the prediction summary,
  a stress-trend chart, HRV feature averages, and recommendations.
- **Stress Calendar** (`/calendar`) — month view colored by each day's most
  frequent stress level (green/yellow/red).
- **User Profile** (`/profile`) — simple, no-login demo profile: monitoring
  period, total measurements, most frequent stress, high-stress episode count.

New files: `extensions.py` (DB + report logic), `templates/history.html`,
`templates/dashboard.html`, `templates/calendar.html`, `templates/profile.html`,
`templates/report.html`, and matching files under `static/js/`.
`stress_history.db` is created next to `app.py` the first time the app runs.
