"""
The opening's wording composed in code, and the opening guard.

  reaction_line      one sentence per emoji (at most two), relation from the membership
  question_lead_in   family question names its asker; own questions (follow_up, gap) do not
  opening_mismatch   fires on a family question in the companion's voice or a wrong reaction verb
  opening_template   "Hello, <name>! <reaction lines> <lead_in> <question as stored>"
"""

from __future__ import annotations

import pytest

from core.services.opening_lines import Reactor, question_lead_in, reaction_line
from server.agents.chat_agent import (
    FREE_MEMORY_INVITATION, OpeningFacts, opening_mismatch, opening_template, stored_question,
)

ELIF = ("Elif Yilmaz", "granddaughter")
CAN = ("Can Yilmaz", "grandson")
TITLE = "The Mulberry Tree"


def _r(person, emoji):
    return Reactor(person[0], person[1], emoji)


# ---------------------------------------------------------------------------
# reaction_line
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("emoji, verb", [
    ("heart", "loved"),
    ("laugh", "laughed at"),
    ("sad", "was moved by"),
    ("pray", "was grateful for"),
])
def test_each_emoji_has_its_verb(emoji, verb):
    assert reaction_line(TITLE, [_r(ELIF, emoji)]) == (
        f"Your granddaughter Elif {verb} your story about The Mulberry Tree.")


def test_two_people_same_emoji_share_one_sentence():
    assert reaction_line(TITLE, [_r(ELIF, "heart"), _r(CAN, "heart")]) == (
        "Your granddaughter Elif and your grandson Can loved your story about The Mulberry Tree.")


def test_two_people_moved_takes_the_plural():
    assert reaction_line(TITLE, [_r(ELIF, "sad"), _r(CAN, "sad")]) == (
        "Your granddaughter Elif and your grandson Can were moved by your story about The Mulberry Tree.")


def test_two_emojis_one_short_sentence_each():
    assert reaction_line(TITLE, [_r(CAN, "laugh"), _r(ELIF, "heart")]) == (
        "Your granddaughter Elif loved your story about The Mulberry Tree. Your grandson Can laughed at it.")


def test_one_person_two_emojis_relation_said_once():
    assert reaction_line(TITLE, [_r(ELIF, "heart"), _r(ELIF, "laugh")]) == (
        "Your granddaughter Elif loved your story about The Mulberry Tree. Elif laughed at it.")


def test_three_emojis_stay_within_two_sentences():
    line = reaction_line(TITLE, [_r(ELIF, "heart"), _r(CAN, "sad"), _r(("Ayse", "daughter"), "pray")])
    assert line == ("Your granddaughter Elif loved your story about The Mulberry Tree. "
                    "Your grandson Can and your daughter Ayse also reacted to it.")
    assert line.count(".") == 2


def test_no_relation_says_the_first_name():
    assert reaction_line(TITLE, [Reactor("Elif Yilmaz", None, "laugh")]) == (
        "Elif laughed at your story about The Mulberry Tree.")


def test_unknown_emoji_gives_no_line():
    assert reaction_line(TITLE, [_r(ELIF, "thumbs")]) == ""


# ---------------------------------------------------------------------------
# question_lead_in
# ---------------------------------------------------------------------------

def test_family_lead_in_names_the_asker_with_relation():
    assert question_lead_in("family", "Elif Yilmaz", "granddaughter") == (
        "Your granddaughter Elif has a question for you:")


def test_family_lead_in_without_relation():
    assert question_lead_in("family", "Elif", None) == "Elif has a question for you:"


@pytest.mark.parametrize("source", ["follow_up", "gap"])
def test_own_question_lead_in(source):
    assert question_lead_in(source, None, None) == "I've been wondering about something:"


# ---------------------------------------------------------------------------
# Opening guard
# ---------------------------------------------------------------------------

