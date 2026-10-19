"""
The opening's exact wording, composed in code (the companion says it as given).

docs/ARCHITECTURE.md "Key design decisions": the model names intent, the code
does the precise work. The opening's reaction sentences and the lead-in to the
marked question are built here from data the opening already gets; the chat
agent's opening guard checks the reply against them.

  reaction_line(...)   one or two sentences per story:
                       "Your granddaughter Elif laughed at your story about The Mulberry Tree."
  question_lead_in()   "Your granddaughter Elif has a question for you:" (family)
                       "I've been wondering about something:" (follow_up, gap)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from core.enums import Emoji, QuestionSource

# Emoji -> verb (singular, plural). Order of Emoji is the order of the sentences.
REACTION_VERBS: dict[str, tuple[str, str]] = {
    Emoji.heart.value: ("loved", "loved"),
    Emoji.laugh.value: ("laughed at", "laughed at"),
    Emoji.sad.value: ("was moved by", "were moved by"),
    Emoji.pray.value: ("was grateful for", "were grateful for"),
}
_EMOJI_ORDER = [e.value for e in Emoji]

OWN_LEAD_IN = "I've been wondering about something:"


@dataclass
class Reactor:
    name: str                       # full name; only the first name is said
    relation_to_center: str | None
    emoji: str


def first_name(name: str | None) -> str:
    parts = (name or "").split()
    return parts[0] if parts else ""


def _person(name: str, relation: str | None, capital: bool) -> str:
    """"your granddaughter Elif", or "Elif" without a relation."""
    if not relation:
        return first_name(name)
    return f"{'Your' if capital else 'your'} {relation} {first_name(name)}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _people(reactors: list[Reactor], introduced: set[str]) -> str:
    """The reactors of one sentence, each with the relation the first time."""
    said = []
    for i, r in enumerate(reactors):
        relation = None if r.name in introduced else r.relation_to_center
        said.append(_person(r.name, relation, capital=i == 0))
        introduced.add(r.name)
    return _join(said)


def reaction_line(story_title: str, reactors: Iterable[Reactor]) -> str:
    """At most two sentences telling who reacted to one story, and how.

    Same emoji: one sentence ("Your granddaughter Elif and your son Can loved
    your story about X."). Different emojis: one short sentence each; from the
    third emoji on, the remaining people share the second sentence
    ("... also reacted to it.").
    """
    by_emoji: dict[str, list[Reactor]] = {}
    for r in reactors:
        if r.emoji in REACTION_VERBS and r.name not in {x.name for x in by_emoji.get(r.emoji, [])}:
            by_emoji.setdefault(r.emoji, []).append(r)
    groups = sorted(by_emoji.items(), key=lambda kv: _EMOJI_ORDER.index(kv[0]))
    if not groups:
        return ""
    introduced: set[str] = set()
    sentences = []
    emoji, people = groups[0]
    verb = REACTION_VERBS[emoji][len(people) > 1]
    sentences.append(f"{_people(people, introduced)} {verb} your story about {story_title}.")
    if len(groups) == 2:
        emoji, people = groups[1]
        verb = REACTION_VERBS[emoji][len(people) > 1]
        sentences.append(f"{_people(people, introduced)} {verb} it.")
    elif len(groups) > 2:
        rest: list[Reactor] = []
        for _, people in groups[1:]:
            rest += [p for p in people if p.name not in {x.name for x in rest}]
        sentences.append(f"{_people(rest, introduced)} also reacted to it.")
    return " ".join(sentences)


def reaction_verbs(emojis: Iterable[str]) -> set[str]:
    """The verbs (singular and plural) a reaction line may use for these emojis."""
    return {v for e in emojis if e in REACTION_VERBS for v in REACTION_VERBS[e]}


def question_lead_in(source: str, asker_name: str | None, relation: str | None) -> str:
    """The exact words before the marked question. A family question names its
    asker (with the relation when known); the companion's own question does not."""
    if source == QuestionSource.family and first_name(asker_name):
        return f"{_person(asker_name or '', relation, capital=True)} has a question for you:"
    if source == QuestionSource.family:
        return "Someone in your family has a question for you:"
    return OWN_LEAD_IN
