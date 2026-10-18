"""
Business logic for the family panel's story endpoints (docs/ARCHITECTURE.md "REST API").

  build_lifeline      GET    /api/lifeline/{person_id}
  build_story         GET    /api/stories/{id}
  build_playlist      GET    /api/stories/{id}/playlist
  set_reaction        POST   /api/stories/{id}/reactions
  correct_period      PATCH  /api/stories/{id}/subjects/{person_id}
  update_story        PATCH  /api/stories/{id}
  remove_link         DELETE /api/links/{id}

Privacy rules applied here (docs/ARCHITECTURE.md "Design principles and rules"):
- Every story passes can_see() before any of its data is used. A story the
  viewer cannot see raises the same NotFound as a missing one, and a linked or
  retold story the viewer cannot see is dropped silently (no count, no id).
- Private segments never leave this module: audio ranges are cut around them,
  transcript words inside them are dropped, and durations are summed from the
  cut ranges. Only the teller is told that a story's session has a private part.
- Reactions are returned as which emojis are present and which are the
  viewer's own, never as counts.

Functions take an open SQLAlchemy session and an explicit viewer_id, like the
other services, and commit their own writes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.access import can_see, role
from core.clock import now_utc
from core.enums import AccessType, Emoji, LifePeriod, LinkStatus, PeriodSource, Role, StoryKind, StoryStatus
from core.models import (
    Circle, Membership, Person, Reaction, Segment, Story, StoryLink, StorySubject,
)
from core.services.feed import _teller
from core.services.photo_view import photo_fields

_PERIODS = [p.value for p in LifePeriod]

# Fixed age ranges per life period, for the lifeline's years (None = open end).
# docs/ARCHITECTURE.md "Data model".
PERIOD_AGES: dict[str, tuple[int, int | None]] = {
    LifePeriod.childhood.value: (0, 12),
    LifePeriod.youth.value: (13, 22),
    LifePeriod.marriage_early_years.value: (23, 30),
    LifePeriod.raising_children.value: (31, 45),
    LifePeriod.midlife.value: (46, 60),
    LifePeriod.retirement.value: (61, None),
}
_EMOJIS = [e.value for e in Emoji]
_SETTABLE_ACCESS = {AccessType.circle.value, AccessType.private.value}

STORY_NOT_FOUND = "Story not found."
LINK_NOT_FOUND = "Link not found."
PERSON_NOT_FOUND = "Person not found."
NOT_ALLOWED = "You cannot change this story."


class NotFound(Exception):
    """Missing, or not visible to the viewer (the two look the same)."""


class Forbidden(Exception):
    """Visible to the viewer, but this change is not theirs to make."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _visible_story(db: DbSession, viewer_id: str, story_id: str) -> Story:
    story = db.get(Story, story_id)
    if story is None or not can_see(db, viewer_id, story):
        raise NotFound(STORY_NOT_FOUND)
    return story


def _subjects(db: DbSession, story_id: str) -> list[StorySubject]:
    return db.query(StorySubject).filter(StorySubject.story_id == story_id).all()


def _subject_item(db: DbSession, s: StorySubject) -> dict[str, Any]:
    person = db.get(Person, s.person_id)
    return {
        "person_id": s.person_id,
        "name": person.name if person else None,
        "period": s.period,
        "period_source": s.period_source,
        "estimated": s.period_source != PeriodSource.family,
        "corrected_by": s.corrected_by,
    }


def _private_segments(db: DbSession, session_id: str, start_ms: int, end_ms: int) -> list[Segment]:
    return (
        db.query(Segment)
        .filter(
            Segment.session_id == session_id,
            Segment.is_private == True,  # noqa: E712
            Segment.start_ms < end_ms,
            Segment.end_ms > start_ms,
        )
        .order_by(Segment.start_ms)
        .all()
    )


