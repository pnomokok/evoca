"""
link_stories and find_gaps (core/services/archive_tools.py) and how the
archivist uses them.

Coverage
--------
- link_stories: a link is created (source ai, status suggested); the same pair
  in reverse returns the same id; cross-circle, self, answer_to, a story from
  another session and a story the viewer cannot see are rejected; at most 3
  links per story.
- Archivist: a saved story is linked to a story found with search_archive; in a
  panel recording search_archive only returns stories the recorder can see.
- Panel: a link to a story the viewer cannot see stays invisible on the story
  page and in the playlist; the playlist plays a linked story in period order.
- find_gaps: empty periods for the center; hidden stories do not count, any
  other story about her does; periods she is too young for are left out;
  non-center person or viewer rejected.
- Gap questions: at most one per run, only for a period find_gaps returned,
  none if one is waiting for that period, none in panel mode, and they go
  through the sensitive-topic matcher.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from core.clock import now_utc
from core.enums import (
    AccessType, LinkSource, LinkStatus, PeriodSource, QuestionSource, QuestionStatus,
    SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.models import Question, Segment, Session as OrmSession, Story, StoryLink, StorySubject
from core.services.archive_tools import (
    MAX_LINKS_PER_STORY, add_question_data, find_gaps_data, link_stories_data,
)
from server.agents.archivist_agent import ArchivistAgent
from tests.test_api import _client, anyio_backend, test_app  # noqa: F401  (fixtures)
from tests.test_archive_tools import db, w  # noqa: F401  (fixtures)
from tests.test_archivist_agent import DynamicScriptedLLM, FakeArchiveBridge, last_tool_json
from tests.test_chat_agent import ScriptedLLM, _tool_use
from tests.test_panel_stories import _req, _story, world  # noqa: F401  (fixture)

ALL_PERIODS = ["childhood", "youth", "marriage_early_years", "raising_children", "midlife", "retirement"]


def _new_story(w, teller=None, period="childhood", session=None, status=StoryStatus.published,
               access=AccessType.circle, title="Story", place=None, subject=None):
    sess = session or w.sess
    s = Story(circle_id=sess.circle_id, teller_id=(teller or w.fatma).id, kind=StoryKind.original,
              title=title, ai_summary=f"{title} summary", place=place,
              sources=[{"session_id": sess.id, "start_ms": 0, "end_ms": 10_000}],
              access={"type": access, "person_ids": []}, status=status,
              publish_at=now_utc().isoformat(), created_at=now_utc().isoformat())
    w.db.add(s); w.db.flush()
    if period:
        w.db.add(StorySubject(story_id=s.id, person_id=(subject or w.fatma).id, period=period,
                              period_source=PeriodSource.ai))
    w.db.commit()
    return s


def _older_session(w, ended=True):
    sess = OrmSession(circle_id=w.circle.id, kind=SessionKind.solo,
                      started_by=SessionStart.spontaneous, participant_ids=[w.fatma.id],
                      started_at=(now_utc() - timedelta(days=3)).isoformat(),
                      ended_at=(now_utc() - timedelta(days=3)).isoformat() if ended else None)
    w.db.add(sess); w.db.commit()
    return sess


def _link(w, a, b, reason="same_place", viewer=None, session_id=None):
    return link_stories_data(w.db, (viewer or w.fatma).id, w.circle.id,
                             w.sess.id if session_id is None else session_id, a.id, b.id, reason)


# ---------------------------------------------------------------------------
# link_stories
# ---------------------------------------------------------------------------

def test_link_is_created_as_an_ai_suggestion(w):
    new, old = _new_story(w), _new_story(w, session=_older_session(w))
    r = _link(w, new, old)
    link = w.db.get(StoryLink, r["link_id"])
    assert r["added"] is True
    assert (link.from_story_id, link.to_story_id, link.reason) == (new.id, old.id, "same_place")
    assert (link.source, link.status) == (LinkSource.ai, LinkStatus.suggested)


def test_the_same_pair_in_reverse_returns_the_same_link(w):
    a = _new_story(w)
    b = _new_story(w, title="Second")          # also saved in this session
    first = _link(w, a, b)
    again = _link(w, b, a, reason="same_event")
    assert again == {"link_id": first["link_id"], "added": False}
    assert w.db.query(StoryLink).count() == 1


@pytest.mark.parametrize("case", [
    "other_circle", "self", "answer_to", "from_other_session", "not_visible", "no_session",
])
def test_bad_links_are_rejected(w, case):
    new, old = _new_story(w), _new_story(w, session=_older_session(w))
    kwargs = {}
    if case == "other_circle":
        old = w.other_story
    elif case == "self":
        old = new
    elif case == "answer_to":
        kwargs["reason"] = "answer_to"
    elif case == "from_other_session":
        new, old = old, new
    elif case == "not_visible":
        old = _new_story(w, teller=w.elif_, session=_older_session(w), access=AccessType.private)
    elif case == "no_session":
        kwargs["session_id"] = ""
    with pytest.raises(ValueError):
        _link(w, new, old, **kwargs)
    assert w.db.query(StoryLink).count() == 0


def test_at_most_three_links_per_story(w):
    new = _new_story(w)
    older = _older_session(w)
    others = [_new_story(w, session=older, title=f"Old {i}") for i in range(MAX_LINKS_PER_STORY + 1)]
    for other in others[:MAX_LINKS_PER_STORY]:
        _link(w, new, other)
    with pytest.raises(ValueError, match="already has 3 links"):
        _link(w, new, others[-1])


# ---------------------------------------------------------------------------
# Archivist: search and link
# ---------------------------------------------------------------------------

def _agent(w, llm, person=None, **kwargs):
    bridge = FakeArchiveBridge(w.db, (person or w.fatma).id, w.circle.id, session_id=w.sess.id)
    return ArchivistAgent(llm=llm, person_id=(person or w.fatma).id, circle_id=w.circle.id,
                          bridge=bridge, checker_llm=ScriptedLLM(["yes"]), **kwargs), bridge


def _search_results(result):
    out = [t.result for t in result.trace if t.tool == "search_archive"][0]
    return {item["story_id"] for item in out["result"]}


@pytest.mark.anyio
async def test_archivist_links_a_new_story_to_one_it_found(w):
    old = _new_story(w, session=_older_session(w), title="The River House", place="Rize")
    llm = DynamicScriptedLLM([
        [_tool_use("save_story", {
            "title": "Fishing in Rize", "summary": "Fatma fished in the river in Rize.",
            "teller_id": w.fatma.id, "place": "Rize",
            "subjects": [{"person_id": w.fatma.id, "period": "childhood"}],
            "sources": [{"session_id": w.sess.id, "start_ms": 0, "end_ms": 10_000}],
        }), _tool_use("search_archive", {"query": "Rize river"})],
        lambda msgs: [_tool_use("link_stories", {
            "from_story_id": last_tool_json(msgs, 0)["story_id"], "to_story_id": old.id,
            "reason": "same_place",
        })],
        "done",
    ])
    agent, _ = _agent(w, llm)
    result = await agent.run(w.sess.id)
    assert old.id in _search_results(result)
    [link_id] = result.links_added
    assert w.db.get(StoryLink, link_id).to_story_id == old.id


@pytest.mark.anyio
async def test_panel_recording_search_only_returns_what_the_recorder_can_see(w):
    older = _older_session(w)
    shared = _new_story(w, session=older, title="Tea in Rize")
    secret = _new_story(w, session=older, title="Rize debt", access=AccessType.private)
    pending = _new_story(w, session=older, title="Rize wedding", status=StoryStatus.pending)
    llm = DynamicScriptedLLM([[_tool_use("search_archive", {"query": "Rize"})], "done"])
    agent, _ = _agent(w, llm, person=w.elif_, panel_recording=True,
                      members=[{"person_id": w.fatma.id, "name": "Fatma"}])
    result = await agent.run(w.sess.id)
    found = _search_results(result)
    assert shared.id in found
    assert secret.id not in found and pending.id not in found


@pytest.mark.anyio
async def test_panel_recording_offers_no_gap_tools(w):
    llm = DynamicScriptedLLM([
        [_tool_use("find_gaps", {"person_id": w.fatma.id}),
         _tool_use("add_question", {"text": "What about your youth?", "source": "gap",
                                    "period": "youth"})],
        "done",
    ])
    agent, bridge = _agent(w, llm, person=w.elif_, panel_recording=True, members=[])
    result = await agent.run(w.sess.id)
    offered = {t["toolSpec"]["name"] for t in llm.calls[0]["tools"]["tools"]}
    assert offered == {"get_session_transcript", "save_story", "search_archive", "link_stories"}
    assert all(t.is_error for t in result.trace)
    assert [n for n, _ in bridge.tool_calls if n in ("find_gaps", "add_question")] == []


# ---------------------------------------------------------------------------
# Panel: links and visibility, playlist order
# ---------------------------------------------------------------------------

def _story_in(db, circle, teller, sess, period, title, access=AccessType.circle, start=0, end=1000):
    return _story(db, circle, teller, [(teller, period)], access=access, title=title,
                  sources=[{"session_id": sess.id, "start_ms": start, "end_ms": end}])


@pytest.mark.anyio
async def test_link_to_an_invisible_story_stays_invisible(world):
    db, circle, fatma, sess = world["db"], world["circle"], world["fatma"], world["sess"]
    secret = _story_in(db, circle, fatma, sess, "youth", "The Well", access=AccessType.private)
    link_stories_data(db, fatma.id, circle.id, sess.id, world["mulberry"].id, secret.id, "same_place")
    db.commit()

    url = f"/api/stories/{world['mulberry'].id}"
    page = (await _req(world["app"], "GET", url, world["elif_"])).json()
    playlist = (await _req(world["app"], "GET", url + "/playlist", world["elif_"])).json()
    assert page["linked_stories"] == []
    assert {i["story_id"] for i in playlist["items"]} == {world["mulberry"].id}
    # The teller of both sees the link.
    own = (await _req(world["app"], "GET", url, fatma)).json()
    assert [l["story"]["id"] for l in own["linked_stories"]] == [secret.id]


@pytest.mark.anyio
async def test_playlist_plays_a_linked_story_in_period_order(world):
    db, circle, fatma, sess = world["db"], world["circle"], world["fatma"], world["sess"]
    later = _story_in(db, circle, fatma, sess, "midlife", "Back to the Tree")
    link_stories_data(db, fatma.id, circle.id, sess.id, later.id, world["mulberry"].id, "continuation")
    db.commit()

    playlist = (await _req(world["app"], "GET", f"/api/stories/{later.id}/playlist",
                           world["elif_"])).json()
    order = []
    for item in playlist["items"]:
        if not order or order[-1] != item["story_id"]:
            order.append(item["story_id"])
    assert order == [world["mulberry"].id, later.id]      # childhood before midlife


# ---------------------------------------------------------------------------
# find_gaps
# ---------------------------------------------------------------------------

def test_find_gaps_returns_the_empty_periods(w):
    assert find_gaps_data(w.db, w.fatma.id, w.circle.id, w.fatma.id) == ALL_PERIODS
    _new_story(w, period="childhood")
    _new_story(w, period="youth", status=StoryStatus.pending)
    # Told by Elif, private to her: still a story about Fatma; only the period leaves.
    _new_story(w, teller=w.elif_, period="raising_children", access=AccessType.private)
    _new_story(w, period="midlife", status=StoryStatus.hidden)        # hidden: not counted
    _new_story(w, period="retirement", subject=w.elif_)               # about someone else
    assert find_gaps_data(w.db, w.fatma.id, w.circle.id, w.fatma.id) == [
        "marriage_early_years", "midlife", "retirement",
    ]


def test_find_gaps_leaves_out_periods_she_is_too_young_for(w):
    w.fatma.birth_year = now_utc().year - 30
    w.db.commit()
    assert find_gaps_data(w.db, w.fatma.id, w.circle.id, w.fatma.id) == [
        "childhood", "youth", "marriage_early_years", "raising_children",
    ]


@pytest.mark.parametrize("who", ["person", "viewer"])
def test_find_gaps_is_only_for_the_center(w, who):
    viewer, person = (w.fatma, w.elif_) if who == "person" else (w.elif_, w.fatma)
    with pytest.raises(ValueError, match="only for the center"):
        find_gaps_data(w.db, viewer.id, w.circle.id, person.id)


# ---------------------------------------------------------------------------
# Gap questions
# ---------------------------------------------------------------------------

def _gap(period, text="What do you remember about those years?"):
    return _tool_use("add_question", {"text": text, "source": "gap", "period": period})


def _gap_questions(w):
    w.db.expire_all()
    return w.db.query(Question).filter(Question.source == QuestionSource.gap).all()


@pytest.mark.anyio
async def test_one_gap_question_per_run(w):
    llm = DynamicScriptedLLM([
        [_tool_use("find_gaps", {"person_id": w.fatma.id})],
        [_gap("marriage_early_years", "What do you remember about your early married years?"),
         _gap("midlife", "What was your life like in your forties?")],
        "done",
    ])
    agent, _ = _agent(w, llm)
    result = await agent.run(w.sess.id)
    [q] = _gap_questions(w)
    assert (q.period, q.status) == ("marriage_early_years", QuestionStatus.waiting)
    assert len(result.questions_added) == 1
    assert "limit" in result.trace[-1].result_preview.lower()


@pytest.mark.anyio
async def test_gap_question_only_for_a_period_find_gaps_returned(w):
    _new_story(w, period="youth")
    llm = DynamicScriptedLLM([[_gap("youth")], "done"])     # find_gaps not called by the model
    agent, bridge = _agent(w, llm)
    result = await agent.run(w.sess.id)
    assert _gap_questions(w) == []
    assert "find_gaps" in [n for n, _ in bridge.tool_calls]   # the code asked for itself
    assert result.trace[-1].is_error


@pytest.mark.anyio
async def test_no_gap_question_when_one_is_waiting_for_that_period(w):
    add_question_data(w.db, w.fatma.id, w.circle.id, "What was your youth like?", "gap", "youth")
    w.db.commit()
    llm = DynamicScriptedLLM([[_tool_use("find_gaps", {"person_id": w.fatma.id})],
                              [_gap("youth", "What do you remember about being young?")], "done"])
    agent, _ = _agent(w, llm)
    result = await agent.run(w.sess.id)
    assert len(_gap_questions(w)) == 1
    assert result.questions_added == []
    assert "already waiting" in result.trace[-1].result_preview


def test_service_gap_question_needs_a_period(w):
    with pytest.raises(ValueError, match="needs the period"):
        add_question_data(w.db, w.fatma.id, w.circle.id, "What about then?", "gap")


@pytest.mark.anyio
async def test_gap_question_goes_through_the_sensitive_topic_matcher(w):
    # The fixture's sensitive topic is "1977 traffic accident".
    llm = DynamicScriptedLLM([[_tool_use("find_gaps", {"person_id": w.fatma.id})],
                              [_gap("midlife", "What happened around the time of the accident?")],
                              "done"])
    agent, _ = _agent(w, llm)
    result = await agent.run(w.sess.id)
    assert [q["status"] for q in result.questions_added] == [QuestionStatus.filtered.value]


# ---------------------------------------------------------------------------
# Privacy review: what the archivist may reuse
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_device_search_only_offers_shareable_stories_without_audio(w):
    older = _older_session(w)
    shared = _new_story(w, session=older, title="Tea in Rize")
    own_pending = _new_story(w, session=older, title="Rize market", status=StoryStatus.pending)
    own_private = _new_story(w, session=older, title="Rize debt", access=AccessType.private)
    others_pending = _new_story(w, teller=w.elif_, session=older, title="Rize bus",
                                status=StoryStatus.pending)
    llm = DynamicScriptedLLM([[_tool_use("search_archive", {"query": "Rize"})], "done"])
    agent, _ = _agent(w, llm)
    result = await agent.run(w.sess.id)
    seen = [t.result for t in result.trace if t.tool == "search_archive"][0]["result"]
    assert {i["story_id"] for i in seen} == {shared.id, own_pending.id}
    assert own_private.id not in str(seen) and others_pending.id not in str(seen)
    assert all(set(i) == {"story_id", "title", "ai_summary", "place", "periods"} for i in seen)


@pytest.mark.anyio
async def test_save_story_cannot_borrow_audio_from_another_session(w):
    older = _older_session(w)
    w.db.add(Segment(session_id=older.id, speaker_id=w.fatma.id, start_ms=0, end_ms=10_000,
                     transcript="The debt in Rize.", words=[], is_private=False))
    w.db.commit()
    args = {"title": "Rize", "summary": "Fatma talks about Rize.", "teller_id": w.fatma.id,
            "subjects": [], "sources": [{"session_id": older.id, "start_ms": 0, "end_ms": 10_000}]}
    llm = DynamicScriptedLLM([[_tool_use("save_story", args)], "done"])
    agent, bridge = _agent(w, llm)
    result = await agent.run(w.sess.id)
    assert result.story_ids == [] and result.trace[0].is_error
    assert "save_story" not in [n for n, _ in bridge.tool_calls]
    # The server checks it again against the session header.
    from core.services.archive_tools import save_story_data
    with pytest.raises(ValueError, match="session being archived"):
        save_story_data(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id, **args)


def test_retelling_of_a_story_the_teller_cannot_see_is_rejected(w):
    from core.services.archive_tools import save_story_data
    hidden_from_fatma = _new_story(w, teller=w.elif_, session=_older_session(w),
                                   access=AccessType.private)
    with pytest.raises(ValueError, match="not found"):
        save_story_data(w.db, w.fatma.id, w.circle.id, title="Again", summary="s",
                        teller_id=w.fatma.id, subjects=[],
                        sources=[{"session_id": w.sess.id, "start_ms": 0, "end_ms": 10_000}],
                        original_story_id=hidden_from_fatma.id)


def test_link_cap_applies_to_both_stories_and_ignores_invisible_links(w):
    older = _older_session(w)
    target = _new_story(w, session=older, title="Popular")
    for i in range(MAX_LINKS_PER_STORY):
        w.db.add(StoryLink(from_story_id=_new_story(w, session=older, title=f"S{i}").id,
                           to_story_id=target.id, reason="same_place",
                           source=LinkSource.ai, status=LinkStatus.suggested))
    w.db.commit()
    with pytest.raises(ValueError, match="already has 3 links"):
        _link(w, _new_story(w), target)
    # A link to a story Fatma cannot see is not counted for her.
    other = _new_story(w, session=older, title="Other")
    secret = _new_story(w, teller=w.elif_, session=older, access=AccessType.private)
    for _ in range(MAX_LINKS_PER_STORY):
        w.db.add(StoryLink(from_story_id=secret.id, to_story_id=other.id, reason="same_place",
                           source=LinkSource.ai, status=LinkStatus.suggested))
    w.db.commit()
    assert _link(w, _new_story(w, title="New"), other)["added"] is True
