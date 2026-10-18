"""
Demo seed data — run with:

    python -m core.seed            # refuses if the database holds real sessions
    python -m core.seed --force    # wipe anyway

Resets the database and creates the Yilmaz family demo fixtures described in
docs/ARCHITECTURE.md.  All text is English.

Safety: the seed deletes the whole database. It refuses to run when the
database contains any Session the seed did not create (recognised by the
seed session's fixed id), unless --force is passed.

Audio: the seed session's audio and segment timings come from
core/seed_assets/ (made once with Polly by scripts/make_seed_audio.py). The
WAV is copied to data/audio/<session_id>.wav, relative to the working
directory, which is where the audio endpoint reads it; run the seed from the
same directory as the backend. No AWS call is made here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow running as __main__ from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.clock import now_utc
from sqlalchemy import func, inspect

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
    Reaction,
    Segment,
    Session,
    SensitiveTopic,
    Story,
    StoryLink,
    StorySubject,
)
from core.services.invitations import invitation_reason

_CIRCLE_TZ = ZoneInfo("Europe/Istanbul")

# The session the seed creates has a fixed id, so the seed can tell seeded
# data from real recordings. Databases seeded before it had this audio_path.
SEED_SESSION_ID = "00000000-5eed-4000-8000-000000000001"
LEGACY_SEED_AUDIO_PATH = "data/audio/session_demo.m4a"

SEED_ASSETS = Path(__file__).parent / "seed_assets"
# Where the backend's audio endpoint reads session audio (server/wav_writer.py).
AUDIO_DIR = Path("data") / "audio"


class SeedRefused(RuntimeError):
    """Raised when seeding would delete sessions the seed did not create."""


def find_recorded_sessions() -> list[tuple[str, str, int]]:
    """Return (session_id, started_at, segment_count) for every non-seed Session."""
    if not inspect(engine).has_table(Session.__tablename__):
        return []
    with SessionLocal() as db:
        rows = (
            db.query(Session.id, Session.started_at, func.count(Segment.id))
            .outerjoin(Segment, Segment.session_id == Session.id)
            .filter(Session.id != SEED_SESSION_ID)
            .filter((Session.audio_path.is_(None)) | (Session.audio_path != LEGACY_SEED_AUDIO_PATH))
            .group_by(Session.id)
            .order_by(Session.started_at)
            .all()
        )
    return [(r[0], r[1], r[2]) for r in rows]


def _refusal_message(recorded: list[tuple[str, str, int]]) -> str:
    lines = [
        f"Refusing to seed: {engine.url.database} contains {len(recorded)} session(s) "
        f"that the seed did not create:",
    ]
    for session_id, started_at, segments in recorded:
        lines.append(f"  - {session_id}  started {started_at}  ({segments} segments)")
    lines += [
        "Seeding deletes the whole database: these conversations, and every story,",
        "question, answer and reaction made from them, would be lost.",
        "Back up the file first, or run with --force to wipe it anyway.",
    ]
    return "\n".join(lines)


def reset_and_seed(force: bool = False) -> None:
    recorded = find_recorded_sessions()
    if recorded and not force:
        raise SeedRefused(_refusal_message(recorded))

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
            is_demo=True,
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
        # Session  (finished, from ~2 hours ago) with its audio
        # ------------------------------------------------------------------
        session_start = now - timedelta(hours=2)
        session_end   = now - timedelta(hours=1, minutes=30)

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        audio_path = AUDIO_DIR / f"{SEED_SESSION_ID}.wav"
        shutil.copyfile(SEED_ASSETS / "seed_session.wav", audio_path)

        session = Session(
            id=SEED_SESSION_ID,
            circle_id=circle.id,
            kind=SessionKind.solo,
            started_by=SessionStart.spontaneous,
            participant_ids=[fatma.id],
            audio_path=audio_path.as_posix(),
            started_at=session_start.isoformat(),
            ended_at=session_end.isoformat(),
        )
        db.add(session)
        db.flush()

        # ------------------------------------------------------------------
        # Segments: Fatma and the agent, timings from the audio (Polly speech marks).
        # The Hatice part is private: it never reaches any story's sources or summary.
        # ------------------------------------------------------------------
        timings = json.loads((SEED_ASSETS / "seed_session.json").read_text(encoding="utf-8"))
        segments = [
            Segment(
                session_id=session.id,
                speaker_id=fatma.id if seg["speaker"] == "center" else None,  # None = agent
                start_ms=seg["start_ms"],
                end_ms=seg["end_ms"],
                transcript=seg["transcript"],
                words=seg["words"],
                is_private=seg["is_private"],
            )
            for seg in timings["segments"]
        ]
        db.add_all(segments)
        db.flush()
        seg_mulberry, seg_tailor = segments[0], segments[4]
        for seg in (seg_mulberry, seg_tailor):
            # A story source must be Fatma's own words, never the private part.
            if seg.is_private or seg.speaker_id != fatma.id:
                raise RuntimeError("seed_session.json changed: a story source is private or not Fatma's")

        # ------------------------------------------------------------------
        # Stories
        # Note: the Hatice segment is private; no story is derived from it.
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
            sources=[{"session_id": session.id, "start_ms": seg_mulberry.start_ms,
                      "end_ms": seg_mulberry.end_ms}],
            place="Village of Akcaabat",
            stated_year=None,
            access={"type": AccessType.circle, "person_ids": []},
            status=StoryStatus.published,
            publish_at=(now - timedelta(hours=1)).isoformat(),
            created_at=(now - timedelta(hours=1, minutes=55)).isoformat(),
        )

        # 2. Published, access = circle — youth memory (tailor's shop)
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
            sources=[{"session_id": session.id, "start_ms": seg_tailor.start_ms,
                      "end_ms": seg_tailor.end_ms}],
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
        # Invitation for today: its reason comes from the scheduler's own
        # function, so it matches whatever the seed above leaves waiting.
        # ------------------------------------------------------------------
        invitation = Invitation(
            circle_id=circle.id,
            person_id=fatma.id,
            date=today_str,
            reason=invitation_reason(db, circle),
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
    print(f"  Audio   : {audio_path.as_posix()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset the database and load the demo family.")
    parser.add_argument("--force", action="store_true",
                        help="wipe the database even if it holds recorded sessions")
    args = parser.parse_args(argv)
    try:
        reset_and_seed(force=args.force)
    except SeedRefused as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
