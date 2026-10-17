"""
photo_url / photo_caption for story, feed and lifeline items (read only).

Kept apart from core/services/photos.py so stories.py and feed.py can use it
without an import cycle. The caller has already checked can_see(); a hidden
story never shows its photo, even to its teller.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.enums import StoryStatus
from core.models import Story, StoryPhoto


def current_photo(db: DbSession, story_id: str) -> StoryPhoto | None:
    return db.query(StoryPhoto).filter(StoryPhoto.story_id == story_id).first()


def photo_fields(db: DbSession, story: Story) -> dict[str, Any]:
    photo = None if story.status == StoryStatus.hidden else current_photo(db, story.id)
    return {
        "photo_url": f"/api/photos/{photo.id}" if photo else None,
        "photo_caption": photo.caption if photo else None,
    }
