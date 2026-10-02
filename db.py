"""Eventora – MySQL access layer (PyMySQL).

Every query in the project lives here so that app.py stays about HTTP and the
templates stay about markup. All MySQL errors are re-raised as
``DatabaseUnavailable`` so the website can show a friendly message instead of a
stack trace when the database is not running yet.

When nothing is listening on the MySQL port, the first connection starts the
server itself (see ``_start_mysql`` and ``MYSQL_AUTOSTART`` in config.py) and
tries again, so the admin panel works even when MySQL was not started by hand.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

from config import Config


class DatabaseUnavailable(RuntimeError):
    """MySQL could not be reached, or rejected the query."""


# --------------------------------------------------------------------------- #
#  Starting MySQL when it is not running
# --------------------------------------------------------------------------- #
# This machine has no registered MySQL Windows *service*, so the server used to
# be started by hand (see start.ps1): forget that once and the admin panel
# answered "The database is not reachable" instead of the sign-in form.
#
# When - and only when - the port refuses the connection, the first query of the
# process starts MySQL the same way start.ps1 does, waits for the port and tries
# again. One attempt per process, never on a remote host, and never for a wrong
# password or a missing database.
_LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
_UNREACHABLE_CODES = (2002, 2003)         # CR_CONNECTION_ERROR / CR_CONN_HOST_ERROR

_SERVER_LOCK = threading.Lock()
_server_start_tried = False


def _is_server_down(exc: BaseException) -> bool:
    """True for 'nothing is listening on the MySQL port' (2002 / 2003)."""
    args = getattr(exc, 'args', ()) or ()
    return bool(args) and args[0] in _UNREACHABLE_CODES


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """True when something already accepts TCP connections on host:port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(timeout)
            return probe.connect_ex((host, port)) == 0
    except OSError:
        return False


def _find_mysqld() -> str | None:
    """The mysqld binary: MYSQLD_PATH, PATH, the MySQL 8.4 install, any install."""
    candidates = []
    if Config.MYSQLD_PATH:
        candidates.append(Path(Config.MYSQLD_PATH))
    from_path = shutil.which('mysqld.exe') or shutil.which('mysqld')
    if from_path:
        candidates.append(Path(from_path))
    if os.name == 'nt':
        candidates.append(Path(r'C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe'))
    else:
        candidates += [Path('/usr/sbin/mysqld'), Path('/usr/bin/mysqld'),
                       Path('/usr/local/mysql/bin/mysqld')]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    # Any other MySQL version installed under "Program Files\MySQL".
    for folder in sorted(Path(r'C:\Program Files\MySQL').glob('*/bin/mysqld.exe')):
        if folder.is_file():
            return str(folder)
    return None


def _ensure_managed_datadir(mysqld: str) -> tuple[Path, bool] | tuple[None, bool]:
    """Initializes (once) and returns (data_dir, just_initialized).

    Used only when MYSQL_DEFAULTS_FILE does not point at a real install, so
    the auto-started server always comes back to the *same* data on every
    run instead of silently falling back to mysqld's own compiled-in
    default folder (which is how admin logins and uploads used to appear to
    vanish between restarts).
    """
    data_dir = Config.MYSQL_MANAGED_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    if (data_dir / 'mysql').is_dir():
        return data_dir, False   # already initialized on a previous run

    print(f'[i] First run: initializing a local MySQL data directory at {data_dir}')
    init_attempts = [
        [mysqld, '--initialize-insecure', f'--datadir={data_dir}'],
    ]
    installer = shutil.which('mariadb-install-db') or shutil.which('mysql_install_db')
    if installer:
        init_attempts.append([installer, f'--datadir={data_dir}', '--auth-root-authentication-method=normal'])

    for attempt in init_attempts:
        try:
            result = subprocess.run(attempt, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f'[!] Could not run {attempt[0]}: {exc}')
            continue
        if result.returncode == 0 and (data_dir / 'mysql').is_dir():
            print(f'[ok] Local MySQL data directory ready at {data_dir}')
            return data_dir, True
        print(f'[!] {attempt[0]} exited {result.returncode}: {result.stderr.strip()[:400]}')

    print('[!] Could not initialize a local MySQL data directory. Install MySQL '
          'properly and set MYSQL_DEFAULTS_FILE / MYSQLD_PATH in .env instead.')
    return None, False


