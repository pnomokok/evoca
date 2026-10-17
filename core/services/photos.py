"""
Story photos for the family panel (one photo per story for now).

  set_photo       POST   /api/stories/{id}/photo
  delete_photo    DELETE /api/stories/{id}/photo
  photo_file      GET    /api/photos/{photo_id}
  (photo_url / photo_caption for story, feed and lifeline items: core/services/photo_view.py)

Rules:
- A story the viewer cannot see, or a hidden story, has no photo for anyone:
  uploads, deletes and reads get the same NotFound as a missing story, and
  photo_fields returns nulls. (Hidden counts as invisible here even for the
  teller, so a hidden story never exposes its photo.)
- Upload: the teller, any subject person, or an admin of the story's circle.
  Delete: the uploader, the teller, or an admin.
- Every upload is decoded and re-encoded (JPEG, at most 1600 px on the long
  side) into a new image, so no metadata of the original (EXIF, GPS, ICC,
  comments) survives. The file name is a fresh UUID, never the client's.
- The chat agent and the archivist never see photos: nothing here is offered
  through MCP.

Like core/services/stories.py, functions take an open session and an explicit
viewer_id and commit their own writes.
"""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session as DbSession

from core.access import can_see, role
from core.clock import now_utc
from core.enums import Role, StoryStatus
from core.models import Story, StoryPhoto, StorySubject
from core.services.photo_view import current_photo, photo_fields
from core.services.stories import STORY_NOT_FOUND, Forbidden, NotFound

log = logging.getLogger(__name__)

# Relative to the working directory, like data/audio (server/wav_writer.py).
PHOTO_DIR = Path("data") / "photos"

MAX_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1600
MAX_PIXELS = 25_000_000          # refuse decompression bombs before decoding
MAX_CAPTION = 120
# MPO is how Pillow reports many phone JPEGs (several frames); the first frame is used.
ACCEPTED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}

PHOTO_NOT_FOUND = "Photo not found."
NOT_ALLOWED = "You cannot change the photo of this story."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _photo_story(db: DbSession, viewer_id: str, story_id: str) -> Story:
    """The story, if the viewer can see it and it is not hidden."""
    story = db.get(Story, story_id)
    if story is None or story.status == StoryStatus.hidden or not can_see(db, viewer_id, story):
        raise NotFound(STORY_NOT_FOUND)
    return story


def _is_admin(db: DbSession, viewer_id: str, story: Story) -> bool:
    return role(db, viewer_id, story.circle_id) == Role.admin


def _remove_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        log.exception("Could not delete photo file %s", path)


def clean_jpeg(raw: bytes) -> bytes:
    """Validate an upload and re-encode it as a metadata-free JPEG.

    Raises ValueError (HTTP 400) for an empty, too big, unsupported or broken image.
    """
    if not raw:
        raise ValueError("The photo is empty.")
    if len(raw) > MAX_BYTES:
        raise ValueError("A photo can be at most 5 MB.")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format not in ACCEPTED_FORMATS:
                raise ValueError("A photo must be JPEG, PNG or WebP.")
            if img.width * img.height > MAX_PIXELS:
                raise ValueError("The photo is too large.")
            if img.format in ("JPEG", "MPO"):
                img.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))   # decode at reduced size when possible
            img.load()
            img = ImageOps.exif_transpose(img)     # keep the orientation the camera recorded
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                img = flat
            else:
                img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            # A brand-new image carries no info dict at all: nothing of the original survives.
            clean = Image.new("RGB", img.size)
            clean.paste(img)
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise ValueError("The photo could not be read.") from None
    out = io.BytesIO()
    clean.save(out, format="JPEG", quality=85, optimize=True, exif=b"")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------

def photo_file(db: DbSession, viewer_id: str, photo_id: str) -> Path:
    """The stored file, if the viewer may see the photo's story."""
    photo = db.get(StoryPhoto, photo_id)
    if photo is None:
        raise NotFound(PHOTO_NOT_FOUND)
    try:
        _photo_story(db, viewer_id, photo.story_id)
    except NotFound:
        raise NotFound(PHOTO_NOT_FOUND) from None
    path = Path(photo.path)
    if not path.exists():
        raise NotFound(PHOTO_NOT_FOUND)
    return path


# ---------------------------------------------------------------------------
# Write side
# ---------------------------------------------------------------------------

def set_photo(
    db: DbSession, viewer_id: str, story_id: str, raw: bytes, caption: str | None = None,
) -> dict[str, Any]:
    """Add or replace the story's photo. Returns {story_id, photo_url, photo_caption}."""
    story = _photo_story(db, viewer_id, story_id)
    allowed = (
        viewer_id == story.teller_id
        or db.get(StorySubject, (story.id, viewer_id)) is not None
        or _is_admin(db, viewer_id, story)
    )
    if not allowed:
        raise Forbidden(NOT_ALLOWED)
    caption = (caption or "").strip() or None
    if caption is not None and len(caption) > MAX_CAPTION:
        raise ValueError(f"A caption can be at most {MAX_CAPTION} characters.")
    jpeg = clean_jpeg(raw)

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    photo_id = str(uuid.uuid4())
    path = PHOTO_DIR / f"{photo_id}.jpg"
    path.write_bytes(jpeg)

    old = current_photo(db, story.id)
    old_path = old.path if old else None
    try:
        if old is not None:
            db.delete(old)
            db.flush()
        db.add(StoryPhoto(id=photo_id, story_id=story.id, path=path.as_posix(), caption=caption,
                          uploaded_by=viewer_id, created_at=now_utc().isoformat()))
        db.commit()
    except Exception:
        db.rollback()
        _remove_file(str(path))
        raise
    if old_path:
        _remove_file(old_path)
    return {"story_id": story.id, **photo_fields(db, story)}


def delete_photo(db: DbSession, viewer_id: str, story_id: str) -> dict[str, Any]:
    """Remove the story's photo (row and file)."""
    story = _photo_story(db, viewer_id, story_id)
    photo = current_photo(db, story.id)
    if photo is None:
        raise NotFound(PHOTO_NOT_FOUND)
    if viewer_id not in (photo.uploaded_by, story.teller_id) and not _is_admin(db, viewer_id, story):
        raise Forbidden(NOT_ALLOWED)
    path = photo.path
    db.delete(photo)
    db.commit()
    _remove_file(path)
    return {"story_id": story.id, "photo_url": None, "photo_caption": None}
