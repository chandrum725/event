"""Eventora – configuration.

Every value can be overridden with an environment variable (see .env.example),
so the same code runs on a laptop, a shared host or a service such as
PythonAnywhere without a single edit.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

try:                                      # python-dotenv is a convenience, not a hard requirement
    from dotenv import load_dotenv
except ImportError:                       # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / '.env')


def _int(name: str, default: int) -> int:
    """Reads an integer environment variable, falling back to `default`."""
    raw = (os.getenv(name) or '').strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _flag(name: str, default: bool = False) -> bool:
    """Reads a yes/no environment variable (1/true/yes/on)."""
    raw = (os.getenv(name) or '').strip().lower()
    if not raw:
        return default
    return raw in ('1', 'true', 'yes', 'on')


# --------------------------------------------------------------------------- #
#  Media categories – the `value` matches data-category in the gallery markup
#  (events.html) and the lightbox filter, `label` is what visitors read.
# --------------------------------------------------------------------------- #
MEDIA_CATEGORIES = (
    {'value': 'weddings', 'label': 'Weddings'},
    {'value': 'corporate', 'label': 'Corporate'},
    {'value': 'birthday', 'label': 'Birthday'},
    {'value': 'concert', 'label': 'Concert'},
    {'value': 'engagement', 'label': 'Engagement'},
)
CATEGORY_VALUES = tuple(c['value'] for c in MEDIA_CATEGORIES)
CATEGORY_LABELS = {c['value']: c['label'] for c in MEDIA_CATEGORIES}

# Mapping used for the JSON API and the <video>/<img> mime types.
MIME_TYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.webp': 'image/webp', '.avif': 'image/avif',
    '.svg': 'image/svg+xml',
    '.mp4': 'video/mp4', '.m4v': 'video/x-m4v', '.webm': 'video/webm',
    '.ogv': 'video/ogg', '.mov': 'video/quicktime',
}


class Config:
    """Plain class – Flask reads it with ``app.config.from_object(Config)``."""

    # ----------------------------------------------------------------- Flask --
    SECRET_KEY = os.getenv('SECRET_KEY', 'eventora-dev-secret-key-change-me')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _flag('SESSION_COOKIE_SECURE', False)   # switch on behind HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int('SESSION_HOURS', 8))
    MAX_CONTENT_LENGTH = _int('MAX_UPLOAD_MB', 128) * 1024 * 1024
    TEMPLATES_AUTO_RELOAD = _flag('FLASK_DEBUG', False)
    JSON_SORT_KEYS = False

    # ----------------------------------------------------------------- MySQL --
    MYSQL_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
    MYSQL_PORT = _int('MYSQL_PORT', 3306)
    MYSQL_USER = os.getenv('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'eventora_db')
    MYSQL_CHARSET = 'utf8mb4'
    MYSQL_CONNECT_TIMEOUT = _int('MYSQL_CONNECT_TIMEOUT', 5)

    # ------------------------------------------------------ MySQL auto-start --
    # This machine has no registered MySQL Windows *service* (installing one
    # needs an elevated shell), so the server is started by start.ps1. Forget
    # that once and the admin panel answers "The database is not reachable"
    # instead of the sign-in form. With this switch on, db.py starts MySQL
    # itself the first time the port refuses a connection, so the admin area
    # works no matter how the app was launched.
    #
    # It is only ever tried on a local host and only when nothing listens on the
    # port - a wrong password or a missing database never starts a server.
    MYSQL_AUTOSTART = _flag('MYSQL_AUTOSTART', os.name == 'nt')
    MYSQLD_PATH = (os.getenv('MYSQLD_PATH') or '').strip()       # empty = search for it
    MYSQL_DEFAULTS_FILE = (os.getenv('MYSQL_DEFAULTS_FILE') or
                           r'C:\ProgramData\MySQL\MySQL Server 8.4\my.ini')
    MYSQL_START_TIMEOUT = _int('MYSQL_START_TIMEOUT', 60)        # seconds to wait for the port

    # When MYSQL_DEFAULTS_FILE above does not exist (no real MySQL install
    # registered on this machine), db.py used to start mysqld with neither
    # --defaults-file nor --datadir, so mysqld fell back to whatever data
    # folder it happens to be compiled with. That folder can silently differ
    # between runs (different working directory, a different mysqld picked
    # up from PATH, etc.) - which looks exactly like "login stops working"
    # or "my uploads disappeared": the server is quietly talking to a
    # different, empty database each time.
    #
    # MYSQL_MANAGED_DATA_DIR fixes that: a folder inside this project that
    # db.py initializes once and always reuses for the auto-started server,
    # so the same admins/media rows are there on every run.
    MYSQL_MANAGED_DATA_DIR = Path(os.getenv('MYSQL_MANAGED_DATA_DIR') or (BASE_DIR / '.mysql-data'))

    # ------------------------------------------------------- the static site --
    # SITE_ROOT is the folder holding index.html / events.html / css / js /
    # images / video. Uploaded media does NOT live here – it is served by the
    # /media/<file> route, which asks MySQL who is allowed to see the file.
    SITE_ROOT = BASE_DIR
    SCHEMA_FILE = BASE_DIR / 'schema.sql'

    # The only extensions the public site route will hand out.
    SITE_EXTENSIONS = (
        '.html', '.css', '.js', '.map', '.json', '.webmanifest', '.txt',
        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.svg', '.ico',
        '.mp4', '.webm', '.ogv', '.mov', '.m4v', '.mp3',
        '.woff', '.woff2', '.ttf',
    )

    # Folders that can never be reached through the public site route.
    SITE_BLOCKED_DIRS = (
        'uploads', 'templates', '__pycache__', '.venv', 'venv', '.git',
        'node_modules', '.idea', '.vscode',
    )

    # Source files that are edited while the site is running (the stylesheet, the
    # script, the pages). They are revalidated on every visit instead of being
    # cached for an hour, so a browser never shows a previous copy of a file that
    # was just changed. Images, fonts and films keep their one-hour cache: they do
    # not change under the same name.
    SITE_LIVE_EXTENSIONS = ('.html', '.css', '.js', '.map', '.json', '.webmanifest', '.txt')

    # Single files in the site root that must stay private even though their
    # extension is on the allow-list above. Add any new backend file here.
    SITE_BLOCKED_FILES = ('requirements.txt', 'schema.sql')

    # ---------------------------------------------------------------- upload --
    UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR') or (BASE_DIR / 'uploads')).resolve()
    UPLOAD_FOLDERS = ('images', 'videos', 'posters')
    IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif')
    VIDEO_EXTENSIONS = ('.mp4', '.webm', '.ogv', '.mov', '.m4v')
    MAX_IMAGE_MB = _int('MAX_IMAGE_MB', 12)
    MAX_VIDEO_MB = _int('MAX_VIDEO_MB', 128)
    UPLOAD_CHUNK = 1024 * 1024               # 1 MB streamed at a time

    # ------------------------------------------------------------- admin boot --
    # Only used by "init-db" / "create-admin" to create the first account.
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
    # Keep this high in production; a short password is only sensible on a
    # private, offline demo machine (set MIN_PASSWORD_LENGTH in .env).
    MIN_PASSWORD_LENGTH = _int('MIN_PASSWORD_LENGTH', 8)


def default_kind_for(name: str) -> str | None:
    """'image', 'video' or None – guessed from a file name's extension."""
    suffix = Path(name or '').suffix.lower()
    if suffix in Config.IMAGE_EXTENSIONS:
        return 'image'
    if suffix in Config.VIDEO_EXTENSIONS:
        return 'video'
    return None


def category_label(value: str) -> str:
    """Human label for a category value (falls back to the value itself)."""
    return CATEGORY_LABELS.get(value, (value or '').replace('-', ' ').title())


def mime_for(name: str) -> str:
    """Mime type for a stored file name."""
    return MIME_TYPES.get(Path(name or '').suffix.lower(), 'application/octet-stream')