def _apply_configured_root_password(host: str, port: int) -> None:
    """After a fresh --initialize-insecure, root has no password yet, but
    .env may specify MYSQL_PASSWORD. Set it once so the app's own configured
    credentials work immediately, instead of failing auth against a DB it
    just created itself."""
    password = Config.MYSQL_PASSWORD
    if not password or Config.MYSQL_USER != 'root':
        return   # nothing to reconcile, or a non-root user we can't safely create here
    try:
        conn = pymysql.connect(host=host, port=port, user='root', password='',
                                connect_timeout=5, charset=Config.MYSQL_CHARSET)
        try:
            with conn.cursor() as cur:
                cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (password,))
            conn.commit()
        finally:
            conn.close()
        print("[ok] Set the local MySQL root password to match MYSQL_PASSWORD in .env.")
    except pymysql.MySQLError as exc:
        print(f'[!] Could not set the initial root password automatically: {exc}. '
              f'If login fails, either clear MYSQL_PASSWORD in .env or delete '
              f'"{Config.MYSQL_MANAGED_DATA_DIR}" and let it reinitialize.')


def _start_mysql() -> bool:
    """Starts MySQL if it is down. True once the port answers.

    Runs at most once per process: a second request must not spawn a second
    server just because the first attempt failed.
    """
    global _server_start_tried

    if not Config.MYSQL_AUTOSTART:
        return False
    if (Config.MYSQL_HOST or '').strip().lower() not in _LOCAL_HOSTS:
        return False                              # a hosted database is not ours to start
    if _port_open(Config.MYSQL_HOST, Config.MYSQL_PORT):
        return False                              # something is listening already

    with _SERVER_LOCK:
        if _server_start_tried:
            return False
        _server_start_tried = True

        mysqld = _find_mysqld()
        if mysqld is None:
            print('[!] MySQL is not running and mysqld could not be found. Start it with '
                  '".\\start.ps1 db", or set MYSQLD_PATH in .env.')
            return False

        command = [mysqld]
        just_initialized = False
        defaults = Path(Config.MYSQL_DEFAULTS_FILE) if Config.MYSQL_DEFAULTS_FILE else None
        if defaults and defaults.is_file():
            command.append(f'--defaults-file={defaults}')   # must be the first option
        else:
            if defaults:
                print(f'[i] No MySQL defaults file at {defaults} - '
                      'using a managed local data directory instead.')
            data_dir, just_initialized = _ensure_managed_datadir(mysqld)
            if data_dir is None:
                return False
            socket_path = data_dir.parent / 'mysqld.sock'
            pid_path = data_dir.parent / 'mysqld.pid'
            command += [f'--datadir={data_dir}', f'--port={Config.MYSQL_PORT}',
                        f'--pid-file={pid_path}']
            if os.name != 'nt':
                command.append(f'--socket={socket_path}')

        # mysqld's own stdout/stderr used to go to DEVNULL, so when startup
        # failed the advice to "check the error log" pointed at a file that
        # was never written - there was nothing to actually diagnose with.
        # Capture it for real so a failed start is debuggable.
        startup_log = Config.MYSQL_MANAGED_DATA_DIR.parent / 'mysqld-startup.log'
        startup_log.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(startup_log, 'ab')

        options = {'stdin': subprocess.DEVNULL, 'stdout': log_handle,
                   'stderr': log_handle, 'close_fds': True}
        if os.name == 'nt':
            # Detached, so MySQL keeps running when the web server is stopped -
            # exactly what "start.ps1 db" does with Start-Process.
            options['creationflags'] = (subprocess.DETACHED_PROCESS |
                                        subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            options['start_new_session'] = True

        print(f'[i] MySQL is not running - starting it ({mysqld}).')
        try:
            subprocess.Popen(command, **options)
        except OSError as exc:
            print(f'[!] MySQL could not be started ({exc}).')
            return False
        finally:
            log_handle.close()

        deadline = time.monotonic() + max(Config.MYSQL_START_TIMEOUT, 1)
        while time.monotonic() < deadline:
            if _port_open(Config.MYSQL_HOST, Config.MYSQL_PORT):
                print(f'[ok] MySQL is up on {Config.MYSQL_HOST}:{Config.MYSQL_PORT}.')
                if just_initialized:
                    _apply_configured_root_password(Config.MYSQL_HOST, Config.MYSQL_PORT)
                return True
            time.sleep(0.5)

        print(f'[!] MySQL did not answer on {Config.MYSQL_HOST}:{Config.MYSQL_PORT} within '
              f'{Config.MYSQL_START_TIMEOUT} s. Last lines of {startup_log}:')
        try:
            tail = startup_log.read_text(errors='replace').splitlines()[-15:]
            for line in tail:
                print(f'    {line}')
        except OSError:
            pass
        return False


# --------------------------------------------------------------------------- #
#  Connection handling
# --------------------------------------------------------------------------- #
def server_reachable(timeout: float = 0.5) -> bool:
    """True when something accepts connections on the MySQL port.

    A fast TCP probe (no query, no password): used by the admin sign-in page to
    say "MySQL is not running" before anybody types a password.
    """
    return _port_open(Config.MYSQL_HOST, Config.MYSQL_PORT, timeout)


def _connect(with_database: bool = True):
    """Opens one connection. `with_database=False` is used to CREATE DATABASE."""
    kwargs = {
        'host': Config.MYSQL_HOST,
        'port': Config.MYSQL_PORT,
        'user': Config.MYSQL_USER,
        'password': Config.MYSQL_PASSWORD,
        'charset': Config.MYSQL_CHARSET,
        'cursorclass': DictCursor,
        'autocommit': False,
        'connect_timeout': Config.MYSQL_CONNECT_TIMEOUT,
    }
    if with_database:
        kwargs['database'] = Config.MYSQL_DATABASE
    try:
        return pymysql.connect(**kwargs)
    except pymysql.MySQLError as exc:
        failure = exc
        if _is_server_down(exc) and _start_mysql():
            # A fresh server may refuse queries for a moment while InnoDB
            # finishes its start-up, so the connection is retried a few times.
            for attempt in range(5):
                if attempt:
                    time.sleep(0.5)
                try:
                    return pymysql.connect(**kwargs)
                except pymysql.MySQLError as retry_exc:
                    failure = retry_exc
                    if not _is_server_down(retry_exc):
                        break                    # a different problem - stop retrying
        raise DatabaseUnavailable(
            f'Cannot connect to MySQL at {Config.MYSQL_HOST}:{Config.MYSQL_PORT} '
            f'as "{Config.MYSQL_USER}" ({failure}).'
        ) from failure


@contextmanager
def connection(with_database: bool = True):
    """Yields a connection and commits (or rolls back) automatically."""
    conn = _connect(with_database)
    try:
        yield conn
        conn.commit()
    except pymysql.MySQLError as exc:
        conn.rollback()
        raise DatabaseUnavailable(str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run(sql: str, params=None, fetch: str | None = None):
    """Runs a single statement.

    fetch='all'  -> list of rows       fetch='one' -> one row or None
    fetch=None   -> last insert id for an INSERT, otherwise the affected rows
    """
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch == 'all':
                    return cur.fetchall()
                if fetch == 'one':
                    return cur.fetchone()
                return cur.lastrowid or cur.rowcount
    except DatabaseUnavailable:
        raise
    except pymysql.MySQLError as exc:
        raise DatabaseUnavailable(str(exc)) from exc


def fetch_all(sql: str, params=None) -> list[dict]:
    return _run(sql, params, fetch='all') or []


def fetch_one(sql: str, params=None) -> dict | None:
    return _run(sql, params, fetch='one')


def execute(sql: str, params=None) -> int:
    return int(_run(sql, params) or 0)


# --------------------------------------------------------------------------- #
#  Schema
# --------------------------------------------------------------------------- #
_COMMENT_RE = re.compile(r'^\s*--.*$', re.MULTILINE)


def split_statements(script: str) -> list[str]:
    """Splits a .sql file into single statements (comments removed)."""
    cleaned = _COMMENT_RE.sub('', script)
    return [s.strip() for s in cleaned.split(';') if s.strip()]


def ensure_schema() -> dict:
    """Creates the database, the tables and the indexes. Safe to run again."""
    if not Config.SCHEMA_FILE.is_file():
        raise DatabaseUnavailable(f'Schema file not found: {Config.SCHEMA_FILE}')

    statements = split_statements(Config.SCHEMA_FILE.read_text(encoding='utf-8'))
    applied, skipped = 0, 0

    # NOTE: the old code skipped CREATE DATABASE / USE while connected with
    # with_database=False, so CREATE TABLE ran with "no database selected"
    # and init-db always failed. Fixed: create the DB explicitly, select it,
    # then apply every other statement.
    db_name = Config.MYSQL_DATABASE
    # Very small identifier guard – database name comes from .env.
    if not re.fullmatch(r'[A-Za-z0-9_]+', db_name or ''):
        raise DatabaseUnavailable(f'Invalid MYSQL_DATABASE name: {db_name!r}')

    try:
        with connection(with_database=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'CREATE DATABASE IF NOT EXISTS `{db_name}` '
                    'CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
                )
                conn.select_db(db_name)
                for statement in statements:
                    upper = statement.upper().lstrip()
                    if upper.startswith('CREATE DATAB') or upper.startswith('USE '):
                        skipped += 1
                        continue
                    cur.execute(statement)
                    applied += 1
    except pymysql.MySQLError as exc:
        raise DatabaseUnavailable(str(exc)) from exc
    return {'statements': applied, 'skipped': skipped,
            'database': Config.MYSQL_DATABASE}


def server_version() -> str:
    row = fetch_one('SELECT VERSION() AS version')
    return (row or {}).get('version', 'unknown')


# --------------------------------------------------------------------------- #
#  Administrators
# --------------------------------------------------------------------------- #
def get_admin_by_id(admin_id: int) -> dict | None:
    return fetch_one(
        'SELECT id, username, display_name, password_hash, created_at, last_login_at '
        'FROM admins WHERE id = %s',
        (admin_id,),
    )


def get_admin_by_username(username: str) -> dict | None:
    return fetch_one(
        'SELECT id, username, display_name, password_hash, created_at, last_login_at '
        'FROM admins WHERE username = %s',
        (username,),
    )


def count_admins() -> int:
    row = fetch_one('SELECT COUNT(*) AS total FROM admins')
    return int((row or {}).get('total') or 0)


def upsert_admin(username: str, password_hash: str, display_name: str | None = None) -> int:
    """Creates the account, or resets the password of an existing one."""
    return execute(
        'INSERT INTO admins (username, password_hash, display_name) '
        'VALUES (%s, %s, %s) '
        'ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), '
        '                        display_name = VALUES(display_name)',
        (username, password_hash, display_name),
    )


def touch_admin_login(admin_id: int) -> None:
    execute('UPDATE admins SET last_login_at = NOW() WHERE id = %s', (admin_id,))


# --------------------------------------------------------------------------- #
#  Media library
# --------------------------------------------------------------------------- #
# Only these keys can ever be written from a form or a JSON body.
MUTABLE_FIELDS = ('title', 'category', 'kind', 'file_name', 'poster_name',
                  'mime_type', 'file_size', 'is_private', 'admin_id')


def list_media(visibility: str = 'all', category: str | None = None,
               kind: str | None = None, limit: int = 200) -> list[dict]:
    """Media rows, newest first.

    visibility: 'all'
                'published'  -> is_private = 0, the only rows viewers may see
                'private'    -> is_private = 1, admin-only material
    """
    sql = [
        'SELECT m.id, m.title, m.category, m.kind, m.file_name, m.poster_name,',
        '       m.mime_type, m.file_size, m.is_private, m.admin_id,',
        '       m.created_at, m.updated_at, a.username AS uploaded_by',
        'FROM media m LEFT JOIN admins a ON a.id = m.admin_id',
        'WHERE 1 = 1',
    ]
    params: list = []

    if visibility == 'published':
        sql.append('AND m.is_private = 0')
    elif visibility == 'private':
        sql.append('AND m.is_private = 1')
    if category:
        sql.append('AND m.category = %s')
        params.append(category)
    if kind:
        sql.append('AND m.kind = %s')
        params.append(kind)

    sql.append('ORDER BY m.created_at DESC, m.id DESC LIMIT %s')
    params.append(int(limit))
    return fetch_all(' '.join(sql), params)


def get_media(media_id: int) -> dict | None:
    return fetch_one(
        'SELECT m.*, a.username AS uploaded_by FROM media m '
        'LEFT JOIN admins a ON a.id = m.admin_id WHERE m.id = %s',
        (media_id,),
    )


def find_media_by_file(file_name: str) -> dict | None:
    """Used by /media/<file> to decide whether a file may leave the server.

    Matches the file itself or the poster of a film. A published row wins over a
    private one, so a public file can never be hidden by a private duplicate.
    """
    return fetch_one(
        'SELECT id, kind, file_name, poster_name, is_private, title, category '
        'FROM media WHERE file_name = %s OR poster_name = %s '
        'ORDER BY is_private ASC, id ASC LIMIT 1',
        (file_name, file_name),
    )


def create_media(fields: dict) -> int:
    columns = [c for c in MUTABLE_FIELDS if c in fields]
    if not columns:
        raise ValueError('create_media() needs at least one field')
    placeholders = ', '.join(['%s'] * len(columns))
    return execute(
        f"INSERT INTO media ({', '.join(columns)}) VALUES ({placeholders})",
        [fields[c] for c in columns],
    )


def update_media(media_id: int, fields: dict) -> int:
    columns = [c for c in MUTABLE_FIELDS if c in fields]
    if not columns:
        return 0
    assignments = ', '.join(f'{c} = %s' for c in columns)
    return execute(
        f'UPDATE media SET {assignments} WHERE id = %s',
        [fields[c] for c in columns] + [media_id],
    )


def delete_media(media_id: int) -> dict | None:
    """Removes the row and returns it, so the files can be deleted from disk."""
    row = get_media(media_id)
    if row is None:
        return None
    execute('DELETE FROM media WHERE id = %s', (media_id,))
    return row


def media_stats() -> dict:
    """Dashboard counters: total / published / admin-only / images / films."""
    row = fetch_one(
        'SELECT COUNT(*) AS total, '
        '       COALESCE(SUM(is_private = 0), 0) AS published, '
        '       COALESCE(SUM(is_private = 1), 0) AS private_items, '
        "       COALESCE(SUM(kind = 'image'), 0) AS images, "
        "       COALESCE(SUM(kind = 'video'), 0) AS videos "
        'FROM media'
    ) or {}
    return {
        'total': int(row.get('total') or 0),
        'published': int(row.get('published') or 0),
        'private_items': int(row.get('private_items') or 0),
        'images': int(row.get('images') or 0),
        'videos': int(row.get('videos') or 0),
    }
