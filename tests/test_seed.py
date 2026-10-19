"""
Tests for the seed safety check in core.seed.

The seed's engine, session factory and init_db are pointed at a temporary
SQLite file, so data/evoca.db is never touched.

Coverage:
  - seeding an empty database works, and re-seeding a seed-only database works
  - a database with a recorded (non-seed) session is refused, with a message
    naming the session, and nothing is deleted
  - --force wipes it anyway
  - a database seeded before the fixed seed session id is still recognised
  - a fresh seed's story ranges play (GET /api/audio, 200) and match the
    segment timings; the range over the private part is refused
  - seed photos: Mulberry and Tailor have photo_url and caption for Elif; the
    pending Workshop (Ayşe only) shows Elif nothing; stored files have no EXIF;
    reseeding leaves no orphan files; a missing photo file does not break it
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.seed as seed
from PIL import Image

from core.services import photos as photo_svc
from core.services.stories import NotFound, build_story
from core.enums import SessionKind, SessionStart
from core.models import (
    Base, Circle, Invitation, Person, Question, Segment, Session as OrmSession, Story, StoryPhoto,
)
from core.services.invitations import invitation_reason


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def seed_db(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'seed_test.db'}")
    Sess = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(seed, "engine", eng)
    monkeypatch.setattr(seed, "SessionLocal", Sess)
    monkeypatch.setattr(seed, "init_db", lambda: Base.metadata.create_all(bind=eng))
    monkeypatch.setattr(seed, "AUDIO_DIR", tmp_path / "audio")   # never the repo's data/audio
    monkeypatch.setattr(photo_svc, "PHOTO_DIR", tmp_path / "photos")   # nor its data/photos
    yield Sess
    eng.dispose()


def _add_recorded_session(Sess) -> str:
    with Sess() as db:
        circle_id = db.query(OrmSession).first().circle_id
        sess = OrmSession(circle_id=circle_id, kind=SessionKind.solo,
                          started_by=SessionStart.spontaneous, participant_ids=[],
                          audio_path=None, started_at="2026-10-15T19:03:12+00:00",
                          ended_at="2026-10-15T19:03:48+00:00")
        db.add(sess)
        db.flush()
        db.add(Segment(session_id=sess.id, speaker_id=None, start_ms=0, end_ms=100,
                       transcript="A real conversation."))
        db.commit()
        return sess.id


def test_seed_empty_database_and_reseed(seed_db):
    assert seed.main([]) == 0
    assert seed.find_recorded_sessions() == []
    assert seed.main([]) == 0  # only the seed's own session exists
    with seed_db() as db:
        assert db.query(OrmSession).count() == 1


def test_seeded_invitation_reason_is_the_schedulers(seed_db):
    """The seeded light's reason is what the scheduler would say for the seed
    state, so the device never mentions a question that does not exist."""
    assert seed.main([]) == 0
    with seed_db() as db:
        circle = db.query(Circle).one()
        invitation = db.query(Invitation).one()
        assert invitation.reason == invitation_reason(db, circle)
        assert db.query(Question).count() == 0
        assert "question" not in invitation.reason


def test_seed_refuses_when_recorded_session_exists(seed_db, capsys):
    seed.main([])
    recorded_id = _add_recorded_session(seed_db)

    assert seed.main([]) == 1
    out = capsys.readouterr().out
    assert "Refusing to seed" in out
    assert recorded_id in out
    assert "(1 segments)" in out
    assert "--force" in out
    with seed_db() as db:
        assert db.get(OrmSession, recorded_id) is not None

    with pytest.raises(seed.SeedRefused):
        seed.reset_and_seed()


def test_seed_force_wipes_recorded_session(seed_db):
    seed.main([])
    recorded_id = _add_recorded_session(seed_db)

    assert seed.main(["--force"]) == 0
    with seed_db() as db:
        assert db.get(OrmSession, recorded_id) is None
        assert db.query(OrmSession).count() == 1


def test_legacy_seed_session_is_still_recognised(seed_db):
    seed.main([])
    with seed_db() as db:   # as seeded before the fixed id: random id, the old m4a path
        sess = db.get(OrmSession, seed.SEED_SESSION_ID)
        legacy = OrmSession(circle_id=sess.circle_id, kind=SessionKind.solo,
                            started_by=SessionStart.spontaneous, participant_ids=[],
                            audio_path=seed.LEGACY_SEED_AUDIO_PATH, started_at=sess.started_at)
        db.add(legacy)
        db.commit()
    assert seed.find_recorded_sessions() == []


@pytest.mark.anyio
async def test_fresh_seed_story_ranges_play(seed_db, tmp_path, monkeypatch):
    seed.main([])
    import server.routers.audio as audio_router
    import server.wav_writer as ww
    from server.app import app
    monkeypatch.setattr(audio_router, "SessionLocal", seed_db)
    monkeypatch.setattr(ww, "_AUDIO_DIR", tmp_path / "audio")

    with seed_db() as db:
        sess = db.get(OrmSession, seed.SEED_SESSION_ID)
        # The file the audio endpoint reads (data/audio/<session_id>.wav, here in tmp_path).
        assert sess.audio_path == (tmp_path / "audio" / f"{sess.id}.wav").as_posix()
        assert Path(sess.audio_path).exists()
        elif_ = db.query(Person).filter(Person.name.startswith("Elif")).one()
        segments = {(s.start_ms, s.end_ms): s for s in
                    db.query(Segment).filter(Segment.session_id == sess.id)}
        stories = db.query(Story).filter(Story.sources != []).all()
        private = next(s for s in segments.values() if s.is_private)
    assert {st.title for st in stories} == {"The Mulberry Tree", "The Tailor's Shop"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for story in stories:
            src = story.sources[0]
            # Each story range is exactly one of Fatma's segments, with word timings inside it.
            seg = segments[(src["start_ms"], src["end_ms"])]
            assert seg.speaker_id == story.teller_id and not seg.is_private
            assert seg.words and seg.words[0]["start_ms"] >= seg.start_ms
            assert seg.words[-1]["end_ms"] <= seg.end_ms
            r = await c.get(f"/api/audio/{src['session_id']}?start={src['start_ms']}&end={src['end_ms']}",
                            headers={"x-person-id": elif_.id})
            assert r.status_code == 200
            with wave.open(io.BytesIO(r.content)) as wf:
                ms = wf.getnframes() * 1000 // wf.getframerate()
            assert abs(ms - (src["end_ms"] - src["start_ms"])) <= 2
        r = await c.get(f"/api/audio/{sess.id}?start={private.start_ms}&end={private.end_ms}",
                        headers={"x-person-id": elif_.id})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Seed photos
# ---------------------------------------------------------------------------

def _people(Sess) -> dict[str, str]:
    with Sess() as db:
        return {p.name.split()[0]: p.id for p in db.query(Person).all()}


def _story_id(Sess, title: str) -> str:
    with Sess() as db:
        return db.query(Story).filter(Story.title == title).one().id


def test_seeded_stories_have_their_photos(seed_db):
    assert seed.main([]) == 0
    people = _people(seed_db)
    with seed_db() as db:
        mulberry = build_story(db, people["Elif"], _story_id(seed_db, "The Mulberry Tree"))
        tailor = build_story(db, people["Elif"], _story_id(seed_db, "The Tailor's Shop"))
        workshop_id = _story_id(seed_db, "Father's Workshop")
        assert mulberry["photo_url"] and mulberry["photo_caption"] == "Mom in the village garden, around 1956"
        assert tailor["photo_url"] and tailor["photo_caption"] == "Mom at the tailor's shop, late 1960s"
        # The pending Workshop is for Ayşe only: Elif sees neither the story nor its photo.
        with pytest.raises(NotFound):
            build_story(db, people["Elif"], workshop_id)
        workshop = build_story(db, people["Ayşe"], workshop_id)
        assert workshop["photo_caption"] == "Her father's workshop, 1950s"
        photo_id = workshop["photo_url"].rsplit("/", 1)[-1]
        with pytest.raises(NotFound):
            photo_svc.photo_file(db, people["Elif"], photo_id)


def test_seed_photo_files_have_no_metadata(seed_db, tmp_path):
    assert seed.main([]) == 0
    files = sorted((tmp_path / "photos").iterdir())
    assert len(files) == 3
    for f in files:
        with Image.open(f) as im:
            assert im.format == "JPEG"
            assert not im.getexif() and "exif" not in im.info and "icc_profile" not in im.info
            assert max(im.size) <= photo_svc.MAX_SIDE


def test_reseeding_leaves_no_orphan_photo_files(seed_db, tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "left-from-an-old-database.jpg").write_bytes(b"old")
    keep_outside = tmp_path / "not-a-photo.jpg"
    keep_outside.write_bytes(b"other directory")
    assert seed.main([]) == 0
    assert seed.main([]) == 0
    with seed_db() as db:
        referenced = {Path(p.path).name for p in db.query(StoryPhoto).all()}
    assert {f.name for f in photos.iterdir()} == referenced and len(referenced) == 3
    assert keep_outside.exists()


def test_a_missing_seed_photo_is_skipped(seed_db, tmp_path, monkeypatch, caplog):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "mulberry.jpg").write_bytes((seed.SEED_PHOTOS_DIR / "mulberry.jpg").read_bytes())
    monkeypatch.setattr(seed, "SEED_PHOTOS_DIR", assets)
    assert seed.main([]) == 0
    assert "tailor.jpg is missing" in caplog.text
    with seed_db() as db:
        assert db.query(StoryPhoto).count() == 1


def test_seed_never_deletes_in_the_default_photos_folder(seed_db, tmp_path, monkeypatch, caplog):
    """data/photos belongs to the default database: orphans there are logged, never deleted."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(photo_svc, "PHOTO_DIR", Path("data") / "photos")
    keep = Path("data/photos/uploaded-under-evoca-db.jpg")
    keep.parent.mkdir(parents=True)
    keep.write_bytes(b"a real upload")
    assert seed.main([]) == 0
    assert keep.exists()
    assert "belong to no story; kept" in caplog.text
