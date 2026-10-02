 # GRS – Event Management Company Website

A responsive, three-page website for an event management company, built with
**HTML5, CSS3 and vanilla JavaScript** (no front-end frameworks, no libraries, no build
step) plus a small **Python (Flask) API and MySQL database** that power the private
admin area – where photos and films are uploaded, kept away from visitors and
published only when the admin decides to.

## Pages

| File           | Purpose                                                             |
| -------------- | ------------------------------------------------------------------- |
| `index.html`   | Home – hero, services, why choose us, team, statistics, map, footer |
| `events.html`  | Event photo gallery with category filters and a lightbox            |
| `company.html` | About, mission, vision, values, timeline, team, contact details     |
| `app.py`       | Flask app: serves the pages above, the JSON API and the admin area  |
| `templates/admin/login.html`     | Admin sign-in (`noindex`, not linked from the site) |
| `templates/admin/dashboard.html` | Upload photos & films, publish them or keep them private |


## Folder structure

```
event-management-website/
├── index.html
├── events.html
├── company.html
├── README.md
├── app.py               (Flask: site routes, JSON API, admin routes, CLI)
├── config.py            (all settings, read from .env if it exists)
├── db.py                (MySQL access layer – every query lives here)
├── auth.py              (password hashing, sessions, CSRF, login throttle)
├── storage.py           (upload validation, random file names, posters)
├── schema.sql           (database + tables – run by "python app.py init-db")
├── requirements.txt     (Flask, PyMySQL, python-dotenv)
├── start.ps1            (Windows launcher: starts MySQL when needed, then Flask)
├── .env                 (your own settings – a copy of .env.example, never committed)
├── .env.example         (copy to .env and fill in)
├── css/
│   ├── style.css        (all site styling, light + dark theme via CSS variables)
│   └── admin.css        (admin panel – reuses the tokens from style.css)
├── js/
│   ├── script.js        (all site behaviour, commented section by section)
│   └── admin.js         (admin panel helpers: preview, confirm, copy link)
├── templates/
│   ├── error.html
│   └── admin/
│       ├── base.html
│       ├── login.html
│       └── dashboard.html
├── uploads/             (created at start-up; uploaded media, never committed)
│   ├── images/
│   ├── videos/
│   └── posters/
├── images/
│   ├── logo.png
│   ├── hero.jpg
│   ├── event1.png … event13.png      (gallery photos)
│   ├── a1.png … a6.png, b1.png … b10.png
│   └── team1.jpg
└── video/
    └── Video1.mp4, Video2.mp4
```

## Running the site

### Option A – the whole stack (website + admin panel + MySQL)

```bashe
pip install -r requirements.txt        # Flask, PyMySQL, python-dotenv
copy .env.example .env                 # then edit MYSQL_* and SECRET_KEY
..\venv\Scripts\python.exe app.py
python app.py init-db                  # creates the database and the tables
python app.py create-admin             # asks for a username and a password
python app.py                          # http://127.0.0.1:5000
```

| URL                                  | Who it is for                                 |
| ------------------------------------ | --------------------------------------------- |
| `http://127.0.0.1:5000/`             | Visitors                                      |
| `http://127.0.0.1:5000/admin/login`  | Only you – never linked from the public pages |
| `http://127.0.0.1:5000/api/media`    | The gallery feed used by `events.html`        |


`python app.py check-db` prints the MySQL version, how many administrators exist and
how the media library is split between published and admin-only items.
`python app.py --help` lists every command.

### MySQL on this machine

There is no MySQL *Windows service* here (registering one needs an elevated shell), so
nothing starts MySQL at boot. Two safety nets cover that, so the admin panel never ends
up showing "The database is not reachable" over the sign-in form again:

- **`MYSQL_AUTOSTART=1`** (the default on Windows, in `.env`): the first query that finds
  nothing listening on `MYSQL_HOST:MYSQL_PORT` starts MySQL exactly the way the launcher
  does, waits for the port and retries the connection. That happens inside `db.py`, so it
  also covers `python app.py` started from the editor or by hand. The attempt is made at
  most once per process, only for a local host, and **only** when the port is closed – a
  wrong password, a deleted database or a hosted MySQL never start a server.