def _audio_ranges(db: DbSession, story: Story) -> list[dict[str, Any]]:
    """The story's sources with every private segment cut out.

    Sources should already exclude private ranges, but a part can be marked
    private after the story was saved, so the cut is made again on every read.
    """
    ranges: list[dict[str, Any]] = []
    for src in story.sources or []:
        session_id = src.get("session_id")
        start, end = src.get("start_ms", 0), src.get("end_ms", 0)
        if not session_id or start >= end:
            continue
        pieces: list[tuple[int, int]] = []
        cursor = start
        for seg in _private_segments(db, session_id, start, end):
            if seg.start_ms > cursor:
                pieces.append((cursor, seg.start_ms))
            cursor = max(cursor, seg.end_ms)
        if cursor < end:
            pieces.append((cursor, end))
        for a, b in pieces:
            ranges.append({
                "session_id": session_id,
                "start_ms": a,
                "end_ms": b,
                "url": f"/api/audio/{session_id}?start={a}&end={b}",
            })
    return ranges


def _duration_ms(ranges: list[dict[str, Any]]) -> int:
    return sum(r["end_ms"] - r["start_ms"] for r in ranges)


def _transcript(db: DbSession, ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-private segments inside the (already cut) audio ranges, words clipped to them."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    session_order: list[str] = []
    for r in ranges:
        if r["session_id"] not in session_order:
            session_order.append(r["session_id"])

    for session_id in session_order:
        spans = [(r["start_ms"], r["end_ms"]) for r in ranges if r["session_id"] == session_id]
        segments = (
            db.query(Segment)
            .filter(Segment.session_id == session_id, Segment.is_private == False)  # noqa: E712
            .order_by(Segment.start_ms)
            .all()
        )
        for seg in segments:
            hits = [(a, b) for a, b in spans if seg.start_ms < b and seg.end_ms > a]
            if seg.id in seen or not hits:
                continue
            seen.add(seg.id)
            inside = any(a <= seg.start_ms and seg.end_ms <= b for a, b in hits)
            words = [
                w for w in seg.words or []
                if "start_ms" in w and "end_ms" in w
                and any(a <= w["start_ms"] and w["end_ms"] <= b for a, b in hits)
            ]
            if inside:
                text = seg.transcript
            else:
                # Only words timed inside the ranges; a partly overlapping segment
                # without word timings shows nothing (its text may belong to
                # another story).
                text = " ".join(w.get("w", "") for w in words)
            if not text and not words:
                continue
            speaker = db.get(Person, seg.speaker_id) if seg.speaker_id else None
            items.append({
                "segment_id": seg.id,
                "speaker": {"id": speaker.id, "name": speaker.name} if speaker else None,
                "start_ms": max(seg.start_ms, min(a for a, _ in hits)),
                "end_ms": min(seg.end_ms, max(b for _, b in hits)),
                "text": text,
                "words": words,
            })
    return items


def _has_private_part(db: DbSession, viewer_id: str, story: Story) -> bool:
    """True only for the teller, when a private part of theirs overlaps this story's own sources.

    Another speaker's private part is not counted, so the teller does not learn
    that someone else kept something private.
    """
    if viewer_id != story.teller_id:
        return False
    for src in story.sources or []:
        session_id = src.get("session_id")
        if not session_id:
            continue
        if any(seg.speaker_id == story.teller_id
               for seg in _private_segments(db, session_id, src.get("start_ms", 0), src.get("end_ms", 0))):
            return True
    return False


def _access(viewer_id: str, story: Story) -> dict[str, Any]:
    """The access level; who else was chosen (person_ids) only for the teller."""
    ids = list(story.access_proxy.person_ids) if viewer_id == story.teller_id else []
    return {"type": story.access_proxy.type, "person_ids": ids}


def _story_ref(db: DbSession, story: Story) -> dict[str, Any]:
    return {"id": story.id, "title": story.title, "teller": _teller(db, story.teller_id, story.circle_id)}


def _live_links(db: DbSession, story_id: str) -> list[StoryLink]:
    return (
        db.query(StoryLink)
        .filter(
            (StoryLink.from_story_id == story_id) | (StoryLink.to_story_id == story_id),
            StoryLink.status != LinkStatus.removed,
        )
        .all()
    )


def _visible_linked(db: DbSession, viewer_id: str, story: Story) -> list[tuple[StoryLink, Story]]:
    """Directly linked stories the viewer can_see(); the rest are dropped silently."""
    out: list[tuple[StoryLink, Story]] = []
    seen: set[str] = set()
    for link in _live_links(db, story.id):
        other_id = link.to_story_id if link.from_story_id == story.id else link.from_story_id
        if other_id == story.id or other_id in seen:
            continue
        other = db.get(Story, other_id)
        if other is None or not can_see(db, viewer_id, other):
            continue
        seen.add(other_id)
        out.append((link, other))
    return out


def _reactions(db: DbSession, viewer_id: str, story_id: str) -> dict[str, list[str]]:
    rows = db.query(Reaction).filter(Reaction.story_id == story_id).all()
    present = {r.emoji for r in rows}
    mine = {r.emoji for r in rows if r.person_id == viewer_id}
    return {
        "present": [e for e in _EMOJIS if e in present],
        "mine": [e for e in _EMOJIS if e in mine],
    }


def _is_center(db: DbSession, viewer_id: str, circle_id: str) -> bool:
    circle = db.get(Circle, circle_id)
    return circle is not None and circle.center_person_id == viewer_id


def _may_hide(db: DbSession, viewer_id: str, story: Story) -> bool:
    if viewer_id == story.teller_id or _is_center(db, viewer_id, story.circle_id):
        return True
    if role(db, viewer_id, story.circle_id) == Role.admin:
        return True
    return db.get(StorySubject, (story.id, viewer_id)) is not None


# ---------------------------------------------------------------------------
# GET /api/lifeline/{person_id}
# ---------------------------------------------------------------------------

def period_years(birth_year: int | None, period: str) -> dict[str, int | None] | None:
    """{from, to} calendar years of a period from birth_year and PERIOD_AGES.

    to is None for the open end (retirement) and when it lies beyond the
    current year; the whole value is None when birth_year is unknown.
    """
    if birth_year is None:
        return None
    age_from, age_to = PERIOD_AGES[period]
    to = birth_year + age_to if age_to is not None else None
    if to is not None and to > now_utc().year:
        to = None
    return {"from": birth_year + age_from, "to": to}


def build_lifeline(db: DbSession, viewer_id: str, person_id: str,
                   circle_id: str | None = None) -> dict[str, Any]:
    """Stories about person_id that the viewer can_see(), grouped by period.

    With circle_id (the panel's selected circle) the person must be in that
    circle and only that circle's stories are listed.

    Periods come in LifePeriod order, all of them, empty ones as empty lists;
    inside a period the oldest story comes first. The period is the subject's
    own (a family correction replaces the AI estimate on the same row). Each
    period carries years ({from, to}, see period_years).
    """
    viewer_circles = [
        c for (c,) in db.query(Membership.circle_id).filter(Membership.person_id == viewer_id).all()
        if circle_id is None or c == circle_id
    ]
    shared = (
        db.query(Membership)
        .filter(Membership.person_id == person_id, Membership.circle_id.in_(viewer_circles))
        .first()
        if viewer_circles else None
    )
    person = db.get(Person, person_id)
    if shared is None or person is None:
        raise NotFound(PERSON_NOT_FOUND)

    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {p: [] for p in _PERIODS}
    for subject in db.query(StorySubject).filter(StorySubject.person_id == person_id).all():
        story = db.get(Story, subject.story_id)
        if story is None or not can_see(db, viewer_id, story) or subject.period not in grouped:
            continue
        if circle_id is not None and story.circle_id != circle_id:
            continue
        grouped[subject.period].append((story.created_at, {
            "id": story.id,
            "title": story.title,
            "ai_summary": story.ai_summary,
            "teller": _teller(db, story.teller_id, story.circle_id),
            "period_source": subject.period_source,
            "estimated": subject.period_source != PeriodSource.family,
            "status": story.status,
            "duration_ms": _duration_ms(_audio_ranges(db, story)),
            **photo_fields(db, story),
        }))

    periods = [
        {
            "period": p,
            "years": period_years(person.birth_year, p),
            "stories": [item for _, item in sorted(grouped[p], key=lambda t: t[0])],
        }
        for p in _PERIODS
    ]
    return {
        "person": {
            "id": person.id,
            "name": person.name,
            "birth_year": person.birth_year,
            "relation_to_center": shared.relation_to_center,
        },
        "periods": periods,
        "gaps": [p["period"] for p in periods if not p["stories"]],
    }


# ---------------------------------------------------------------------------
# GET /api/stories/{id}
# ---------------------------------------------------------------------------

def build_story(db: DbSession, viewer_id: str, story_id: str) -> dict[str, Any]:
    story = _visible_story(db, viewer_id, story_id)
    ranges = _audio_ranges(db, story)

    # A retelling of a story the viewer cannot see looks like an original, so
    # neither the id nor the kind hints that the other story exists.
    kind, original_id = story.kind, story.original_story_id
    if original_id is not None:
        original = db.get(Story, original_id)
        if original is None or not can_see(db, viewer_id, original):
            kind, original_id = StoryKind.original, None

    retellings = [
        _story_ref(db, s)
        for s in db.query(Story).filter(Story.original_story_id == story.id).all()
        if can_see(db, viewer_id, s)
    ]

    return {
        "id": story.id,
        "circle_id": story.circle_id,
        "title": story.title,
        "ai_summary": story.ai_summary,
        "kind": kind,
        "original_story_id": original_id,
        "status": story.status,
        "teller": _teller(db, story.teller_id, story.circle_id),
        "subjects": [_subject_item(db, s) for s in _subjects(db, story.id)],
        "place": story.place,
        "stated_year": story.stated_year,
        **photo_fields(db, story),
        "access": _access(viewer_id, story),
        "can_hide": story.status != StoryStatus.hidden and _may_hide(db, viewer_id, story),
        "can_change_access": viewer_id == story.teller_id,
        "has_private_part": _has_private_part(db, viewer_id, story),
        "audio": ranges,
        "transcript": _transcript(db, ranges),
        "retellings": retellings,
        "linked_stories": [
            {
                "link_id": link.id,
                "reason": link.reason,
                "source": link.source,
                "status": link.status,
                "story": _story_ref(db, other),
            }
            for link, other in _visible_linked(db, viewer_id, story)
        ],
        "reactions": _reactions(db, viewer_id, story.id),
        "publish_at": story.publish_at,
        "created_at": story.created_at,
    }


# ---------------------------------------------------------------------------
# GET /api/stories/{id}/playlist
# ---------------------------------------------------------------------------

def build_playlist(db: DbSession, viewer_id: str, story_id: str) -> dict[str, Any]:
    """The story and its directly linked stories (depth 1), in life order.

    Ordered by each story's earliest subject period, then created_at. A linked
    story the viewer cannot see is skipped without a trace.
    """
    story = _visible_story(db, viewer_id, story_id)
    stories = [story] + [other for _, other in _visible_linked(db, viewer_id, story)]

    def earliest(s: Story) -> StorySubject | None:
        subs = [x for x in _subjects(db, s.id) if x.period in _PERIODS]
        return min(subs, key=lambda x: _PERIODS.index(x.period)) if subs else None

    keyed = []
    for s in stories:
        first = earliest(s)
        rank = _PERIODS.index(first.period) if first else len(_PERIODS)
        keyed.append((rank, s.created_at, s, first))
    keyed.sort(key=lambda t: (t[0], t[1]))

    items: list[dict[str, Any]] = []
    for _, _, s, first in keyed:
        teller = _teller(db, s.teller_id, s.circle_id)
        for r in _audio_ranges(db, s):
            items.append({
                "story_id": s.id,
                "title": s.title,
                "teller": teller,
                "period": first.period if first else None,
                "estimated": first is None or first.period_source != PeriodSource.family,
                **r,
            })
    return {"story_id": story.id, "items": items}


# ---------------------------------------------------------------------------
# POST /api/stories/{id}/reactions
# ---------------------------------------------------------------------------

def set_reaction(db: DbSession, viewer_id: str, story_id: str, emoji: str, action: str) -> dict[str, Any]:
    """Add or remove the viewer's emoji. Idempotent; a new reaction waits to be told to the center."""
    story = _visible_story(db, viewer_id, story_id)
    if emoji not in _EMOJIS:
        raise ValueError("Invalid emoji.")
    if action not in ("add", "remove"):
        raise ValueError("action must be 'add' or 'remove'.")

    existing = db.get(Reaction, (story.id, viewer_id, emoji))
    if action == "add" and existing is None:
        db.add(Reaction(
            story_id=story.id, person_id=viewer_id, emoji=emoji,
            delivered_to_center=False, created_at=now_utc().isoformat(),
        ))
    elif action == "remove" and existing is not None:
        db.delete(existing)
    db.commit()
    return {"story_id": story.id, **_reactions(db, viewer_id, story.id)}


# ---------------------------------------------------------------------------
# PATCH /api/stories/{id}/subjects/{person_id}
# ---------------------------------------------------------------------------

def correct_period(db: DbSession, viewer_id: str, story_id: str, person_id: str, period: str) -> dict[str, Any]:
    """A family correction of a subject's period; it wins over the AI estimate."""
    story = _visible_story(db, viewer_id, story_id)
    subject = db.get(StorySubject, (story.id, person_id))
    if subject is None:
        raise NotFound("Subject not found.")
    if period not in _PERIODS:
        raise ValueError("Invalid period.")
    subject.period = period
    subject.period_source = PeriodSource.family
    subject.corrected_by = viewer_id
    db.commit()
    return _subject_item(db, subject)


# ---------------------------------------------------------------------------
# PATCH /api/stories/{id}
# ---------------------------------------------------------------------------

def update_story(
    db: DbSession,
    viewer_id: str,
    story_id: str,
    access: str | None = None,
    hidden: bool | None = None,
) -> dict[str, Any]:
    """Change access (teller only) and/or hide (teller, subject, center, admin).

    Hiding is final: hidden=False is refused for everyone (ARCHITECTURE.md "Known limits").

    Every permission is checked before anything changes, so a request that is
    partly refused changes nothing.
    """
    story = _visible_story(db, viewer_id, story_id)
    if access is None and hidden is None:
        raise ValueError("Nothing to change.")
    if access is not None and access not in _SETTABLE_ACCESS:
        raise ValueError("Access can be set to 'private' or 'circle'.")
    if hidden is False:
        raise ValueError("A hidden story cannot be shown again.")

    is_teller = viewer_id == story.teller_id
    if access is not None and not is_teller:
        raise Forbidden(NOT_ALLOWED)
    if hidden is True and not _may_hide(db, viewer_id, story):
        raise Forbidden(NOT_ALLOWED)

    if access is not None:
        story.access = {"type": access, "person_ids": []}
    if hidden is True:
        story.status = StoryStatus.hidden
    db.commit()
    return {"id": story.id, "status": story.status, "access": _access(viewer_id, story)}


# ---------------------------------------------------------------------------
# DELETE /api/links/{id}
# ---------------------------------------------------------------------------

def remove_link(db: DbSession, viewer_id: str, link_id: str) -> dict[str, Any]:
    """Mark a wrong link removed (the row stays). The viewer must see both stories."""
    link = db.get(StoryLink, link_id)
    if link is None:
        raise NotFound(LINK_NOT_FOUND)
    for sid in (link.from_story_id, link.to_story_id):
        s = db.get(Story, sid)
        if s is None or not can_see(db, viewer_id, s):
            raise NotFound(LINK_NOT_FOUND)
    link.status = LinkStatus.removed
    db.commit()
    return {"id": link.id, "status": link.status}
