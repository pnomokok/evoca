"""
Invitation scheduler: the device light at the circle's chat time.

docs/ARCHITECTURE.md A2, "Design principles and rules" and "Background jobs and the demo clock". For each
active circle, once chat_time has passed in the circle's timezone and there is
no Invitation for that local date, exactly one is created for the center:

- status "sent" (the light goes on), or
- status "skipped" when the center already had a session that local day or a
  session is live now: the day is handled and the light stays off.

At most one invitation per circle per local date. The unique index on
(circle_id, date) keeps it so under concurrent passes: the losing insert is
rolled back and skipped.

The reason is built here, in this priority order (the chat agent rephrases it):
1. undelivered reactions on the center's stories
2. waiting family questions
3. waiting follow_up or gap questions
4. a plain invitation to chat
Only questions get_pending_questions would offer count (waiting, not matching a
sensitive topic). The reason names at most a first name: never question text,
story titles or topic words.

run_invitations() is a plain function: the FastAPI lifespan calls it every
minute (server/app.py), tests and the demo CLI call it directly. "Now" is
core.clock.now_utc(), so DEMO_NOW moves the clock:

    DEMO_NOW=2026-10-18T07:05:00+00:00 python -m server.run_invitations
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from core.clock import now_utc
from core.enums import CircleStatus, InvitationStatus, QuestionSource, SessionStart
from core.models import Circle, Invitation, Person, Reaction, Session as OrmSession, Story
from core.services.session_tools import get_pending_questions_data

REASON_REACTION_ONE = "{name} reacted to your story"
REASON_REACTION_MANY = "Your family reacted to your stories"
REASON_FAMILY_QUESTION = "{name} has a question for you"
REASON_AGENT_QUESTION = "I have a question about one of your stories"
REASON_DEFAULT = "Would you like to chat today?"


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _first_name(name: str | None) -> str:
    return (name or "").split()[0] if (name or "").split() else "Your family"


def _has_invitation(db: DbSession, circle_id: str, date: str) -> bool:
    return (
        db.query(Invitation.id)
        .filter(Invitation.circle_id == circle_id, Invitation.date == date)
        .first()
        is not None
    )


def _center_already_talked(db: DbSession, circle: Circle, now: datetime, tz: ZoneInfo) -> bool:
    """True if a session of the center is live now, or one started earlier
    this local day. Panel recordings are family members' own, not the center's."""
    today = now.astimezone(tz).date()
    sessions = (
        db.query(OrmSession)
        .filter(
            OrmSession.circle_id == circle.id,
            OrmSession.started_by != SessionStart.panel_recording,
        )
        .all()
    )
    for sess in sessions:
        if circle.center_person_id not in (sess.participant_ids or []):
            continue
        if sess.ended_at is None:
            return True
        started = _parse_utc(sess.started_at)
        if started.astimezone(tz).date() == today and started <= now:
            return True
    return False


def invitation_reason(db: DbSession, circle: Circle) -> str:
    """The most meaningful thing waiting for the center, as a short sentence."""
    center_id = circle.center_person_id
    reactor_ids = {
        r.person_id
        for r in db.query(Reaction)
        .join(Story, Story.id == Reaction.story_id)
        .filter(
            Story.circle_id == circle.id,
            Story.teller_id == center_id,
            Reaction.delivered_to_center == False,  # noqa: E712
            Reaction.person_id != center_id,
        )
        .all()
    }
    if len(reactor_ids) == 1:
        person = db.get(Person, next(iter(reactor_ids)))
        return REASON_REACTION_ONE.format(name=_first_name(person.name if person else None))
    if reactor_ids:
        return REASON_REACTION_MANY

    # Ordered family -> follow_up -> gap; sensitive-topic matches are left out.
    waiting = get_pending_questions_data(db, center_id, circle.id, limit=1)
    if waiting and waiting[0].source == QuestionSource.family:
        return REASON_FAMILY_QUESTION.format(name=_first_name(waiting[0].asker_name))
    if waiting:
        return REASON_AGENT_QUESTION
    return REASON_DEFAULT


def run_invitations(db: DbSession) -> list[str]:
    """One scheduler pass over every active circle. Commits each invitation
    it creates and returns their ids (sent and skipped)."""
    now = now_utc()
    created: list[str] = []
    circles = db.query(Circle).filter(Circle.status == CircleStatus.active).all()
    for circle in circles:
        tz = ZoneInfo(circle.timezone)
        local = now.astimezone(tz)
        if local.strftime("%H:%M") < circle.chat_time:
            continue
        date = local.strftime("%Y-%m-%d")
        if _has_invitation(db, circle.id, date):
            continue

        skipped = _center_already_talked(db, circle, now, tz)
        inv = Invitation(
            circle_id=circle.id,
            person_id=circle.center_person_id,
            date=date,
            reason=invitation_reason(db, circle),
            status=InvitationStatus.skipped if skipped else InvitationStatus.sent,
        )
        db.add(inv)
        try:
            db.commit()
        except IntegrityError:
            # Another pass created today's invitation first.
            db.rollback()
            continue
        created.append(inv.id)
    return created
