"""
Business logic for the archivist-agent MCP tools.

All functions are pure (no MCP imports) and receive an open SQLAlchemy session
plus explicit viewer_id / circle_id so they can be called from tests without
an MCP context.

Tool table from docs/PROJECT.md:
  get_session_transcript   — non-private segments + asked questions
  save_story               — new pending story with subjects and sources
  record_answer            — flip an asked (or never-asked family) question to "answered"
  add_question             — follow_up / gap question for the center person
  mark_question_declined   — the center declined to answer: "asked" -> "declined"
  reopen_question          — asked but not answered: "asked" -> "waiting"
  add_refused_topic        — the center refused a topic: a SensitiveTopic with source "speaker"
  link_stories             — an ai-suggested link from a story of this session to a related one
  find_gaps                — life periods of the center with no story yet
  merge_stories            — one memory saved as several stories in one run becomes one story
  extend_session_answers   — repair: answers of a session cover their whole story (see merge_stories)

Private segments (is_private = True) never appear in any output here, and no
story source or answer range may overlap one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.clock import now_utc
from core.access import can_see
from core.enums import (
    AccessType,
    LifePeriod,
    LinkReason,
    LinkSource,
    LinkStatus,
    PeriodSource,
    QuestionSource,
    QuestionStatus,
    SessionStart,
    StoryKind,
    StoryStatus,
    TopicSource,
)
from core.models import (
    Circle,
    Membership,
    Person,
    Question,
    Segment,
    SensitiveTopic,
    Session as OrmSession,
    Story,
    Reaction,
    StoryLink,
    StoryPhoto,
    StorySubject,
)
from core.services.session_tools import _matches_sensitive_topic, _meaningful_words

_MAX_TOPIC_CHARS = 200

_PUBLISH_DELAY = timedelta(hours=24)
_VALID_PERIODS = {p.value for p in LifePeriod}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_session_in_circle(db: DbSession, session_id: str, circle_id: str) -> OrmSession:
    sess: OrmSession | None = db.get(OrmSession, session_id)
    if sess is None or sess.circle_id != circle_id:
        raise ValueError(f"Session '{session_id}' not found in this circle.")
    return sess


def _require_circle_member(db: DbSession, person_id: str, circle_id: str, label: str) -> None:
    m = (
        db.query(Membership)
        .filter(Membership.person_id == person_id, Membership.circle_id == circle_id)
        .first()
    )
    if m is None:
        raise ValueError(f"{label} '{person_id}' is not a member of this circle.")


def _overlaps_private(db: DbSession, session_id: str, start_ms: int, end_ms: int) -> bool:
    """True if [start_ms, end_ms) overlaps any private segment of the session.

    Ranges that only touch a private segment's boundary do not overlap.
    """
    hit = (
        db.query(Segment.id)
        .filter(
            Segment.session_id == session_id,
            Segment.is_private == True,  # noqa: E712
            Segment.start_ms < end_ms,
            Segment.end_ms > start_ms,
        )
        .first()
    )
    return hit is not None


def _check_range(db: DbSession, session_id: str, start_ms: int, end_ms: int) -> None:
    """Validate an audio range: ordered and clear of private segments."""
    if start_ms >= end_ms:
        raise ValueError(
            f"Invalid range {start_ms}-{end_ms} ms: start_ms must be less than end_ms."
        )
    if _overlaps_private(db, session_id, start_ms, end_ms):
        # Never name the private segment or its text; only the rejected range.
        raise ValueError(
            f"Range {start_ms}-{end_ms} ms in session '{session_id}' overlaps a private "
            f"part of the session. Use only ranges of the segments you were given."
        )


def _person_name_and_relation(
    db: DbSession, person_id: str | None, circle_id: str
) -> tuple[str | None, str | None]:
    if not person_id:
        return None, None
    p = db.get(Person, person_id)
    m = (
        db.query(Membership)
        .filter(Membership.person_id == person_id, Membership.circle_id == circle_id)
        .first()
    )
    return (p.name if p else None), (m.relation_to_center if m else None)


# ---------------------------------------------------------------------------
# get_session_transcript
# ---------------------------------------------------------------------------

@dataclass
class TranscriptSegmentItem:
    segment_id: str
    speaker_id: str | None          # None = agent
    speaker_name: str | None        # None = agent
    start_ms: int
    end_ms: int
    transcript: str
    words: list[dict[str, Any]]


@dataclass
class AskedQuestionItem:
    question_id: str
    text: str
    asker_name: str | None
    asker_relation_to_center: str | None


@dataclass
class SessionTranscriptResult:
    session_id: str
    started_at: str
    segments: list[TranscriptSegmentItem]
    asked_questions: list[AskedQuestionItem]


def get_session_transcript_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    session_id: str,
) -> SessionTranscriptResult:
    """Return the session's non-private segments in order, plus asked questions.

    Private segments are excluded at the query level, so not even their ids
    leave this function.
    """
    sess = _require_session_in_circle(db, session_id, circle_id)

    rows = (
        db.query(Segment)
        .filter(
            Segment.session_id == session_id,
            Segment.is_private == False,  # noqa: E712
        )
        .order_by(Segment.start_ms)
        .all()
    )

    segments: list[TranscriptSegmentItem] = []
    for s in rows:
        name, _ = _person_name_and_relation(db, s.speaker_id, circle_id)
        segments.append(
            TranscriptSegmentItem(
                segment_id=s.id,
                speaker_id=s.speaker_id,
                speaker_name=name,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                transcript=s.transcript,
                words=list(s.words or []),
            )
        )

    asked = (
        db.query(Question)
        .filter(
            Question.circle_id == circle_id,
            Question.status == QuestionStatus.asked,
        )
        .order_by(Question.created_at)
        .all()
    )
    asked_items: list[AskedQuestionItem] = []
    for q in asked:
        name, relation = _person_name_and_relation(db, q.asker_id, circle_id)
        asked_items.append(
            AskedQuestionItem(
                question_id=q.id,
                text=q.text,
                asker_name=name,
                asker_relation_to_center=relation,
            )
        )

    return SessionTranscriptResult(
        session_id=sess.id,
        started_at=sess.started_at,
        segments=segments,
        asked_questions=asked_items,
    )


# ---------------------------------------------------------------------------
# save_story
# ---------------------------------------------------------------------------

def save_story_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    title: str,
    summary: str,
    teller_id: str,
    subjects: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    place: str | None = None,
    stated_year: int | None = None,
    original_story_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Create a pending Story with its StorySubjects and return its id.

    Raises ValueError if any person, period, session, range or original story
    is invalid, or if a source range overlaps a private segment. With
    session_id (the X-Evoca-Session-Id header of the archivist's connection),
    every source must be in that session: a story never borrows the audio of
    another session, e.g. of a private story found with search_archive. The
    original story must be one the viewer can see.
    """
    if not title or not title.strip():
        raise ValueError("title must not be empty.")

    _require_circle_member(db, teller_id, circle_id, "Teller")

    seen: set[str] = set()
    for subj in subjects:
        pid = subj.get("person_id")
        period = subj.get("period")
        if not pid:
            raise ValueError("Every subject needs a person_id.")
        if pid in seen:
            raise ValueError(f"Subject '{pid}' is listed more than once.")
        seen.add(pid)
        _require_circle_member(db, pid, circle_id, "Subject")
        if period not in _VALID_PERIODS:
            raise ValueError(
                f"Invalid period '{period}'. Use one of: {', '.join(sorted(_VALID_PERIODS))}."
            )

    if not sources:
        raise ValueError("A story needs at least one source range.")
    clean_sources: list[dict[str, Any]] = []
    for src in sources:
        sid = src.get("session_id")
        start_ms, end_ms = src.get("start_ms"), src.get("end_ms")
        if not isinstance(start_ms, int) or not isinstance(end_ms, int):
            raise ValueError("Every source needs integer start_ms and end_ms.")
        if session_id and sid != session_id:
            raise ValueError("Sources must be ranges of the session being archived.")
        _require_session_in_circle(db, sid, circle_id)
        _check_range(db, sid, start_ms, end_ms)
        clean_sources.append({"session_id": sid, "start_ms": start_ms, "end_ms": end_ms})

    if original_story_id is not None:
        original: Story | None = db.get(Story, original_story_id)
        if original is None or original.circle_id != circle_id or not can_see(db, viewer_id, original):
            raise ValueError(f"Original story '{original_story_id}' not found in this circle.")

    now = now_utc()
    story = Story(
        circle_id=circle_id,
        teller_id=teller_id,
        kind=StoryKind.retelling if original_story_id else StoryKind.original,
        original_story_id=original_story_id,
        title=title.strip(),
        ai_summary=summary,
        sources=clean_sources,
        place=place,
        stated_year=stated_year,
        access={"type": AccessType.circle.value, "person_ids": []},
        status=StoryStatus.pending,
        publish_at=(now + _PUBLISH_DELAY).isoformat(),
        created_at=now.isoformat(),
    )
    db.add(story)
    db.flush()

    for subj in subjects:
        db.add(
            StorySubject(
                story_id=story.id,
                person_id=subj["person_id"],
                period=subj["period"],
                period_source=PeriodSource.ai,
                corrected_by=None,
            )
        )
    db.flush()
    return story.id


