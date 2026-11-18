"""
Authentication extension for the HRV Stress Detection app.

Kept in its own module, exactly like extensions.py, so the original
prediction pipeline (model / scaler / feature columns / /api/predict)
in app.py is never touched. This file only adds:

  1. users.db (SQLite)        -> separate DB file, does not touch
                                  stress_history.db used by extensions.py
  2. Registration / Login      -> name, email, password, confirm password, age
  3. Session handling          -> Flask session cookie (user_id, name, email)
  4. login_required            -> guard for normal HTML pages (redirects to /login)
  5. api_login_required        -> guard for JSON /api/* endpoints (401 JSON)

Nothing here modifies app.py's model-loading or prediction functions.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the users table if it doesn't exist yet. Safe to call many times."""
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                age INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


def create_user(name: str, email: str, password: str, age: Optional[int]) -> Dict[str, Any]:
    """Validates input and inserts a new user. Raises ValueError on bad input."""
    name = (name or "").strip()
    email = (email or "").strip().lower()

    if not name:
        raise ValueError("Full name is required.")
    if not email or not EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address.")
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    if age is not None:
        try:
            age = int(age)
            if age < 1 or age > 120:
                raise ValueError
        except ValueError:
            raise ValueError("Enter a valid age.")

    if get_user_by_email(email) is not None:
        raise ValueError("An account with this email already exists.")

    password_hash = generate_password_hash(password)

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, age, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, email, password_hash, age, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": name, "email": email, "age": age}
    finally:
        conn.close()


def verify_user(email: str, password: str) -> Dict[str, Any]:
    """Checks credentials. Raises ValueError with a user-facing message on failure."""
    user = get_user_by_email(email or "")
    if user is None or not check_password_hash(user["password_hash"], password or ""):
        raise ValueError("Incorrect email or password.")
    return {"id": user["id"], "name": user["name"], "email": user["email"], "age": user["age"]}


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def login_user(user: Dict[str, Any]) -> None:
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]


def logout_user() -> None:
    session.clear()


def current_user() -> Optional[Dict[str, Any]]:
    if "user_id" not in session:
        return None
    return {
        "id": session.get("user_id"),
        "name": session.get("user_name"),
        "email": session.get("user_email"),
    }


def login_required(view_func):
    """Guard for normal HTML page routes. Redirects to /login if not signed in."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login_page", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped


def api_login_required(view_func):
    """Guard for JSON /api/* routes. Returns a 401 JSON error if not signed in."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return jsonify({"ok": False, "error": "Authentication required."}), 401
        return view_func(*args, **kwargs)

    return wrapped
