"""Eventora – Flask API + MySQL admin backend.

    python app.py init-db                     create the database and the tables
    python app.py create-admin                create/reset an administrator
    python app.py check-db                    test the MySQL connection
    python app.py                             start the server on http://127.0.0.1:5000

WHAT THIS FILE SERVES
  /                     the existing website (index.html, events.html, company.html …)
  /css /js /images /video           the site's own files
  /api/health           is Flask up, is MySQL reachable?
  /api/media            PUBLIC gallery feed – published items only
  /media/<file>         one uploaded file, released only to someone allowed to see it
  /admin, /admin/login  the admin area (not linked from the public site)
  /api/admin/…          JSON API for the same actions

THE RULE THAT MATTERS MOST
  A freshly uploaded photo or film is ADMIN ONLY (media.is_private = 1):
  it is filtered out in SQL by /api/media and /media/<file> answers 404 to
  anybody who is not signed in. The admin presses "Publish to viewers" to make
  an item public – only then does it appear in the gallery on events.html.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

import click
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from werkzeug.exceptions import HTTPException

import auth
import db
import storage
from config import (CATEGORY_VALUES, Config, MEDIA_CATEGORIES, category_label,
                    default_kind_for)

# --------------------------------------------------------------------------- #
#  App
# --------------------------------------------------------------------------- #
app = Flask(__name__, static_folder=None)     # the site's own files are served by site_file()
app.config.from_object(Config)
setattr(app.json, 'sort_keys', False)

storage.ensure_folders()


@app.context_processor
def inject_globals():
    """Values every template may use."""
    return {
        'current_admin': auth.current_admin(),
        'csrf_token': auth.csrf_token(),
        'category_label': category_label,
        'categories': MEDIA_CATEGORIES,
        'max_image_mb': Config.MAX_IMAGE_MB,
        'max_video_mb': Config.MAX_VIDEO_MB,
    }


@app.after_request
def add_security_headers(response):
    """Small, cheap headers that stop browsers doing dangerous things."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    if request.path.startswith('/admin') or request.path.startswith('/api/admin'):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'   # keep the admin area out of search
        response.headers['Cache-Control'] = 'no-store'
    return response


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
_EMPTY_STATS = {'total': 0, 'published': 0, 'private_items': 0, 'images': 0, 'videos': 0}


def _iso(value):
    return value.isoformat(sep=' ') if hasattr(value, 'isoformat') else (str(value) if value else None)


def _pretty(value) -> str:
    return value.strftime('%d %b %Y, %H:%M') if hasattr(value, 'strftime') else ''


def _media_url(file_name):
    return url_for('media_file', filename=file_name) if file_name else None


def _media_json(row: dict, for_admin: bool = False) -> dict:
    """The one place where a database row becomes a JSON object for the browser."""
    category = row.get('category') or CATEGORY_VALUES[0]
    data = {
        'id': int(row['id']),
        'title': row.get('title') or '',
        'category': category,
        'category_label': category_label(category),
        'kind': row.get('kind') or 'image',
        'mime_type': row.get('mime_type') or '',
        'size': int(row.get('file_size') or 0),
        'url': _media_url(row.get('file_name')),
        'poster_url': _media_url(row.get('poster_name')),
        'is_private': bool(row.get('is_private')),
        'visibility': 'private' if row.get('is_private') else 'published',
        'created_at': _iso(row.get('created_at')),
    }
    if for_admin:
        data['updated_at'] = _iso(row.get('updated_at'))
        data['uploaded_by'] = row.get('uploaded_by')
        data['size_label'] = storage.human_size(data['size'])
        data['created_at_label'] = _pretty(row.get('created_at'))
    return data


def _safe_site_parts(filename: str) -> list[str]:
    """Validates a path inside the website folder (used by site_file)."""
    parts = [p for p in str(filename or '').replace('\\', '/').split('/')
             if p not in ('', '.')]
    if not parts or '..' in parts:
        abort(404)
    if any(p.startswith('.') for p in parts):
        abort(404)
    if any(p.lower() in Config.SITE_BLOCKED_DIRS for p in parts):
        abort(404)
    if len(parts) == 1 and parts[0].lower() in Config.SITE_BLOCKED_FILES:
        abort(404)
    if Path(parts[-1]).suffix.lower() not in Config.SITE_EXTENSIONS:
        abort(404)
    if not (Config.SITE_ROOT / Path(*parts)).is_file():
        abort(404)
    return parts