# ---------------------------------------------------------------------------
# record_answer
# ---------------------------------------------------------------------------

def record_answer_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    question_id: str,
    story_id: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    """Mark a question as answered by a range of a story's session.

    The question must be asked, or a waiting family question that was never
    asked (the speaker sometimes answers it on her own; the archivist's checker
    confirms the answer first). Follow-up and gap questions must be asked.
    The session is taken from the story's first source. The answer range is
    checked against private segments so a private range never reaches the asker.
    """
    q: Question | None = db.get(Question, question_id)
    if q is None or q.circle_id != circle_id:
        raise ValueError(f"Question '{question_id}' not found in this circle.")
    unasked_family = q.status == QuestionStatus.waiting and q.source == QuestionSource.family
    if q.status != QuestionStatus.asked and not unasked_family:
        raise ValueError(
            f"Question '{question_id}' has status '{q.status}', expected 'asked' "
            f"(or a waiting family question)."
        )
    if unasked_family:
        circle: Circle | None = db.get(Circle, circle_id)
        topics = db.query(SensitiveTopic).filter(SensitiveTopic.circle_id == circle_id).all()
        if (circle is None or q.target_person_id != circle.center_person_id
                or any(_matches_sensitive_topic(q.text, t.text) for t in topics)):
            # Same message as a missing question: a sensitive match is never revealed.
            raise ValueError(f"Question '{question_id}' not found in this circle.")

    story: Story | None = db.get(Story, story_id)
    if story is None or story.circle_id != circle_id:
        raise ValueError(f"Story '{story_id}' not found in this circle.")
    if not story.sources:
        raise ValueError(f"Story '{story_id}' has no sources to answer from.")

    session_id = story.sources[0]["session_id"]
    _check_range(db, session_id, start_ms, end_ms)

    answer = {
        "story_id": story_id,
        "session_id": session_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
    }
    q.status = QuestionStatus.answered
    q.answer = answer
    db.flush()
    return answer


