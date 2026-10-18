"""
Story photo endpoints (one photo per story).

POST   /api/stories/{id}/photo   multipart image (+ caption, at most 120 characters)
DELETE /api/stories/{id}/photo
GET    /api/photos/{photo_id}

Logic and rules live in core.services.photos: who may upload or delete, the
re-encoding that strips every bit of metadata, and the same 404 for a story or
photo the viewer cannot see. Like audio, the panel fetches a photo with its
identity header and shows it as a blob; responses are Cache-Control: private, no-store.

limit_photo_upload (an HTTP middleware, added in server/app.py) refuses an upload
whose Content-Length is over the limit before the body is read, so a huge body
never reaches the multipart parser. Decoding and re-encoding run in a worker
thread so they never block the event loop.
"""

from __future__ import annotations

import re
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from core.services import photos as photo_svc
from server.auth import Viewer, panel_viewer
from server.routers.panel import _story_call

router = APIRouter()

_UPLOAD_PATH = re.compile(r"^/api/stories/[^/]+/photo$")
# Room for the multipart boundaries and the caption field around the image.
MAX_UPLOAD_BODY = photo_svc.MAX_BYTES + 64 * 1024


async def limit_photo_upload(request: Request, call_next):
    if request.method == "POST" and _UPLOAD_PATH.match(request.url.path):
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_UPLOAD_BODY):
            return JSONResponse(status_code=400, content={"detail": "A photo can be at most 5 MB."})
    return await call_next(request)


@router.post("/api/stories/{story_id}/photo")
async def post_story_photo(
    story_id: str,
    image: Annotated[UploadFile, File()],
    caption: Annotated[str | None, Form()] = None,
    viewer: Viewer = Depends(panel_viewer),
):
    """Add or replace the photo: the teller, a subject person or an admin. Matches POST_story_photo.json."""
    raw = await image.read(photo_svc.MAX_BYTES + 1)   # one byte more is enough to refuse it
    return await anyio.to_thread.run_sync(
        lambda: _story_call(viewer.circle_id, photo_svc.set_photo, viewer.person_id, story_id, raw, caption)
    )


@router.delete("/api/stories/{story_id}/photo")
async def delete_story_photo(
    story_id: str,
    viewer: Viewer = Depends(panel_viewer),
):
    """Remove the photo: its uploader, the teller or an admin."""
    return _story_call(viewer.circle_id, photo_svc.delete_photo, viewer.person_id, story_id)


@router.get("/api/photos/{photo_id}")
async def get_photo(
    photo_id: str,
    viewer: Viewer = Depends(panel_viewer),
):
    """The JPEG, only if the viewer can see its story (otherwise 404, like a missing photo)."""
    path = _story_call(viewer.circle_id, photo_svc.photo_file, viewer.person_id, photo_id)
    return Response(content=path.read_bytes(), media_type="image/jpeg",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