def _live_case() -> OpeningFacts:
    """The live bug: Elif laughed at The Mulberry Tree and asked about winter."""
    return OpeningFacts(
        center_first_name="Fatma",
        reaction_lines=["Your granddaughter Elif laughed at your story about The Mulberry Tree."],
        reaction_emojis=["laugh"],
        question={"question_id": "q1", "text": "Grandma, how was your house kept warm in winter?",
                  "source": "family", "asker_id": "elif", "asker_name": "Elif Yilmaz",
                  "lead_in": "Your granddaughter Elif has a question for you:"},
    )


LIVE_BUG_REPLY = ("Hello, Fatma! Your granddaughter Elif loved your story about The Mulberry Tree. "
                  "I've been wondering about something: How was your house kept warm in winter?")


def test_guard_fires_on_the_live_bug():
    assert opening_mismatch(LIVE_BUG_REPLY, _live_case()) is not None


def test_guard_fires_on_own_voice_even_with_the_right_verb():
    reply = LIVE_BUG_REPLY.replace("loved", "laughed at")
    assert opening_mismatch(reply, _live_case()) == "family_lead_in_missing"


def test_guard_fires_on_wrong_verb_alone():
    reply = ("Hello, Fatma! Your granddaughter Elif loved your story about The Mulberry Tree. "
             "Your granddaughter Elif has a question for you: how did you keep warm in winter?")
    assert opening_mismatch(reply, _live_case()) == "reaction_verb_mismatch"


def test_guard_does_not_fire_on_a_correct_reply():
    reply = ("Hello, Fatma! Your granddaughter Elif laughed at your story about The Mulberry Tree. "
             "Your granddaughter Elif has a question for you: how did you keep your house warm in winter?")
    assert opening_mismatch(reply, _live_case()) is None


def test_guard_accepts_a_curly_apostrophe_and_case():
    facts = _live_case()
    facts.question = {**facts.question, "asker_id": None, "source": "gap",
                      "lead_in": "I've been wondering about something:"}
    reply = ("Hello, Fatma! Your granddaughter Elif laughed at your story about The Mulberry Tree. "
             "I’ve been wondering about something: what kept your house warm in winter?")
    assert opening_mismatch(reply, facts) is None


def test_guard_fires_when_own_question_is_given_to_family():
    facts = _live_case()
    facts.question = {**facts.question, "asker_id": None, "source": "gap",
                      "lead_in": "I've been wondering about something:"}
    reply = ("Hello, Fatma! Your granddaughter Elif laughed at your story about The Mulberry Tree. "
             "Your granddaughter Elif has a question for you: what kept your house warm?")
    assert opening_mismatch(reply, facts) == "own_question_attributed"


def test_guard_fires_on_an_invented_reaction():
    facts = OpeningFacts("Fatma", [], [], None)
    assert opening_mismatch("Hello, Fatma! Elif loved your story. What is on your mind?", facts) == (
        "reaction_verb_mismatch")


def test_template_for_the_live_case_is_exact():
    assert opening_template(_live_case()) == (
        "Hello, Fatma! Your granddaughter Elif laughed at your story about The Mulberry Tree. "
        "Your granddaughter Elif has a question for you: How was your house kept warm in winter?")


def test_template_without_a_question_invites_a_memory():
    facts = OpeningFacts("Fatma", ["Elif laughed at your story about The Mulberry Tree."], ["laugh"], None)
    assert opening_template(facts) == (
        f"Hello, Fatma! Elif laughed at your story about The Mulberry Tree. {FREE_MEMORY_INVITATION}")


@pytest.mark.parametrize("stored, spoken", [
    ("Grandma, how was your house kept warm in winter?", "How was your house kept warm in winter?"),
    ("Fatma, what did you cook??", "What did you cook?"),
    ("what games did you play", "What games did you play?"),
    ("“Grandpa, where did you work?”", "Where did you work?"),
])
def test_stored_question_is_cleaned_for_speech(stored, spoken):
    assert stored_question(stored, "Fatma") == spoken
