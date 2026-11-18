import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from tensorflow.keras.models import load_model

import extensions as ext
import auth as authm

APP_TITLE = "HRV-based Stress Detection"


@dataclass
class Artifacts:
    model: Any
    scaler: Any
    feature_columns: List[str]


_artifacts: Optional[Artifacts] = None
_artifacts_error: Optional[str] = None


def _artifact_paths() -> Tuple[str, str, str]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return (
        os.path.join(base_dir, "stress_ann_model.h5"),
        os.path.join(base_dir, "scaler.pkl"),
        os.path.join(base_dir, "feature_columns.pkl"),
    )


def get_artifacts() -> Optional[Artifacts]:
    global _artifacts, _artifacts_error
    if _artifacts is not None or _artifacts_error is not None:
        return _artifacts

    model_path, scaler_path, cols_path = _artifact_paths()

    missing = [p for p in (model_path, scaler_path, cols_path) if not os.path.exists(p)]
    if missing:
        _artifacts_error = (
            "Missing required files: "
            + ", ".join(os.path.basename(p) for p in missing)
            + ". Put them in the same folder as app.py."
        )
        return None

    try:
        model = load_model(model_path)
        scaler = joblib.load(scaler_path)
        feature_columns = joblib.load(cols_path)
        feature_columns = [str(c) for c in feature_columns]
        _artifacts = Artifacts(model=model, scaler=scaler, feature_columns=feature_columns)
        return _artifacts
    except Exception as e:
        _artifacts_error = f"Failed to load model/scaler/columns: {e}"
        return None


def artifacts_status() -> Dict[str, Any]:
    model_path, scaler_path, cols_path = _artifact_paths()
    return {
        "ready": get_artifacts() is not None,
        "error": _artifacts_error,
        "expected_files": {
            "stress_ann_model.h5": os.path.exists(model_path),
            "scaler.pkl": os.path.exists(scaler_path),
            "feature_columns.pkl": os.path.exists(cols_path),
        },
    }


def _class_to_label_and_level(cls: int) -> Tuple[str, str]:
    # User-requested labels:
    # - Interruption -> Medium level stress
    # - Time pressure -> High stress
    # - No stress -> Low stress
    mapping = {
        0: ("Medium level stress", "medium"),
        1: ("Low stress", "low"),
        2: ("High stress", "high"),
    }
    return mapping.get(cls, (f"Unknown ({cls})", "unknown"))


def _suggestions_for_level(level: str) -> List[str]:
    if level == "high":
        return [
            "Pause and take 8–10 slow breaths (inhale 4s, exhale 6s).",
            "Reduce cognitive load for 10 minutes: close extra tabs, single-task.",
            "Hydrate and do a short walk or gentle stretch break.",
            "If this persists, consider resting and revisiting the task with a plan.",
        ]
    if level == "medium":
        return [
            "Do a 2-minute reset: relaxed breathing and drop shoulder tension.",
            "Prioritize the next one task (write it down) before continuing.",
            "Try a 25/5 focus cycle (Pomodoro) to reduce pressure build-up.",
        ]
    if level == "low":
        return [
            "Great — your HRV pattern is consistent with a calm/low-stress state.",
            "Keep your current pace and take regular short breaks to maintain it.",
        ]
    return ["No suggestions available for this prediction."]


def predict_from_values(values_by_feature: Dict[str, float]) -> Tuple[str, str, List[str]]:
    art = get_artifacts()
    if art is None:
        raise RuntimeError(_artifacts_error or "Artifacts not loaded.")

    x = np.array([values_by_feature[c] for c in art.feature_columns], dtype=np.float32).reshape(1, -1)
    x = art.scaler.transform(x)

    pred = art.model.predict(x, verbose=0)
    cls = int(np.argmax(pred))
    label, level = _class_to_label_and_level(cls)
    suggestions = _suggestions_for_level(level)
    return label, level, suggestions


def random_values_dict() -> Dict[str, float]:
    art = get_artifacts()
    if art is None:
        raise RuntimeError(_artifacts_error or "Artifacts not loaded.")
    vals = np.random.uniform(0, 1, len(art.feature_columns)).astype(float).tolist()
    return {k: float(v) for k, v in zip(art.feature_columns, vals)}


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hrv-stress-dnn-app-dev-secret-key")

# Extension: create stress_history.db (if missing) on startup. Never touches
# the model/scaler/feature_columns artifacts above.
ext.init_db()

# Extension: create users.db (if missing) on startup for login/registration.
authm.init_db()


# ---------------------------------------------------------------------------
# Auth extension — landing page, register, login, logout.
# These are purely additive and do not modify the prediction pipeline above.
# ---------------------------------------------------------------------------

@app.get("/")
def landing():
    if authm.current_user():
        return redirect(url_for("home"))
    return render_template("landing.html", title=APP_TITLE)


@app.get("/register")
def register_page():
    if authm.current_user():
        return redirect(url_for("home"))
    return render_template("register.html", title=APP_TITLE)


@app.post("/register")
def register_submit():
    form = request.form
    if authm.current_user():
        return redirect(url_for("home"))
    try:
        if form.get("password") != form.get("confirm_password"):
            raise ValueError("Passwords do not match.")
        user = authm.create_user(
            name=form.get("name", ""),
            email=form.get("email", ""),
            password=form.get("password", ""),
            age=form.get("age"),
        )
        authm.login_user(user)
        return redirect(url_for("home"))
    except ValueError as e:
        return render_template("register.html", title=APP_TITLE, error=str(e), form=form), 400