def _admin_back_url() -> str:
    """Back to the dashboard, keeping the filters the admin was using."""
    query = request.query_string.decode()
    return url_for('admin_dashboard') + (f'?{query}' if query else '')


# --------------------------------------------------------------------------- #
#  The public website
# --------------------------------------------------------------------------- #
@app.get('/')
def site_index():
    """Home page of the public website."""
    return send_from_directory(Config.SITE_ROOT, 'index.html', max_age=0)


@app.get('/<path:filename>')
def site_file(filename):
    """Serves the website's own files, from an allow-list.

    Only known-safe extensions are handed out and the folders that hold private
    material (uploads/, templates/, …) are refused, so app.py, .env and every
    uploaded photo or film are unreachable through this route. Uploaded media is
    served by media_file(), which asks MySQL first.
    """
    parts = _safe_site_parts(filename)
    suffix = Path(parts[-1]).suffix.lower()
    # Pages, CSS and JS are revalidated on every visit (a 304 costs nothing), so an
    # edit is picked up straight away; images, fonts and films keep a one-hour cache.
    max_age = 0 if suffix in Config.SITE_LIVE_EXTENSIONS else 3600
    return send_from_directory(Config.SITE_ROOT, '/'.join(parts),
                               conditional=True, max_age=max_age)


# --------------------------------------------------------------------------- #
#  Public API  (what visitors are allowed to know)
# --------------------------------------------------------------------------- #
@app.get('/api/health')
def api_health():
    """Status endpoint: is Flask up, and is MySQL reachable?"""
    try:
        stats = db.media_stats()
        return jsonify(status='ok', database='connected',
                       mysql=db.server_version(), media=stats)
    except db.DatabaseUnavailable as exc:
        return jsonify(status='degraded', database='unavailable',
                       error=str(exc), media=_EMPTY_STATS), 503


@app.get('/api/media')
def api_media():
    """The gallery feed used by events.html.

    PUBLISHED ITEMS ONLY. Media the admin has kept to themselves
    (is_private = 1) is filtered out in SQL and never leaves the database, so a
    visitor cannot even learn that it exists.

    Optional filters: ?category=weddings  ?kind=image|video
    """
    category = (request.args.get('category') or '').strip().lower() or None
    kind = (request.args.get('kind') or '').strip().lower() or None
    if category not in CATEGORY_VALUES:
        category = None
    if kind not in ('image', 'video'):
        kind = None

    try:
        rows = db.list_media(visibility='published', category=category, kind=kind)
    except db.DatabaseUnavailable as exc:
        return jsonify(items=[], count=0, error='database_unavailable', message=str(exc)), 503

    items = [_media_json(row) for row in rows]
    return jsonify(items=items, count=len(items))


@app.get('/media/<path:filename>')
def media_file(filename):
    """Serves one uploaded file – but only to somebody allowed to see it.

      published item  -> served to everyone, so <img>/<video> work normally
      admin-only item -> served to a signed-in admin, 404 for everybody else
      unknown file    -> 404

    Stored names are random 32-character hex strings, so private material can be
    neither listed nor guessed.
    """
    try:
        relative = storage.safe_relative(filename)
    except storage.UploadError:
        abort(404)

    path = storage.resolve(relative)
    if path is None or not path.is_file():
        abort(404)

    try:
        row = db.find_media_by_file(relative)
    except db.DatabaseUnavailable:
        abort(503)

    if row is None:
        abort(404)
    if row.get('is_private') and not auth.is_authenticated():
        abort(404)     # 404, not 403: the existence of the file is not confirmed

    return send_from_directory(Config.UPLOAD_DIR, relative,
                               conditional=True, max_age=3600)


