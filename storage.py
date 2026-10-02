"""Eventora – upload storage.

Responsible for everything that touches the disk under ``uploads/``:

  * validating that a file really is the image / film it claims to be
    (extension **and** magic bytes – a .png that is secretly a script is refused),
  * storing it under a random name so a visitor can never guess a private URL,
  * creating a branded SVG poster when a film is uploaded without one,
  * deleting files when their record is removed.

Every file lives inside ``uploads/images``, ``uploads/videos`` or
``uploads/posters`` and is only ever handed out by the ``/media/<file>`` route
in app.py, which first asks MySQL whether the visitor may see it.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from config import Config, MIME_TYPES


class UploadError(ValueError):
    """A friendly message about a file the admin chose – safe to show in the UI."""


# --------------------------------------------------------------------------- #
#  Folders
# --------------------------------------------------------------------------- #
def ensure_folders() -> None:
    """Creates uploads/ and its sub-folders (called on every start-up)."""
    Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for folder in Config.UPLOAD_FOLDERS:
        (Config.UPLOAD_DIR / folder).mkdir(exist_ok=True)


def safe_relative(name: str) -> str:
    """Turns a request path into 'folder/file.ext', or raises UploadError.

    Blocks absolute paths, '..' and any folder other than images/videos/posters.
    """
    candidate = str(name or '').replace('\\', '/').strip('/')
    parts = [p for p in candidate.split('/') if p not in ('', '.')]
    if not parts or len(parts) > 2:
        raise UploadError('Unsafe file path')
    if any(p == '..' or p.startswith('.') for p in parts):
        raise UploadError('Unsafe file path')
    if len(parts) == 2 and parts[0] not in Config.UPLOAD_FOLDERS:
        raise UploadError('Unsafe file path')
    return '/'.join(parts)


def resolve(name: str) -> Path | None:
    """Absolute path for a stored file name, or None if it is unsafe."""
    try:
        rel = safe_relative(name)
    except UploadError:
        return None
    return Config.UPLOAD_DIR / Path(*rel.split('/'))


# --------------------------------------------------------------------------- #
#  Kind detection (no external libraries – imghdr was removed in Python 3.13)
# --------------------------------------------------------------------------- #
_AVIF_BRANDS = (b'avif', b'avis')


def detect_kind(head: bytes) -> str | None:
    """'image', 'video' or None, decided from the first bytes of the file."""
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image'
    if head.startswith(b'\xff\xd8\xff'):
        return 'image'
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return 'image'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image'
    if head[4:8] == b'ftyp':                     # MP4 / MOV / AVIF container
        return 'image' if head[8:12] in _AVIF_BRANDS else 'video'
    if head[:4] == b'\x1a\x45\xdf\xa3':          # Matroska / WebM
        return 'video'
    if head.startswith(b'OggS'):
        return 'video'
    return None


def extensions_for(kind: str) -> tuple[str, ...]:
    return Config.IMAGE_EXTENSIONS if kind == 'image' else Config.VIDEO_EXTENSIONS


def _article(word: str) -> str:
    """'a' or 'an', so messages read like English ('an image', 'a video')."""
    return 'an' if (word or '')[:1].lower() in 'aeiou' else 'a'


def limit_mb(kind: str) -> int:
    return Config.MAX_IMAGE_MB if kind == 'image' else Config.MAX_VIDEO_MB


def human_size(num_bytes: int) -> str:
    size = float(num_bytes or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} GB'


# --------------------------------------------------------------------------- #
#  Saving
# --------------------------------------------------------------------------- #
def _new_name(kind_folder: str, suffix: str) -> str:
    return f'{kind_folder}/{uuid.uuid4().hex}{suffix}'


def _stream_to_disk(file_storage, rel_name: str) -> tuple[bytes, int]:
    """Writes the upload in 1 MB chunks, returning (first 512 bytes, size)."""
    destination = resolve(rel_name)
    size, head = 0, b''
    with open(destination, 'wb') as out:
        while True:
            chunk = file_storage.stream.read(Config.UPLOAD_CHUNK)
            if not chunk:
                break
            if len(head) < 512:
                head += chunk[:512 - len(head)]
            size += len(chunk)
            out.write(chunk)
    return head, size


def _remove(rel_name: str | None) -> None:
    if not rel_name:
        return
    path = resolve(rel_name)
    if path is not None and path.is_file():
        path.unlink(missing_ok=True)


def save_media(file_storage, kind: str) -> dict:
    """Validates and stores an image or a film.

    Returns {'file_name', 'mime_type', 'file_size'}; raises UploadError with a
    message that can be shown straight to the admin.
    """
    ensure_folders()
    original = Path(file_storage.filename or '')
    suffix = original.suffix.lower()

    if suffix not in extensions_for(kind):
        allowed = ', '.join(extensions_for(kind))
        raise UploadError(
            f'"{original.name}" is not a supported {kind} file. Allowed: {allowed}.'
        )

    rel_name = _new_name('images' if kind == 'image' else 'videos', suffix)
    try:
        head, size = _stream_to_disk(file_storage, rel_name)
    except OSError as exc:
        _remove(rel_name)
        raise UploadError(f'The file could not be saved: {exc}') from exc

    if size == 0:
        _remove(rel_name)
        raise UploadError('That file is empty – nothing was uploaded.')

    detected = detect_kind(head)
    if detected != kind:
        _remove(rel_name)
        if detected is None:
            raise UploadError(
                f'"{original.name}" does not look like a real {kind} file, so it was refused.'
            )
        raise UploadError(
            f'"{original.name}" is {_article(detected)} {detected} file, so it cannot be '
            f'uploaded as {_article(kind)} {kind}. Choose {detected} as the media type, '
            f'or pick another file.'
        )

    if size > limit_mb(kind) * 1024 * 1024:
        _remove(rel_name)
        raise UploadError(
            f'"{original.name}" is {human_size(size)} – the limit for a {kind} '
            f'is {limit_mb(kind)} MB.'
        )

    return {
        'file_name': rel_name,
        'mime_type': MIME_TYPES.get(suffix, 'application/octet-stream'),
        'file_size': size,
    }


def save_poster(file_storage) -> dict:
    """Stores an optional poster image that belongs to a film."""
    ensure_folders()
    original = Path(file_storage.filename or '')
    suffix = original.suffix.lower()
    if suffix not in Config.IMAGE_EXTENSIONS:
        raise UploadError(
            'A poster must be an image ('
            + ', '.join(Config.IMAGE_EXTENSIONS) + ').'
        )

    rel_name = _new_name('posters', suffix)
    try:
        head, size = _stream_to_disk(file_storage, rel_name)
    except OSError as exc:
        _remove(rel_name)
        raise UploadError(f'The poster could not be saved: {exc}') from exc

    if size == 0 or detect_kind(head) != 'image':
        _remove(rel_name)
        raise UploadError(f'"{original.name}" does not look like a real image file.')

    return {
        'file_name': rel_name,
        'mime_type': MIME_TYPES.get(suffix, 'application/octet-stream'),
        'file_size': size,
    }


# --------------------------------------------------------------------------- #
#  Generated poster for a film uploaded without one
# --------------------------------------------------------------------------- #
_POSTER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 900" width="1200" height="900">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#17123a"/>
      <stop offset=".55" stop-color="#43176f"/>
      <stop offset="1" stop-color="#7a1f5c"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="900" fill="url(#sky)"/>
  <circle cx="600" cy="410" r="104" fill="rgba(255,255,255,.14)" stroke="rgba(255,255,255,.55)" stroke-width="4"/>
  <path d="M562 350v120l100-60z" fill="#ffffff"/>
  <text x="600" y="606" fill="#ffffff" font-family="Georgia, 'Times New Roman', serif" font-size="48" text-anchor="middle">{title}</text>
  <text x="600" y="664" fill="rgba(255,255,255,.78)" font-family="Helvetica, Arial, sans-serif" font-size="30" letter-spacing="2" text-anchor="middle">{subtitle}</text>
</svg>
"""


def placeholder_poster(title: str, subtitle: str = '') -> str:
    """Writes a branded SVG poster and returns its stored file name."""
    ensure_folders()
    rel_name = _new_name('posters', '.svg')
    short_title = title if len(title) <= 44 else title[:41].rstrip() + '…'
    svg = _POSTER_SVG.format(
        title=xml_escape(short_title),
        subtitle=xml_escape(subtitle or 'Event film'),
    )
    resolve(rel_name).write_text(svg, encoding='utf-8')
    return rel_name


# --------------------------------------------------------------------------- #
#  Removing
# --------------------------------------------------------------------------- #
def delete(*rel_names: str | None) -> None:
    """Deletes stored files. Missing files are ignored (never raises)."""
    for rel_name in rel_names:
        _remove(rel_name)