# ---------------------------------------------------------------------------
# merge_stories
# ---------------------------------------------------------------------------

def _merged_ranges(ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sorted ranges per session, with overlapping or touching ones joined."""
    out: list[dict[str, Any]] = []
    for r in sorted(ranges, key=lambda r: (r["session_id"], r["start_ms"], r["end_ms"])):
        last = out[-1] if out else None
        if last and last["session_id"] == r["session_id"] and r["start_ms"] <= last["end_ms"]:
            last["end_ms"] = max(last["end_ms"], r["end_ms"])
        else:
            out.append(dict(r))
    return out


def merge_stories_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    session_id: str,
    story_ids: list[str],
    title: str,
    summary: str,
) -> dict[str, Any]:
    """Merge stories saved as parts of one memory into the first one.

    Called by the archivist's own code (never the model) after a run, for
    stories its split guard flagged. Every story must be pending, told by the
    same person and sourced only from session_id (the X-Evoca-Session-Id
    header): only stories just saved from the session being archived can be
    merged. The survivor gets the union of the sources, the first stated_year
    (and place) any part has, every subject (the survivor's period wins for a
    person in both), and the new title and summary. Answers, links, photos,
    reactions and retellings that point at a merged story move to the
    survivor; the merged stories are deleted. Returns {story_id, merged_ids}.
    """
    if not title or not title.strip():
        raise ValueError("title must not be empty.")
    ids = list(dict.fromkeys(story_ids or []))
    if len(ids) < 2:
        raise ValueError("Merging needs at least two stories.")
    if not session_id:
        raise ValueError("No session: only stories of the session being archived can be merged.")

    stories: list[Story] = []
    for sid in ids:
        story: Story | None = db.get(Story, sid)
        if story is None or story.circle_id != circle_id:
            raise ValueError(f"Story '{sid}' not found in this circle.")
        if story.status != StoryStatus.pending:
            raise ValueError(f"Story '{sid}' is not pending; only just-saved stories can be merged.")
        if not story.sources or any(src.get("session_id") != session_id for src in story.sources):
            raise ValueError(f"Story '{sid}' is not from the session being archived.")
        stories.append(story)
    survivor, others = stories[0], stories[1:]
    if any(s.teller_id != survivor.teller_id for s in others):
        raise ValueError("Only stories by the same teller can be merged.")

    sources = _merged_ranges([src for s in stories for src in s.sources])
    for src in sources:
        _check_range(db, src["session_id"], src["start_ms"], src["end_ms"])

    other_ids = [s.id for s in others]
    have = {s.person_id for s in db.query(StorySubject).filter(StorySubject.story_id == survivor.id)}
    for subj in db.query(StorySubject).filter(StorySubject.story_id.in_(other_ids)).all():
        if subj.person_id not in have:
            db.add(StorySubject(story_id=survivor.id, person_id=subj.person_id, period=subj.period,
                                period_source=subj.period_source, corrected_by=subj.corrected_by))
            have.add(subj.person_id)
        db.delete(subj)

    for q in db.query(Question).filter(Question.circle_id == circle_id).all():
        if q.answer and q.answer.get("story_id") in other_ids:
            q.answer = {**q.answer, "story_id": survivor.id}
    answered = [q for q in db.query(Question).filter(Question.circle_id == circle_id).all()
                if q.answer and q.answer.get("story_id") == survivor.id]

    seen_links: set[tuple[str, str, str]] = set()
    links = db.query(StoryLink).filter(
        StoryLink.from_story_id.in_(ids) | StoryLink.to_story_id.in_(ids)
    ).all()
    for link in sorted(links, key=lambda link: link.from_story_id != survivor.id):
        frm = survivor.id if link.from_story_id in other_ids else link.from_story_id
        to = survivor.id if link.to_story_id in other_ids else link.to_story_id
        key = (frm, to, link.reason)
        if frm == to or key in seen_links:
            db.delete(link)
            continue
        seen_links.add(key)
        link.from_story_id, link.to_story_id = frm, to

    for photo in db.query(StoryPhoto).filter(StoryPhoto.story_id.in_(other_ids)).all():
        photo.story_id = survivor.id
    reacted = {(r.person_id, r.emoji) for r in db.query(Reaction).filter(Reaction.story_id == survivor.id)}
    for r in db.query(Reaction).filter(Reaction.story_id.in_(other_ids)).all():
        if (r.person_id, r.emoji) not in reacted:
            db.add(Reaction(story_id=survivor.id, person_id=r.person_id, emoji=r.emoji,
                            delivered_to_center=r.delivered_to_center, created_at=r.created_at))
            reacted.add((r.person_id, r.emoji))
        db.delete(r)
    for retelling in db.query(Story).filter(Story.original_story_id.in_(other_ids)).all():
        retelling.original_story_id = survivor.id

    survivor.sources = sources
    survivor.title = title.strip()
    survivor.ai_summary = summary
    if survivor.stated_year is None:
        survivor.stated_year = next((s.stated_year for s in others if s.stated_year is not None), None)
    if survivor.place is None:
        survivor.place = next((s.place for s in others if s.place), None)
    for q in answered:
        _extend_answer(db, q, survivor)
    db.flush()
    for s in others:
        db.delete(s)
    db.flush()
    return {"story_id": survivor.id, "merged_ids": other_ids}


def _extend_answer(db: DbSession, q: Question, story: Story) -> None:
    """Widen q's answer range over the story's neighbouring pieces in its session.

    The checker confirms one range of the answer, but the speaker's answer
    often goes on in later segments that end up in the same story (or in a
    part merged into it). The range grows piece by piece, and only across a
    gap that holds nothing but the agent's turns: any speech left out of the
    story (another story, a refused topic) or any private segment stops it,
    because GET /api/audio lets the asker hear every part of the answer range.
    """
    ans = q.answer or {}
    session_id = ans.get("session_id")
    start, end = ans.get("start_ms"), ans.get("end_ms")
    srcs = sorted((src for src in story.sources or [] if src.get("session_id") == session_id),
                  key=lambda src: src["start_ms"])
    if not srcs or start is None or end is None or _overlaps_private(db, session_id, start, end):
        return
    for src in srcs:                                  # forwards
        if src["end_ms"] <= end:
            continue
        if src["start_ms"] > end and not _agent_only_gap(db, session_id, end, src["start_ms"]):
            break
        end = src["end_ms"]
    for src in reversed(srcs):                        # backwards
        if src["start_ms"] >= start:
            continue
        if src["end_ms"] < start and not _agent_only_gap(db, session_id, src["end_ms"], start):
            break
        start = src["start_ms"]
    if (start, end) != (ans["start_ms"], ans["end_ms"]):
        q.answer = {**ans, "start_ms": start, "end_ms": end}


def _agent_only_gap(db: DbSession, session_id: str, start_ms: int, end_ms: int) -> bool:
    """True if [start_ms, end_ms) overlaps no person's segment and no private segment."""
    hit = (
        db.query(Segment.id)
        .filter(
            Segment.session_id == session_id,
            (Segment.speaker_id.isnot(None)) | (Segment.is_private == True),  # noqa: E712
            Segment.start_ms < end_ms,
            Segment.end_ms > start_ms,
        )
        .first()
    )
    return hit is None


def extend_session_answers(db: DbSession, session_id: str) -> list[str]:
    """Repair for answers recorded before merge_stories widened them.

    Every answered question whose answer comes from session_id gets the range
    merge_stories would now give it. Returns the ids of the changed questions.
    """
    changed: list[str] = []
    for q in db.query(Question).filter(Question.status == QuestionStatus.answered).all():
        if not q.answer or q.answer.get("session_id") != session_id:
            continue
        story: Story | None = db.get(Story, q.answer.get("story_id"))
        if story is None:
            continue
        before = dict(q.answer)
        _extend_answer(db, q, story)
        if q.answer != before:
            changed.append(q.id)
    db.flush()
    return changed


# ---------------------------------------------------------------------------
# add_question
# ---------------------------------------------------------------------------

_AGENT_SOURCES = {QuestionSource.follow_up.value, QuestionSource.gap.value}


def add_question_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    text: str,
    source: str,
    period: str | None = None,
) -> dict[str, str]:
    """Add an agent question for the circle's center person.

    Matches against the circle's sensitive topics: a match is saved with
    status "filtered" (kept, never asked), otherwise "waiting".
    """
    if not text or not text.strip():
        raise ValueError("text must not be empty.")
    if source not in _AGENT_SOURCES:
        raise ValueError(f"Invalid source '{source}'. Use 'follow_up' or 'gap'.")
    if period is not None and period not in _VALID_PERIODS:
        raise ValueError(
            f"Invalid period '{period}'. Use one of: {', '.join(sorted(_VALID_PERIODS))}."
        )

    circle: Circle | None = db.get(Circle, circle_id)
    if circle is None:
        raise ValueError(f"Circle '{circle_id}' not found.")

    if source == QuestionSource.gap.value:
        if period is None:
            raise ValueError("A gap question needs the period it is about.")
        waiting_gap = (
            db.query(Question.id)
            .filter(
                Question.circle_id == circle_id,
                Question.source == QuestionSource.gap,
                Question.period == period,
                Question.status == QuestionStatus.waiting,
            )
            .first()
        )
        if waiting_gap is not None:
            raise ValueError(f"A gap question about '{period}' is already waiting. Add no other.")

    topics = db.query(SensitiveTopic).filter(SensitiveTopic.circle_id == circle_id).all()
    sensitive = any(_matches_sensitive_topic(text, t.text) for t in topics)
    status = QuestionStatus.filtered if sensitive else QuestionStatus.waiting

    q = Question(
        circle_id=circle_id,
        target_person_id=circle.center_person_id,
        asker_id=None,
        text=text.strip(),
        source=source,
        period=period,
        status=status,
        answer=None,
        created_at=now_utc().isoformat(),
    )
    db.add(q)
    db.flush()
    return {"question_id": q.id, "status": status.value}