- **`.\start.ps1`** does the same before it boots Flask: `.\start.ps1` (or nothing, it is
  the default action) starts MySQL if port 3306 is closed and then runs the website,
  `.\start.ps1 db` starts only the database, `.\start.ps1 status` reports what is up,
  `.\start.ps1 stop` shuts the website and MySQL down.

Set `MYSQL_AUTOSTART=0` to switch the automatic start off, and `MYSQLD_PATH` /
`MYSQL_DEFAULTS_FILE` / `MYSQL_START_TIMEOUT` when `mysqld` lives somewhere unusual or
needs longer to come up. The VS Code task **MySQL: start (port 3306)** calls the launcher
for you, and the two "Flask: run app" tasks run it first.

### Option B – just the static pages

No installation needed. Open `index.html` in any modern browser, or serve the folder
with any static host (for example `python3 -m http.server` inside the folder).
The admin panel, the uploads and everything that needs MySQL are simply not available
in this mode, and the gallery falls back to the photos written in the HTML.

## Admin area, Flask API and MySQL

The admin area is **not linked from the public website** – no visitor sees a "login"
button, the word "admin" does not appear on any public page, and both the admin pages
and the admin API answer with `X-Robots-Tag: noindex, nofollow`. You reach it by typing
`/admin/login` yourself.

### The privacy rule

| Where the item is                       | Who can see it                                                        |
| --------------------------------------- | --------------------------------------------------------------------- |
| Just uploaded (`is_private = 1`)         | **Only the signed-in admin.** `GET /api/media` filters it out in SQL and `/media/<file>` answers **404** to everybody else, so a guessed URL leaks nothing. It never appears in the gallery. |
| Published (`is_private = 0`)             | Everyone – the item joins the `events.html` gallery and its file is served to visitors. |
| Published item switched back to private  | It leaves the gallery immediately and its file stops being served to visitors. |

Other safeguards in the backend:

- Passwords are stored as **PBKDF2-SHA256 hashes** (Werkzeug); the plain password is
  never written anywhere.
- Sessions are signed cookies (`HttpOnly`, `SameSite=Lax`, 8 hours), a **new session id
  and CSRF token** are issued at every sign-in, and you can set
  `SESSION_COOKIE_SECURE=1` when running behind HTTPS.
- Every POST and DELETE needs a **CSRF token**, the JSON API included.
- Five failed sign-ins from the same address and username **lock that pair for 10 minutes**.
- Uploads are checked by **extension and magic bytes** (PNG/JPG/GIF/WEBP/AVIF and
  MP4/WEBM/MOV/M4V/OGV), renamed to a random 32-character name, and capped by
  `MAX_IMAGE_MB` / `MAX_VIDEO_MB` (`MAX_UPLOAD_MB` caps the whole request).
- The public routes are an **allow-list**: only known-safe extensions are served and
  `uploads/`, `templates/`, `__pycache__` and dot-files (`.env`) are refused, so
  `app.py`, your database password and private media can never be downloaded as
  static files.
- Deleting an item removes the row **and** the files from disk.

### Uploading from the dashboard

1. Sign in at `/admin/login`.
2. Choose a title, category, media type and **who can see it** (the default is
   *Admin only*), then pick the file – a live preview confirms it is the right one.
3. A film uploaded without a poster gets a branded SVG poster generated automatically,
   so its gallery tile is never blank.
4. Press **Publish to viewers** on an item when it is ready. The dashboard shows the
   split with counters and filters (`All / Published / Admin only`, plus categories).

### JSON API

