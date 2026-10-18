"""
Access control — implements the can_see() function from docs/ARCHITECTURE.md
"Access control" exactly.

Pseudo-code from the doc (reproduced verbatim for traceability):

    def can_see(viewer_id, story) -> bool:
        if story.status == "hidden" and viewer_id != story.teller_id: return False
        if story.status == "pending" and role(viewer_id) not in ("center", "admin") \\
           and viewer_id != story.teller_id: return False
        t = story.access.type
        if t == "private":    return viewer_id == story.teller_id
        if t == "selected":   return viewer_id == story.teller_id or viewer_id in story.access.person_ids
        if t == "circle":     return is_member(viewer_id, story.circle_id)
        if t == "all_family": return shares_any_circle(viewer_id, story.teller_id)
        return False

Notes:
- role(viewer_id) is always evaluated in the context of story.circle_id because
  memberships are per (person, circle) pair.
- can_see() takes a db session as its first argument because it must query
  Membership rows.
- Private segments (is_private=True) are never surfaced by any tool; that
  filtering happens at the query level, not here.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.models import Membership, Story
from core.enums import Role, StoryStatus, AccessType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def role(db: Session, viewer_id: str, circle_id: str) -> str | None:
    """Return the viewer's Role in the given circle, or None if not a member."""
    m = (
        db.query(Membership)
        .filter(
            Membership.person_id == viewer_id,
            Membership.circle_id == circle_id,
        )
        .first()
    )
    return m.role if m else None


def is_member(db: Session, viewer_id: str, circle_id: str) -> bool:
    """Return True if viewer_id has any membership in circle_id."""
    return (
        db.query(Membership)
        .filter(
            Membership.person_id == viewer_id,
            Membership.circle_id == circle_id,
        )
        .first()
        is not None
    )


def shares_any_circle(db: Session, viewer_id: str, teller_id: str) -> bool:
    """Return True if viewer and teller share at least one circle.

    Used for the 'all_family' access level (Vision scope).
    """
    viewer_circle_ids = [
        row.circle_id
        for row in db.query(Membership.circle_id)
        .filter(Membership.person_id == viewer_id)
        .all()
    ]
    if not viewer_circle_ids:
        return False
    return (
        db.query(Membership)
        .filter(
            Membership.person_id == teller_id,
            Membership.circle_id.in_(viewer_circle_ids),
        )
        .first()
        is not None
    )


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------

def can_see(db: Session, viewer_id: str, story: Story) -> bool:
    """Return True if viewer_id is allowed to see story.

    Implements the access-control pseudo-code from the doc exactly.
    Every MCP tool and REST endpoint must call this before returning story data.
    """
    # --- status guards -------------------------------------------------------
    if story.status == StoryStatus.hidden and viewer_id != story.teller_id:
        return False

    if (
        story.status == StoryStatus.pending
        and role(db, viewer_id, story.circle_id) not in (Role.center, Role.admin)
        and viewer_id != story.teller_id
    ):
        return False

    # --- access-type rules ---------------------------------------------------
    access = story.access_proxy
    t = access.type

    if t == AccessType.private:
        return viewer_id == story.teller_id

    if t == AccessType.selected:
        return viewer_id == story.teller_id or viewer_id in access.person_ids

    if t == AccessType.circle:
        return is_member(db, viewer_id, story.circle_id)

    if t == AccessType.all_family:
        return shares_any_circle(db, viewer_id, story.teller_id)

    return False
