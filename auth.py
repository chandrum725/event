"""Eventora – admin authentication.

One small module for everything about proving who the admin is:

  * PBKDF2-SHA256 password hashing (Werkzeug) – passwords are never stored,
  * signed-cookie sessions (Flask) created fresh on every sign-in,
  * CSRF tokens for every POST (forms and the JSON API),
  * a simple in-memory throttle so online password guessing stops after
    ``LOGIN_MAX_ATTEMPTS`` failures,
  * the decorators the routes use: ``login_required`` (HTML) and
    ``api_login_required`` (JSON).
"""
from __future__ import annotations

import hmac
import secrets
import time
from functools import wraps

from flask import flash, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db

PASSWORD_METHOD = 'pbkdf2:sha256:600000'

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 10 * 60
_ATTEMPTS: dict[str, list] = {}          # key -> [failures, first_failure_ts]

# The admin panel is not part of the public site: the templates are marked
# noindex and the session cookie is SameSite=Lax, so it is never sent cross-site.


# --------------------------------------------------------------------------- #
#  Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return generate_password_hash(password, method=PASSWORD_METHOD)


def verify_password(admin_row: dict, password: str) -> bool:
    stored = (admin_row or {}).get('password_hash') or ''
    if not stored:
        return False
    try:
        return check_password_hash(stored, password)
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
#  CSRF
# --------------------------------------------------------------------------- #
def csrf_token() -> str:
    """The token for the current session, created on first use."""
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


def supplied_csrf_token() -> str:
    token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token') or ''
    if not token:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            token = str(payload.get('csrf_token') or '')
    return token


def csrf_ok() -> bool:
    expected = session.get('csrf_token')
    supplied = supplied_csrf_token()
    if not expected or not supplied:
        return False
    return hmac.compare_digest(str(expected), str(supplied))


# --------------------------------------------------------------------------- #
#  Login throttling (per address + username, kept in memory)
# --------------------------------------------------------------------------- #
def _attempt_key(username: str) -> str:
    return f'{(request.remote_addr or "?")}|{(username or "").lower()}'


def lock_seconds_left(username: str) -> int:
    key = _attempt_key(username)
    entry = _ATTEMPTS.get(key)
    if not entry:
        return 0
    failures, first_seen = entry
    if failures < LOGIN_MAX_ATTEMPTS:
        return 0
    remaining = LOGIN_LOCK_SECONDS - (time.time() - first_seen)
    if remaining <= 0:
        _ATTEMPTS.pop(key, None)
        return 0
    return int(remaining)


def _record_failure(username: str) -> None:
    key = _attempt_key(username)
    failures, first_seen = _ATTEMPTS.get(key, [0, time.time()])
    _ATTEMPTS[key] = [failures + 1, first_seen if failures else time.time()]


def clear_failures(username: str) -> None:
    _ATTEMPTS.pop(_attempt_key(username), None)


def authenticate(username: str, password: str) -> tuple[dict | None, str | None, int]:
    """Checks credentials.

    Returns (admin, error_message, http_status) – exactly one of admin/error is
    set. The message never says which half of the pair was wrong.
    """
    if not username or not password:
        return None, 'Username and password are both required.', 400

    left = lock_seconds_left(username)
    if left:
        return None, f'Too many failed attempts. Try again in {left // 60 + 1} minute(s).', 429

    try:
        admin = db.get_admin_by_username(username)
    except db.DatabaseUnavailable as exc:
        return None, f'The database is not reachable, so sign-in is unavailable. {exc}', 503

    if admin is None or not verify_password(admin, password):
        _record_failure(username)
        return None, 'Invalid username or password.', 401

    clear_failures(username)
    try:
        db.touch_admin_login(admin['id'])
    except db.DatabaseUnavailable:
        pass                                 # signing in still works without the timestamp
    return admin, None, 200


# --------------------------------------------------------------------------- #
#  Sessions
# --------------------------------------------------------------------------- #
def start_session(admin_row: dict) -> None:
    """Starts a clean session (a new session id and CSRF token on every sign-in)."""
    session.clear()
    session['admin_id'] = int(admin_row['id'])
    session['admin_username'] = admin_row.get('username') or ''
    session['csrf_token'] = secrets.token_urlsafe(32)
    session.permanent = True


def end_session() -> None:
    session.clear()


def current_admin() -> dict | None:
    """The signed-in admin as a plain dict, or None. Cached for the request."""
    if 'admin' in g:
        return g.admin

    g.admin = None
    admin_id = session.get('admin_id')
    if admin_id:
        try:
            row = db.get_admin_by_id(int(admin_id))
        except (db.DatabaseUnavailable, TypeError, ValueError):
            row = None
        if row is None:
            session.clear()                      # the account was deleted – sign out
        else:
            g.admin = {'id': int(row['id']),
                       'username': row['username'],
                       'display_name': row.get('display_name')}
    return g.admin


def is_authenticated() -> bool:
    return current_admin() is not None


# --------------------------------------------------------------------------- #
#  Decorators
# --------------------------------------------------------------------------- #
def login_required(view):
    """Admin pages: send visitors to the sign-in form, remembering where they were."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            flash('Please sign in to open the admin area.', 'info')
            # request.full_path is "/admin?" when there is no query string –
            # strip the dangling "?" so ?next= stays clean.
            here = request.path
            if request.query_string:
                here += '?' + request.query_string.decode(errors='replace')
            return redirect(url_for('admin_login', next=safe_next_path(here)))
        return view(*args, **kwargs)
    return wrapper


def api_login_required(view):
    """JSON endpoints: 401 instead of a redirect."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            return jsonify(error='authentication_required',
                           message='Sign in to the admin area first.'), 401
        return view(*args, **kwargs)
    return wrapper


def safe_next_path(candidate: str | None) -> str:
    """Only relative, single-slash paths are accepted (no open redirects)."""
    path = (candidate or '').strip()
    # Drop a dangling "?" (Flask's request.full_path appends one with no query).
    if path.endswith('?') and '?' not in path[:-1]:
        path = path[:-1]
    if path == '/admin/login':
        # After signing in there is nothing to go "back" to.
        return url_for('admin_dashboard')
    if (
        path.startswith('/')
        and not path.startswith('//')
        and not path.startswith('/\\')
        and '\\' not in path
        and not any(ord(ch) < 32 for ch in path)
        and '://' not in path
    ):
        return path
    return url_for('admin_dashboard')