| Method & path                    | What it does                                                             | Auth |
| -------------------------------- | ------------------------------------------------------------------------ | ---- |
| `GET /api/health`                | Flask + MySQL status and library counts                                  | –    |
| `GET /api/media`                 | Gallery feed: **published items only**, `?category=` `?kind=`             | –    |
| `GET /media/<file>`              | One stored file; 404 unless it is published or you are signed in          | session |
| `GET /api/admin/session`         | `{authenticated, admin, csrf_token}`                                     | –    |
| `POST /api/admin/login`          | Sign in (`username`, `password`, `csrf_token`)                            | CSRF |
| `POST /api/admin/logout`         | Sign out                                                                 | CSRF |
| `GET /api/admin/media`           | Every item, private ones included: `?visibility=all\|published\|private`  | session |
| `POST /api/admin/media`          | Upload (multipart): `file`, `poster`, `title`, `category`, `kind`, `visibility` | session |
| `POST /api/admin/media/<id>`     | Change `title`, `category` or `visibility`                                | session |
| `DELETE /api/admin/media/<id>`   | Delete the row and its files                                              | session |

Example session with `curl` (the upload stays admin-only without `visibility=published`):

```bash
curl -c cookies.txt http://127.0.0.1:5000/api/admin/session        # hands out the CSRF token

curl -b cookies.txt -c cookies.txt -H "X-CSRF-Token: <token>" \
     -d "username=admin&password=<password>" http://127.0.0.1:5000/api/admin/login


### Database

`schema.sql` creates `eventora_db` with two tables: `admins` (username, PBKDF2 hash,
last sign-in) and `media` (title, category, kind, file, poster, mime type, size,
`is_private`, who uploaded it, timestamps). Run `python app.py init-db`, or import the
file with the `mysql` client or phpMyAdmin – every statement is `IF NOT EXISTS` safe, so
running it twice changes nothing.


## Replacing the placeholders

All placeholders are easy to find with a project-wide search.

### Company name
The name "Eventora" appears in the header, footer, `<title>` tags and copyright line
of all three pages. Search for `Eventora` and replace it.

### Google Maps (index.html)
1. In Google Maps, find your office, click **Share → Embed a map** and copy the `src` URL.
2. In `index.html`, replace `YOUR_GOOGLE_MAP_EMBED_URL` with that URL.

Until you do this, a friendly "Your map will appear here" panel is shown instead of a broken frame.

These appear in the floating buttons, the "Connect With Us" popup, the footer,
the team cards and the company contact section on every page.

### Contact details
Search for and replace:


Also update the matching `tel:` and `mailto:` links.

### Images
Every image in `images/` is a generated placeholder illustration. Replace each file
with your own photo **using the same file name** and the site will pick it up automatically.

| File                     | Recommended size | Used for                           |
| ------------------------ | ---------------- | ---------------------------------- |
| `logo.png`               | 256 × 256        | Header, footer, favicon            |
| `hero.jpg`               | 1920 × 1080      | Home page hero background          |
| `event1.png – event13.png` | 1200 × 900     | Gallery (see categories below)     |
| `a1.png – a6.png`, `b1.png – b10.png` | 1200 × 900 | Gallery photos     |
| `team1.jpg`              | 800 × 800 (square) | Circular team portrait           |

Remember to update the `alt` text of each image in the HTML so it describes your real photo.
Team names and roles are placeholders in the team sections of `index.html` and `company.html`.

### Adding or changing gallery photos (events.html)
Each photo is one `<figure class="gallery-item" data-category="...">` block. Valid
categories are `weddings`, `corporate`, `birthday`, `concert` and `engagement`.
Copy an existing block, change the image path, title and category, and the filters
and lightbox will include it automatically. To add a new filter, add a button with a
matching `data-filter` value.

The same block is generated by `js/script.js` (section 11) for every photo or film you
**publish** in the admin panel, so those items need no HTML at all – upload them at
`/admin/login` instead.

## Theme colours
All colours live in CSS variables at the top of `css/style.css`. The light theme is
defined on `:root` and the dark theme on `[data-theme="dark"]`, so a single file
controls both. Main variables: `--bg-color`, `--text-color`, `--primary-color`,
`--secondary-color`, `--card-color`, `--border-color`.

The chosen theme is saved in `localStorage` (key `eventora-theme`) and restored on
every page. If nothing is saved, the visitor's system preference is used.