# ---------------------------------------------------------------------------
# mark_question_declined / reopen_question
# ---------------------------------------------------------------------------

def _require_asked_question(db: DbSession, circle_id: str, question_id: str) -> Question:
    q: Question | None = db.get(Question, question_id)
    if q is None or q.circle_id != circle_id:
        raise ValueError(f"Question '{question_id}' not found in this circle.")
    if q.status != QuestionStatus.asked:
        raise ValueError(
            f"Question '{question_id}' has status '{q.status}', expected 'asked'."
        )
    return q


def mark_question_declined_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    question_id: str,
    session_id: str,
    start_ms: int,
    end_ms: int,
) -> None:
    """Set an asked question to "declined": the speaker declined to answer it.

    start_ms / end_ms is where the speaker declines, in a session of the
    circle; it must not overlap a private segment. A declined question is
    never offered again.
    """
    q = _require_asked_question(db, circle_id, question_id)
    _require_session_in_circle(db, session_id, circle_id)
    _check_range(db, session_id, start_ms, end_ms)
    q.status = QuestionStatus.declined
    db.flush()


def reopen_question_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    question_id: str,
) -> None:
    """Return an asked but unanswered question to "waiting" so it is asked again."""
    q = _require_asked_question(db, circle_id, question_id)
    q.status = QuestionStatus.waiting
    db.flush()


