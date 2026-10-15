"""
Demo seed data — run with:

    python -m core.seed

Resets the database and creates the Yilmaz family demo fixtures described in
docs/PROJECT.md.  All text is English.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow running as __main__ from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.clock import now_utc
from core.db import SessionLocal, engine, init_db
from core.enums import (
    AccessType,
    CircleStatus,
    Emoji,
    InvitationStatus,
    LifePeriod,
    LinkReason,
    LinkSource,
    LinkStatus,
    PeriodSource,
    QuestionSource,
    QuestionStatus,
    Role,
    SessionKind,
    SessionStart,
    StoryKind,
    StoryStatus,
)
from core.models import (
    Base,
    Circle,
    Invitation,
    Membership,
    Person,
    Question,
    Reaction,
    Segment,
    Session,
    SensitiveTopic,
    Story,
    StoryLink,
    StorySubject,
)

_CIRCLE_TZ = ZoneInfo("Europe/Istanbul")


def reset_and_seed() -> None:
    # Drop all tables and recreate them (clean slate).
    Base.metadata.drop_all(bind=engine)
    init_db()

    now = now_utc()
    today_str = now.astimezone(_CIRCLE_TZ).strftime("%Y-%m-%d")

    with SessionLocal() as db:
        # ------------------------------------------------------------------
        # People
        # ------------------------------------------------------------------
        fatma = Person(
            name="Fatma Yilmaz",
            birth_year=1948,
            language="en",
            created_at=now.isoformat(),
        )
        ayse = Person(
            name="Ayşe Yilmaz",
            birth_year=1975,
            language="en",
            created_at=now.isoformat(),
        )
        elif_ = Person(
            name="Elif Yilmaz",
            birth_year=2003,
            language="en",
            created_at=now.isoformat(),
        )
        can = Person(
            name="Can Yilmaz",
            birth_year=2006,
            language="en",
            created_at=now.isoformat(),
        )
        db.add_all([fatma, ayse, elif_, can])
        db.flush()

        # ------------------------------------------------------------------
        # Circle
        # ------------------------------------------------------------------
        circle = Circle(
            name="The Yilmaz Family",
            center_person_id=fatma.id,
            status=CircleStatus.active,
            chat_time="10:00",
            timezone="Europe/Istanbul",
        )
        db.add(circle)
        db.flush()

        # ------------------------------------------------------------------
        # Memberships
        # ------------------------------------------------------------------
        db.add_all([
            Membership(
                person_id=fatma.id, circle_id=circle.id,
                role=Role.center, relation_to_center=None,
            ),
            Membership(
                person_id=ayse.id, circle_id=circle.id,
                role=Role.admin, relation_to_center="daughter",
            ),
            Membership(
                person_id=elif_.id, circle_id=circle.id,
                role=Role.member, relation_to_center="granddaughter",
            ),
            Membership(
                person_id=can.id, circle_id=circle.id,
                role=Role.member, relation_to_center="grandson",
            ),
        ])
        db.flush()

        # ------------------------------------------------------------------
        # Session  (finished, from ~2 hours ago)
        # ------------------------------------------------------------------
        session_start = now - timedelta(hours=2)
        session_end   = now - timedelta(hours=1, minutes=30)

        session = Session(
            circle_id=circle.id,
            kind=SessionKind.solo,
            started_by=SessionStart.spontaneous,
            participant_ids=[fatma.id],
            audio_path="data/audio/session_demo.m4a",
            started_at=session_start.isoformat(),
            ended_at=session_end.isoformat(),
        )
        db.add(session)
        db.flush()

        # ------------------------------------------------------------------
        # Segments
        # ------------------------------------------------------------------
        seg1 = Segment(
            session_id=session.id,
            speaker_id=fatma.id,
            start_ms=0,
            end_ms=45_000,
            transcript=(
                "When I was a little girl in the village, we had a big mulberry tree "
                "in the garden. Every summer we would climb it and eat until our hands "
                "turned purple."
            ),
            words=[
                {"w": "When", "start_ms": 0,   "end_ms": 400},
                {"w": "I",    "start_ms": 410,  "end_ms": 500},
            ],
            is_private=False,
        )
        seg2 = Segment(
            session_id=session.id,
            speaker_id=None,  # agent
            start_ms=45_500,
            end_ms=52_000,
            transcript="That sounds wonderful. Did you have siblings to climb with?",
            words=[],
            is_private=False,
        )
        # This segment is private — it never reaches any story's sources or summary.
        seg3 = Segment(
            session_id=session.id,
            speaker_id=fatma.id,
            start_ms=52_500,
            end_ms=95_000,
            transcript=(
                "Yes, my sister Hatice and I. We were inseparable. "
                "She moved to Germany in 1972 — I did not see her for three years. "
                "Those were hard times, but let us not talk about that today."
            ),
            words=[{"w": "Yes", "start_ms": 52_500, "end_ms": 52_900}],
            is_private=True,
        )
        db.add_all([seg1, seg2, seg3])
        db.flush()

        # ------------------------------------------------------------------
        # Stories
        # Note: seg3 is private; no story is derived from it.
        # ------------------------------------------------------------------

        # 1. Published, access = circle — childhood memory
        story_mulberry = Story(
            circle_id=circle.id,
            teller_id=fatma.id,
            kind=StoryKind.original,
            original_story_id=None,
            title="The Mulberry Tree",
            ai_summary=(
                "Fatma recalls climbing the mulberry tree with her sister every summer "
                "as a child in their village garden."
            ),
            sources=[{"session_id": session.id, "start_ms": 0, "end_ms": 45_000}],
            place="Village of Akcaabat",
            stated_year=None,
            access={"type": AccessType.circle, "person_ids": []},
            status=StoryStatus.published,
            publish_at=(now - timedelta(hours=1)).isoformat(),
            created_at=(now - timedelta(hours=1, minutes=55)).isoformat(),
        )

        # 2. Published, access = circle — youth memory (tailor's shop)
        #    Sources point to seg1's session but a later time range to keep
        #    it cleanly separate from the mulberry extract.
        story_tailor = Story(
            circle_id=circle.id,
            teller_id=fatma.id,
            kind=StoryKind.original,
            original_story_id=None,
            title="The Tailor's Shop",
            ai_summary=(
                "As a young woman Fatma worked at the neighbourhood tailor's shop. "
                "She learned to sew by hand and remembers the hum of the old Singer "
                "machine and the smell of fresh cotton on warm afternoons."
            ),
            sources=[{"session_id": session.id, "start_ms": 45_500, "end_ms": 52_000}],
            place="Village of Akcaabat",
            stated_year=None,
            access={"type": AccessType.circle, "person_ids": []},
            status=StoryStatus.published,
            publish_at=(now - timedelta(hours=1)).isoformat(),
            created_at=(now - timedelta(hours=1, minutes=45)).isoformat(),
        )

        # 3. Pending, access = selected (Ayşe only)
        story_pending = Story(
            circle_id=circle.id,
            teller_id=fatma.id,
            kind=StoryKind.original,
            original_story_id=None,
            title="Father's Workshop",
            ai_summary=(
                "Fatma describes her father's carpentry workshop and the smell of "
                "fresh sawdust that she still associates with safety."
            ),
            sources=[],
            place=None,
            stated_year=None,
            access={"type": AccessType.selected, "person_ids": [ayse.id]},
            status=StoryStatus.pending,
            publish_at=(now + timedelta(hours=23)).isoformat(),
            created_at=(now - timedelta(minutes=30)).isoformat(),
        )

        db.add_all([story_mulberry, story_tailor, story_pending])
        db.flush()

        # ------------------------------------------------------------------
        # StorySubjects
        # ------------------------------------------------------------------
        db.add_all([
            StorySubject(
                story_id=story_mulberry.id,
                person_id=fatma.id,
                period=LifePeriod.childhood,
                period_source=PeriodSource.ai,
                corrected_by=None,
            ),
            StorySubject(
                story_id=story_tailor.id,
                person_id=fatma.id,
                period=LifePeriod.youth,
                period_source=PeriodSource.ai,
                corrected_by=None,
            ),
            StorySubject(
                story_id=story_pending.id,
                person_id=fatma.id,
                period=LifePeriod.childhood,
                period_source=PeriodSource.ai,
                corrected_by=None,
            ),
        ])
        db.flush()

        # ------------------------------------------------------------------
        # StoryLink  (tailor → mulberry, same place)
        # ------------------------------------------------------------------
        link = StoryLink(
            from_story_id=story_tailor.id,
            to_story_id=story_mulberry.id,
            reason=LinkReason.same_place,
            source=LinkSource.ai,
            status=LinkStatus.suggested,
        )
        db.add(link)
        db.flush()

        # ------------------------------------------------------------------
        # Questions  (from Elif to Fatma)
        # ------------------------------------------------------------------
        q1 = Question(
            circle_id=circle.id,
            target_person_id=fatma.id,
            asker_id=elif_.id,
            text="Grandma, what was school like when you were young?",
            source=QuestionSource.family,
            period=LifePeriod.childhood,
            status=QuestionStatus.waiting,
            answer=None,
            created_at=(now - timedelta(days=1)).isoformat(),
        )
        q2 = Question(
            circle_id=circle.id,
            target_person_id=fatma.id,
            asker_id=elif_.id,
            text="Did you ever meet anyone famous growing up?",
            source=QuestionSource.family,
            period=None,
            status=QuestionStatus.waiting,
            answer=None,
            created_at=(now - timedelta(hours=3)).isoformat(),
        )
        db.add_all([q1, q2])
        db.flush()

        # ------------------------------------------------------------------
        # SensitiveTopic
        # ------------------------------------------------------------------
        sensitive = SensitiveTopic(
            circle_id=circle.id,
            text="1972 separation from Hatice",
            added_by=ayse.id,
            created_at=(now - timedelta(days=2)).isoformat(),
        )
        db.add(sensitive)
        db.flush()

        # ------------------------------------------------------------------
        # Reaction  (Elif reacts to mulberry story)
        # ------------------------------------------------------------------
        reaction = Reaction(
            story_id=story_mulberry.id,
            person_id=elif_.id,
            emoji=Emoji.laugh,
            delivered_to_center=False,
            created_at=(now - timedelta(minutes=10)).isoformat(),
        )
        db.add(reaction)
        db.flush()

        # ------------------------------------------------------------------
        # Invitation for today
        # ------------------------------------------------------------------
        invitation = Invitation(
            circle_id=circle.id,
            person_id=fatma.id,
            date=today_str,
            reason="Elif has a question for you.",
            status=InvitationStatus.sent,
        )
        db.add(invitation)

        db.commit()

    print("Seed complete.")
    print("  Circle  : The Yilmaz Family")
    print("  People  : Fatma (center), Ayşe (admin), Elif (member), Can (member)")
    print(f"  Stories : {story_mulberry.title!r}, {story_tailor.title!r}, {story_pending.title!r}")
    print(f"  Today   : {today_str} (circle timezone: Europe/Istanbul)")
    print(f"  Database: {os.environ.get('EVOCA_DB_PATH', 'data/evoca.db')}")


if __name__ == "__main__":
    reset_and_seed()