@app.get("/login")
def login_page():
    if authm.current_user():
        return redirect(url_for("home"))
    return render_template("login.html", title=APP_TITLE, next_url=request.args.get("next", ""))


@app.post("/login")
def login_submit():
    form = request.form
    if authm.current_user():
        return redirect(url_for("home"))
    try:
        user = authm.verify_user(form.get("email", ""), form.get("password", ""))
        authm.login_user(user)
        next_url = form.get("next") or url_for("home")
        return redirect(next_url)
    except ValueError as e:
        return render_template("login.html", title=APP_TITLE, error=str(e), form=form), 400


@app.get("/logout")
def logout():
    authm.logout_user()
    return redirect(url_for("landing"))


@app.get("/home")
@authm.login_required
def home():
    return render_template(
        "home.html",
        title=APP_TITLE,
        status=artifacts_status(),
    )


@app.get("/about")
@authm.login_required
def about():
    return render_template(
        "about.html",
        title=APP_TITLE,
        status=artifacts_status(),
    )


@app.get("/predict")
@authm.login_required
def predict_page():
    art = get_artifacts()
    columns = art.feature_columns if art else []
    return render_template(
        "predict.html",
        title=APP_TITLE,
        status=artifacts_status(),
        feature_columns=columns,
    )


@app.get("/api/status")
@authm.api_login_required
def api_status():
    return jsonify(artifacts_status())


@app.get("/api/random")
@authm.api_login_required
def api_random():
    try:
        return jsonify({"ok": True, "values": random_values_dict()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.post("/api/predict")
@authm.api_login_required
def api_predict():
    try:
        payload = request.get_json(force=True, silent=False)
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")

        values = payload.get("values")
        if not isinstance(values, dict):
            raise ValueError('Expected {"values": {...}}.')

        art = get_artifacts()
        if art is None:
            raise RuntimeError(_artifacts_error or "Artifacts not loaded.")

        cleaned: Dict[str, float] = {}
        missing = []
        for c in art.feature_columns:
            if c not in values:
                missing.append(c)
                continue
            try:
                cleaned[c] = float(values[c])
            except Exception:
                raise ValueError(f"Invalid number for '{c}'.")

        if missing:
            raise ValueError(f"Missing {len(missing)} feature(s).")

        pred_label, stress_level, suggestions = predict_from_values(cleaned)

        # Extension: Stress History — save every "Predict Stress" click.
        # Never lets a history/DB issue break the prediction response.
        try:
            level_to_class = {"medium": 0, "low": 1, "high": 2}
            ext.record_prediction(
                values=cleaned,
                stress_level=stress_level,
                prediction_class=level_to_class.get(stress_level),
                prediction_label=pred_label,
            )
        except Exception:
            pass

        return jsonify(
            {
                "ok": True,
                "prediction": pred_label,
                "stress_level": stress_level,
                "suggestions": suggestions,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ---------------------------------------------------------------------------
# Extension pages — Stress History, Dashboard, Calendar, Profile, Report
# These are purely additive and do not modify any existing route above.
# ---------------------------------------------------------------------------

@app.get("/history")
@authm.login_required
def history_page():
    return render_template("history.html", title=APP_TITLE, status=artifacts_status())


@app.get("/dashboard")
@authm.login_required
def dashboard_page():
    return render_template("dashboard.html", title=APP_TITLE, status=artifacts_status())


@app.get("/calendar")
@authm.login_required
def calendar_page():
    return render_template("calendar.html", title=APP_TITLE, status=artifacts_status())


@app.get("/profile")
@authm.login_required
def profile_page():
    return render_template("profile.html", title=APP_TITLE, status=artifacts_status())


@app.get("/report")
@authm.login_required
def report_page():
    return render_template("report.html", title=APP_TITLE, status=artifacts_status())


# ---------------------------------------------------------------------------
# Extension APIs
# ---------------------------------------------------------------------------

@app.get("/api/history")
@authm.api_login_required
def api_history():
    try:
        limit = request.args.get("limit", default=200, type=int)
        level = request.args.get("level")
        date_str = request.args.get("date")
        records = ext.fetch_history(limit=limit, level=level, date_str=date_str)
        return jsonify({"ok": True, "records": records})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/dashboard-summary")
@authm.api_login_required
def api_dashboard_summary():
    try:
        return jsonify({"ok": True, **ext.dashboard_summary()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/trend")
@authm.api_login_required
def api_trend():
    try:
        date_str = request.args.get("date")
        return jsonify({"ok": True, "points": ext.trend_series(date_str)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/daily-summary")
@authm.api_login_required
def api_daily_summary():
    try:
        date_str = request.args.get("date")
        return jsonify({"ok": True, **ext.daily_summary(date_str)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/calendar")
@authm.api_login_required
def api_calendar():
    try:
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        data = ext.calendar_month(year, month)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/profile")
@authm.api_login_required
def api_profile():
    try:
        return jsonify({"ok": True, **ext.profile_stats()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/report.pdf")
@authm.api_login_required
def api_report_pdf():
    try:
        date_str = request.args.get("date")
        pdf_bytes = ext.build_report_pdf(date_str)
        filename = f"hrv_stress_report_{date_str or ext.date.today().isoformat()}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

