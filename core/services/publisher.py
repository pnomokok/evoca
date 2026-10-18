"""
Publisher: pending stories whose publish_at has passed become published.

docs/ARCHITECTURE.md "Background jobs and the demo clock": the publisher runs every minute. A new
story waits 24 hours as "pending" so the center or an admin can hide it first;
after that it opens according to its access.

publish_due_stories() is a plain function: the FastAPI lifespan calls it every
minute (server/app.py), tests call it directly. "Now" is core.clock.now_utc(),
so DEMO_NOW can move time forward:

    DEMO_NOW=2026-10-18T09:00:00+00:00 python -m core.services.publisher

Hidden stories are never pending, so they are never published here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session as DbSession

from core.clock import now_utc
from core.enums import StoryStatus
from core.models import Story


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def publish_due_stories(db: DbSession) -> list[str]:
    """Publish every pending story whose publish_at is not in the future.

    Compares parsed datetimes (not ISO strings), so differently formatted
    timestamps compare correctly. Commits and returns the published story ids.
    """
    now = now_utc()
    due = [
        story
        for story in db.query(Story).filter(Story.status == StoryStatus.pending).all()
        if _parse_utc(story.publish_at) <= now
    ]
    for story in due:
        story.status = StoryStatus.published
    if due:
        db.commit()
    return [story.id for story in due]


if __name__ == "__main__":
    from core.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        published = publish_due_stories(db)
    print(f"now = {now_utc().isoformat()}: published {len(published)} stories")
    for story_id in published:
        print(f"  {story_id}")