# ---------------------------------------------------------------------------
# add_refused_topic
# ---------------------------------------------------------------------------

def add_refused_topic_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    session_id: str,
    text: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    """Remember a topic the speaker refused on her own ("I don't want to talk
    about Hatice"): a SensitiveTopic with source "speaker", added_by the center.

    Same range rules as mark_question_declined: session_id is the session being
    archived (the X-Evoca-Session-Id header, never a model argument), the range
    must not overlap a private segment, and it must hold the center's own words
    (a refusal by anyone else in a gathering is not the center's). Only the archivist of a center's session
    may call it, never for a panel recording. The same topic text twice is
    stored once; a family topic with that text does not count (the admin can
    delete it). Returns {topic_id, added}.
    """
    topic = " ".join((text or "").split())
    if not topic:
        raise ValueError("text must not be empty.")
    if len(topic) > _MAX_TOPIC_CHARS:
        raise ValueError(f"text must be at most {_MAX_TOPIC_CHARS} characters: name the topic only.")
    if not _meaningful_words(topic):
        # It would filter no question, so saving it would promise what it cannot keep.
        raise ValueError("text must name the topic itself: a name, a place or an event.")

    circle: Circle | None = db.get(Circle, circle_id)
    if circle is None:
        raise ValueError(f"Circle '{circle_id}' not found.")
    if viewer_id != circle.center_person_id:
        raise ValueError("Only the archivist of the center's own sessions can add a refused topic.")
    if not session_id:
        raise ValueError("No session: a refused topic must be in the session being archived.")
    sess = _require_session_in_circle(db, session_id, circle_id)
    if sess.started_by == SessionStart.panel_recording:
        raise ValueError("A panel recording cannot add a refused topic.")
    _check_range(db, session_id, start_ms, end_ms)

    spoken = (
        db.query(Segment.id)
        .filter(
            Segment.session_id == session_id,
            Segment.is_private == False,  # noqa: E712
            Segment.speaker_id == circle.center_person_id,
            Segment.start_ms < end_ms,
            Segment.end_ms > start_ms,
        )
        .first()
    )
    if spoken is None:
        raise ValueError(
            f"Range {start_ms}-{end_ms} ms holds no words of the center person. "
            f"Use the range of the segment where they refuse."
        )

    # Only the center's own topics count as duplicates: a family topic with the
    # same text can be deleted by the admin, and the refusal must outlive it.
    norm = topic.lower()
    for existing in db.query(SensitiveTopic).filter(
        SensitiveTopic.circle_id == circle_id,
        SensitiveTopic.source == TopicSource.speaker,
    ).all():
        if " ".join(existing.text.lower().split()) == norm:
            return {"topic_id": existing.id, "added": False}

    row = SensitiveTopic(
        circle_id=circle_id,
        text=topic,
        source=TopicSource.speaker,
        added_by=circle.center_person_id,
        created_at=now_utc().isoformat(),
    )
    db.add(row)
    db.flush()
    return {"topic_id": row.id, "added": True}