# --------------------------------------------------------------------------- #
#  Media actions – shared by the HTML dashboard and the JSON API
# --------------------------------------------------------------------------- #
def _requested_visibility() -> str:
    """'published' or 'private'. Anything unexpected means private (the safe default)."""
    raw = (request.form.get('visibility') or request.form.get('is_private') or '').strip().lower()
    if raw in ('published', 'public', 'viewers', '0', 'false', 'no'):
        return 'published'
    return 'private'


def _upload_from_request(admin_id: int) -> dict:
    """Validates the upload form, stores the file(s) and returns the DB row fields.

    NEW ITEMS ARE ADMIN ONLY unless the form explicitly asks for them to be
    published, so nothing can reach visitors by accident.
    """
    file_storage = request.files.get('file') or request.files.get('media')
    if file_storage is None:
        raise storage.UploadError('Choose an image or a video file to upload.')

    original_filename = (file_storage.filename or '').strip()
    if not original_filename:
        raise storage.UploadError('Choose an image or a video file to upload.')

    original_name = Path(original_filename).name
    guessed = default_kind_for(original_name)
    kind = (request.form.get('kind') or '').strip().lower()
    if kind not in ('image', 'video'):
        kind = guessed or 'image'
    if guessed and guessed != kind:
        raise storage.UploadError(
            f'"{original_name}" is a {guessed} file – set the media type to '
            f'{guessed} or choose another file.'
        )

    title = (request.form.get('title') or '').strip()
    if not title:
        title = Path(original_name).stem.replace('_', ' ').replace('-', ' ').strip().title()
    title = (title or 'Untitled media')[:160]

    category = (request.form.get('category') or '').strip().lower() or CATEGORY_VALUES[0]
    if category not in CATEGORY_VALUES:
        raise storage.UploadError('Please choose one of the listed categories.')

    saved = storage.save_media(file_storage, kind)
    poster_name = None
    try:
        if kind == 'video':
            poster_file = request.files.get('poster')
            if poster_file is not None and (poster_file.filename or '').strip():
                poster_name = storage.save_poster(poster_file)['file_name']
            else:                       # so a film always has a thumbnail in the gallery
                poster_name = storage.placeholder_poster(
                    title, f'{category_label(category)} · Event film')
    except storage.UploadError:
        storage.delete(saved['file_name'])
        raise

    return {
        'title': title,
        'category': category,
        'kind': kind,
        'file_name': saved['file_name'],
        'poster_name': poster_name,
        'mime_type': saved['mime_type'],
        'file_size': saved['file_size'],
        'is_private': 0 if _requested_visibility() == 'published' else 1,
        'admin_id': admin_id,
    }


def store_upload(admin_id: int) -> dict:
    """Saves the upload and inserts its row. Cleans the files up if MySQL fails."""
    fields = _upload_from_request(admin_id)
    try:
        media_id = db.create_media(fields)
    except Exception:
        storage.delete(fields.get('file_name'), fields.get('poster_name'))   # no orphan files
        raise
    return db.get_media(media_id) or dict(fields, id=media_id)


def set_visibility(media_id: int, is_private: bool) -> dict | None:
    """Publishes an item to viewers, or hides it again."""
    if db.get_media(media_id) is None:
        return None
    db.update_media(media_id, {'is_private': 1 if is_private else 0})
    return db.get_media(media_id)


def update_details(media_id: int, fields: dict) -> dict | None:
    """Changes the title / category / visibility of one item."""
    if db.get_media(media_id) is None:
        return None
    if fields:
        db.update_media(media_id, fields)
    return db.get_media(media_id)


def remove_media(media_id: int) -> dict | None:
    """Deletes the row and the file(s) it pointed at."""
    row = db.delete_media(media_id)
    if row is None:
        return None
    storage.delete(row.get('file_name'), row.get('poster_name'))
    return row