# ---------------------------------------------------------------------------
# link_stories
# ---------------------------------------------------------------------------

_AI_LINK_REASONS = {r.value for r in LinkReason} - {LinkReason.answer_to.value}
MAX_LINKS_PER_STORY = 3


def _visible_live_links(db: DbSession, viewer_id: str, story_id: str) -> int:
    """Live links of a story whose other story the viewer can see (a link to
    a story they cannot see is not even counted, so the cap reveals nothing)."""
    count = 0
    for link in (
        db.query(StoryLink)
        .filter(
            (StoryLink.from_story_id == story_id) | (StoryLink.to_story_id == story_id),
            StoryLink.status != LinkStatus.removed,
        )
        .all()
    ):
        other = db.get(Story, link.to_story_id if link.from_story_id == story_id else link.from_story_id)
        if other is not None and can_see(db, viewer_id, other):
            count += 1
    return count


def link_stories_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    session_id: str,
    from_story_id: str,
    to_story_id: str,
    reason: str,
) -> dict[str, Any]:
    """Suggest a link (source "ai", status "suggested") from a story saved in
    the session being archived to a related story of the same circle.

    session_id is the X-Evoca-Session-Id header, never a model argument. The
    viewer (the session's teller: the center, or the recorder of a panel
    recording) must be able to see both stories. A link between the same two
    stories, in either direction, is not added twice: its id is returned.
    Neither story may already have MAX_LINKS_PER_STORY live links (counting
    only links to stories the viewer can see). Returns {link_id, added}.
    """
    if reason not in _AI_LINK_REASONS:
        raise ValueError(
            f"Invalid reason '{reason}'. Use one of: {', '.join(sorted(_AI_LINK_REASONS))}."
        )
    if from_story_id == to_story_id:
        raise ValueError("A story cannot be linked to itself.")
    if not session_id:
        raise ValueError("No session: from_story_id must be a story saved in the session being archived.")

    stories: dict[str, Story] = {}
    for story_id in (from_story_id, to_story_id):
        story: Story | None = db.get(Story, story_id)
        # The same message for missing, other circle and not visible.
        if story is None or story.circle_id != circle_id or not can_see(db, viewer_id, story):
            raise ValueError(f"Story '{story_id}' not found in this circle.")
        stories[story_id] = story
    if not any(src.get("session_id") == session_id for src in stories[from_story_id].sources or []):
        raise ValueError("from_story_id must be a story saved in the session being archived.")

    existing = (
        db.query(StoryLink)
        .filter(
            ((StoryLink.from_story_id == from_story_id) & (StoryLink.to_story_id == to_story_id))
            | ((StoryLink.from_story_id == to_story_id) & (StoryLink.to_story_id == from_story_id))
        )
        .first()
    )
    if existing is not None:
        # A link the family removed stays removed: the AI does not suggest it again.
        return {"link_id": existing.id, "added": False}

    for story_id in (from_story_id, to_story_id):
        if _visible_live_links(db, viewer_id, story_id) >= MAX_LINKS_PER_STORY:
            raise ValueError(f"Story '{story_id}' already has {MAX_LINKS_PER_STORY} links. Add no more.")

    link = StoryLink(
        from_story_id=from_story_id,
        to_story_id=to_story_id,
        reason=reason,
        source=LinkSource.ai,
        status=LinkStatus.suggested,
    )
    db.add(link)
    db.flush()
    return {"link_id": link.id, "added": True}