# --------------------------------------------------------------------------- #
#  Admin area (HTML) – deliberately not linked from the public website
# --------------------------------------------------------------------------- #
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Sign-in form. Nothing on the public pages points here."""
    next_url = auth.safe_next_path(request.args.get('next') or request.form.get('next'))

    if request.method == 'POST':
        if not auth.csrf_ok():
            flash('That form had expired. Please try again.', 'error')
            return redirect(url_for('admin_login', next=next_url))

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        admin, error, status = auth.authenticate(username, password)

        if error or admin is None:
            flash(error or 'Sign-in failed. Please try again.', 'error')
            return render_template('admin/login.html', next_url=next_url,
                                   username=username,
                                   database_down=status == 503), status

        auth.start_session(admin)
        flash(f'Welcome back, {admin.get("username")}.', 'success')
        return redirect(next_url)

    if auth.is_authenticated():
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/login.html', next_url=next_url, username='',
                           database_down=not db.server_reachable())


@app.post('/admin/logout')
@auth.login_required
def admin_logout():
    if not auth.csrf_ok():
        abort(400)
    auth.end_session()
    flash('You have been signed out.', 'info')
    return redirect(url_for('admin_login'))


@app.get('/admin')
@auth.login_required
def admin_dashboard():
    """Upload photos and films, and choose what viewers may see."""
    view = (request.args.get('view') or 'all').strip().lower()
    if view not in ('all', 'published', 'private'):
        view = 'all'
    category = (request.args.get('category') or '').strip().lower() or None
    if category not in CATEGORY_VALUES:
        category = None
    kind = (request.args.get('kind') or '').strip().lower() or None
    if kind not in ('image', 'video'):
        kind = None

    db_error, rows, stats = None, [], dict(_EMPTY_STATS)
    try:
        rows = db.list_media(visibility=view, category=category, kind=kind)
        stats = db.media_stats()
    except db.DatabaseUnavailable as exc:
        db_error = str(exc)

    return render_template(
        'admin/dashboard.html',
        items=[_media_json(row, for_admin=True) for row in rows],
        stats=stats, db_error=db_error,
        view=view, category=category, kind=kind,
    )


@app.post('/admin/media/upload')
@auth.login_required
def admin_media_upload():
    """Uploads one photo or film. It arrives as ADMIN ONLY unless published explicitly."""
    if not auth.csrf_ok():
        abort(400)
    admin = auth.current_admin()
    if admin is None:
        return redirect(url_for('admin_login'))
    try:
        row = store_upload(admin['id'])
    except storage.UploadError as exc:
        flash(str(exc), 'error')
    except db.DatabaseUnavailable as exc:
        flash(f'MySQL is not reachable, so the upload was not saved. {exc}', 'error')
    else:
        visibility = 'admin only' if row.get('is_private') else 'visible to viewers'
        flash(f'"{row["title"]}" was added ({visibility}).', 'success')
    return redirect(_admin_back_url())


@app.post('/admin/media/<int:media_id>/visibility')
@auth.login_required
def admin_media_visibility(media_id: int):
    """The publish / hide switch for one item."""
    if not auth.csrf_ok():
        abort(400)
    publish = (request.form.get('visibility') or '').strip().lower() == 'published'
    try:
        row = set_visibility(media_id, is_private=not publish)
    except db.DatabaseUnavailable as exc:
        flash(f'MySQL is not reachable, so nothing changed. {exc}', 'error')
        return redirect(_admin_back_url())

    if row is None:
        flash('That item no longer exists.', 'error')
    elif row.get('is_private'):
        flash(f'"{row["title"]}" is now admin only – viewers cannot see it.', 'success')
    else:
        flash(f'"{row["title"]}" is now published and appears in the gallery.', 'success')
    return redirect(_admin_back_url())


@app.post('/admin/media/<int:media_id>/update')
@auth.login_required
def admin_media_update(media_id: int):
    """Renames an item, moves it to another category, or changes its visibility."""
    if not auth.csrf_ok():
        abort(400)

    fields: dict = {}
    title = (request.form.get('title') or '').strip()
    if title:
        fields['title'] = title[:160]
    category = (request.form.get('category') or '').strip().lower()
    if category in CATEGORY_VALUES:
        fields['category'] = category
    if request.form.get('visibility'):
        fields['is_private'] = 0 if _requested_visibility() == 'published' else 1

    try:
        row = update_details(media_id, fields)
    except db.DatabaseUnavailable as exc:
        flash(f'MySQL is not reachable, so nothing changed. {exc}', 'error')
        return redirect(_admin_back_url())

    flash('Changes saved.' if row else 'That item no longer exists.',
          'success' if row else 'error')
    return redirect(_admin_back_url())


@app.post('/admin/media/<int:media_id>/delete')
@auth.login_required
def admin_media_delete(media_id: int):
    """Removes an item: the row, the file and its poster."""
    if not auth.csrf_ok():
        abort(400)
    try:
        row = remove_media(media_id)
    except db.DatabaseUnavailable as exc:
        flash(f'MySQL is not reachable, so nothing was deleted. {exc}', 'error')
        return redirect(_admin_back_url())

    if row is None:
        flash('That item no longer exists.', 'error')
    else:
        flash(f'"{row["title"]}" and its file were deleted.', 'success')
    return redirect(_admin_back_url())


# --------------------------------------------------------------------------- #
#  Admin JSON API
#  The same rules as the dashboard, for scripts / a mobile client.
#  Every POST or DELETE needs the CSRF token; GET /api/admin/session hands one out.
# --------------------------------------------------------------------------- #
@app.get('/api/admin/session')
def api_admin_session():
    """Is the caller signed in? Also returns the CSRF token to use next."""
    admin = auth.current_admin()
    return jsonify(authenticated=admin is not None, admin=admin,
                   csrf_token=auth.csrf_token())


@app.post('/api/admin/login')
def api_admin_login():
    """Signs in and answers with the admin document plus a fresh CSRF token."""
    if not auth.csrf_ok():
        return jsonify(error='invalid_csrf_token',
                       message='Send the csrf_token from GET /api/admin/session.',
                       csrf_token=auth.csrf_token()), 400

    payload = request.form if request.form else (request.get_json(silent=True) or {})
    admin, error, status = auth.authenticate(
        str(payload.get('username') or '').strip(),
        str(payload.get('password') or ''),
    )
    if error or admin is None:
        return jsonify(error='login_failed',
                       message=error or 'Sign-in failed. Please try again.'), status

    auth.start_session(admin)
    return jsonify(authenticated=True,
                   admin={'id': admin['id'], 'username': admin['username']},
                   csrf_token=auth.csrf_token())


@app.post('/api/admin/logout')
def api_admin_logout():
    if not auth.csrf_ok():
        return jsonify(error='invalid_csrf_token'), 400
    auth.end_session()
    return jsonify(authenticated=False)


@app.get('/api/admin/media')
@auth.api_login_required
def api_admin_media():
    """EVERY item, admin-only material included. ?visibility=all|published|private"""
    visibility = (request.args.get('visibility') or 'all').strip().lower()
    if visibility not in ('all', 'published', 'private'):
        visibility = 'all'
    category = (request.args.get('category') or '').strip().lower() or None
    if category not in CATEGORY_VALUES:
        category = None
    kind = (request.args.get('kind') or '').strip().lower() or None
    if kind not in ('image', 'video'):
        kind = None

    try:
        rows = db.list_media(visibility=visibility, category=category, kind=kind)
        stats = db.media_stats()
    except db.DatabaseUnavailable as exc:
        return jsonify(error='database_unavailable', message=str(exc)), 503

    return jsonify(items=[_media_json(row, for_admin=True) for row in rows],
                   count=len(rows), stats=stats)


@app.post('/api/admin/media')
@auth.api_login_required
def api_admin_media_create():
    """Uploads one item.

    multipart/form-data with:
      file (required), poster (films only), title, category,
      kind=image|video, visibility=private|published   (private is the default)
    """
    if not auth.csrf_ok():
        return jsonify(error='invalid_csrf_token'), 400
    admin = auth.current_admin()
    if admin is None:
        return jsonify(error='authentication_required'), 401
    try:
        row = store_upload(admin['id'])
    except storage.UploadError as exc:
        return jsonify(error='upload_rejected', message=str(exc)), 400
    except db.DatabaseUnavailable as exc:
        return jsonify(error='database_unavailable', message=str(exc)), 503
    return jsonify(item=_media_json(row, for_admin=True)), 201


@app.post('/api/admin/media/<int:media_id>')
@auth.api_login_required
def api_admin_media_update(media_id: int):
    """Changes title / category / visibility. Form fields or a JSON body."""
    if not auth.csrf_ok():
        return jsonify(error='invalid_csrf_token'), 400

    payload = request.form if request.form else (request.get_json(silent=True) or {})
    fields: dict = {}

    if 'title' in payload:
        title = str(payload.get('title') or '').strip()
        if title:
            fields['title'] = title[:160]
    if 'category' in payload:
        new_category = str(payload.get('category') or '').strip().lower()
        if new_category not in CATEGORY_VALUES:
            return jsonify(error='invalid_category',
                           message='category must be one of: ' + ', '.join(CATEGORY_VALUES)), 400
        fields['category'] = new_category
    if 'visibility' in payload or 'is_private' in payload:
        raw = str(payload.get('visibility', payload.get('is_private'))).strip().lower()
        fields['is_private'] = 0 if raw in ('published', 'public', '0', 'false', 'no') else 1

    try:
        row = update_details(media_id, fields)
    except db.DatabaseUnavailable as exc:
        return jsonify(error='database_unavailable', message=str(exc)), 503
    if row is None:
        return jsonify(error='not_found'), 404
    return jsonify(item=_media_json(row, for_admin=True))


@app.delete('/api/admin/media/<int:media_id>')
@auth.api_login_required
def api_admin_media_delete(media_id: int):
    """Deletes the row and the file(s)."""
    if not auth.csrf_ok():
        return jsonify(error='invalid_csrf_token'), 400
    try:
        row = remove_media(media_id)
    except db.DatabaseUnavailable as exc:
        return jsonify(error='database_unavailable', message=str(exc)), 503
    if row is None:
        return jsonify(error='not_found'), 404
    return jsonify(deleted=True, id=media_id)


# --------------------------------------------------------------------------- #
#  Error pages
# --------------------------------------------------------------------------- #
def _wants_json() -> bool:
    return request.path.startswith('/api/') or \
        'application/json' in (request.headers.get('Accept') or '')


@app.errorhandler(HTTPException)
def handle_http_error(error):
    """JSON for the API, a friendly page for everything else."""
    status = error.code or 500

    if _wants_json():
        name = (error.name or 'error').lower().replace(' ', '_')
        return jsonify(error=name, message=error.description, status=status), status

    limit_mb = Config.MAX_CONTENT_LENGTH // (1024 * 1024)
    messages = {
        400: 'That request was not accepted – please try again from the page.',
        403: 'You are not allowed to do that.',
        404: 'That page could not be found.',
        413: f'The file is bigger than the upload limit of {limit_mb} MB.',
        503: 'MySQL is not available right now, so this page cannot load its data.',
    }
    return render_template(
        'error.html',
        status=status,
        heading=error.name or 'Something went wrong',
        message=messages.get(status, error.description or 'Please try again.'),
    ), status


# --------------------------------------------------------------------------- #
#  Command line
# --------------------------------------------------------------------------- #
#  The values shipped in the source and in .env.example. A SECRET_KEY that is
#  still one of these signs every session cookie with a key the whole world
#  knows, so it is worth a loud warning on start-up.
_WEAK_SECRET_KEYS = frozenset({
    'eventora-dev-secret-key-change-me',
    'change-this-to-a-long-random-string',
})


def cmd_init_db() -> int:
    """python app.py init-db – creates the database, the tables and first admin."""
    try:
        result = db.ensure_schema()
    except db.DatabaseUnavailable as exc:
        print(f'[x] {exc}')
        print('    Is MySQL running? Check MYSQL_USER / MYSQL_PASSWORD in .env.')
        return 1

    print(f'[ok] Database "{result["database"]}" is ready '
          f'({result["statements"]} statements applied, {result["skipped"]} skipped).')

    if Config.ADMIN_PASSWORD:
        return cmd_create_admin(Config.ADMIN_USERNAME, Config.ADMIN_PASSWORD, quiet=True)

    print('[i] No ADMIN_PASSWORD in .env, so no administrator was created yet.')
    print('    Create one with:  python app.py create-admin')
    return 0


def cmd_create_admin(username=None, password=None, quiet=False) -> int:
    """python app.py create-admin – creates an account or resets its password."""
    username = (username or Config.ADMIN_USERNAME or '').strip()
    if not username and sys.stdin.isatty():
        username = input('Admin username: ').strip()
    if not username:
        print('[x] A username is required (use --username).')
        return 1

    if not password:
        if not sys.stdin.isatty():
            print('[x] No password supplied. Use --password or ADMIN_PASSWORD in .env.')
            return 1
        password = getpass.getpass(f'New password for "{username}": ')
        repeated = getpass.getpass('Repeat the password: ')
        if password != repeated:
            print('[x] The two passwords do not match.')
            return 1

    if len(password) < Config.MIN_PASSWORD_LENGTH:
        print(f'[x] Please use at least {Config.MIN_PASSWORD_LENGTH} characters.')
        return 1

    try:
        db.upsert_admin(username, auth.hash_password(password))
    except db.DatabaseUnavailable as exc:
        print(f'[x] {exc}')
        print('    Run "python app.py init-db" once MySQL is running.')
        return 1

    print(f'[ok] Administrator "{username}" is ready.')
    if not quiet:
        print('     Only a PBKDF2 hash is stored, and the password is never served.')
        print('     Sign in at /admin/login')
    return 0


def cmd_check_db() -> int:
    """python app.py check-db – prints what the backend can see."""
    try:
        version = db.server_version()
        stats = db.media_stats()
        admins = db.count_admins()
    except db.DatabaseUnavailable as exc:
        print(f'[x] {exc}')
        return 1

    print(f'[ok] MySQL {version} – database "{Config.MYSQL_DATABASE}" is reachable.')
    print(f'     Administrators : {admins}')
    print(f'     Media          : {stats["total"]} total '
          f'({stats["published"]} published, {stats["private_items"]} admin only – '
          f'{stats["images"]} images, {stats["videos"]} films)')
    return 0


@app.cli.command('init-db')
def init_db_command():
    """flask --app app init-db"""
    raise SystemExit(cmd_init_db())


@app.cli.command('create-admin')
@click.option('--username', default=None, help='Login name for the administrator.')
@click.option('--password', default=None, help='Password (omit it to be asked safely).')
def create_admin_command(username, password):
    """flask --app app create-admin"""
    raise SystemExit(cmd_create_admin(username, password))


@app.cli.command('check-db')
def check_db_command():
    """flask --app app check-db"""
    raise SystemExit(cmd_check_db())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='python app.py',
        description='Eventora – Flask API + MySQL admin backend',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='examples:\n'
               '  python app.py init-db\n'
               '  python app.py create-admin --username admin\n'
               '  python app.py check-db\n'
               '  python app.py                     # http://127.0.0.1:5000\n',
    )
    parser.add_argument('command', nargs='?', default='run',
                        choices=('run', 'init-db', 'create-admin', 'check-db'),
                        help='what to do (default: start the server)')
    parser.add_argument('--host', default=os.getenv('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT') or 5000))
    parser.add_argument('--username', default=None)
    parser.add_argument('--password', default=None)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args(argv)

    if args.command == 'init-db':
        return cmd_init_db()
    if args.command == 'create-admin':
        return cmd_create_admin(args.username, args.password)
    if args.command == 'check-db':
        return cmd_check_db()

    if app.config['SECRET_KEY'] in _WEAK_SECRET_KEYS:
        print('[!] SECRET_KEY is still a built-in / example value, so session cookies')
        print('    can be forged. Set a random one in .env before going live:')
        print('      python -c "import secrets; print(secrets.token_hex(32))"')

    base = f'http://{args.host}:{args.port}'
    print(f'[i] Website     : {base}/')
    print(f'[i] Admin panel : {base}/admin/login   (not linked from the website)')
    print(f'[i] Public API  : {base}/api/media     (published items only)')
    try:
        print(f'[i] MySQL       : {db.server_version()} ({Config.MYSQL_DATABASE})')
    except db.DatabaseUnavailable as exc:
        print(f'[!] MySQL       : not reachable – {exc}')
        print('    Run "python app.py init-db" once MySQL is running.')

    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())