# ---------------------------------------------------------------------------
# find_gaps
# ---------------------------------------------------------------------------

# Earliest plausible age for each period. A period the center cannot have
# reached yet (age below this) is not a gap. Nothing else is skipped: an
# older center may well have stories of every period.
_PERIOD_START_AGE = {
    LifePeriod.childhood.value: 0,
    LifePeriod.youth.value: 13,
    LifePeriod.marriage_early_years.value: 18,
    LifePeriod.raising_children.value: 18,
    LifePeriod.midlife.value: 40,
    LifePeriod.retirement.value: 55,
}


def find_gaps_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    person_id: str,
) -> list[str]:
    """Life periods of the circle's center with no story about her yet, in
    LifePeriod order.

    Only for the center (person_id and the viewer). Counts every story of the
    circle where she is a subject, in any status except hidden, whoever told
    it and whatever its access: only period names leave this function, never
    a story.
    """
    circle: Circle | None = db.get(Circle, circle_id)
    if circle is None:
        raise ValueError(f"Circle '{circle_id}' not found.")
    if person_id != circle.center_person_id or viewer_id != circle.center_person_id:
        raise ValueError("find_gaps is only for the center person of the circle.")

    covered = {
        period
        for (period,) in db.query(StorySubject.period)
        .join(Story, Story.id == StorySubject.story_id)
        .filter(
            Story.circle_id == circle_id,
            Story.status != StoryStatus.hidden,
            StorySubject.person_id == person_id,
        )
        .all()
    }

    person = db.get(Person, person_id)
    age = now_utc().year - person.birth_year if person and person.birth_year else None
    return [
        p.value for p in LifePeriod
        if p.value not in covered and (age is None or age >= _PERIOD_START_AGE[p.value])
    ]
