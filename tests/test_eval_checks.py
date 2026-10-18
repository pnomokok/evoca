"""
Tests for evals/text_checks.py (the eval runner's pure text helpers).

  has_tech_words    — "sewing tools" is a memory, "my tools" / "a tool call" is machinery
  parse_judge_json  — valid JSON as is; the judge's unescaped quotes inside
                      invented_facts are repaired; no JSON / unrepairable -> error
  attributes_question — "she has a question", "<name> asks", "<relation> wants to
                      know" are caught; the companion's own question is not
"""

from __future__ import annotations

import pytest

from evals.text_checks import attributes_question, has_tech_words, parse_judge_json, says_any_phrase


@pytest.mark.parametrize("reply", [
    "Do you still have any of the sewing tools you used when you were younger?",
    "It's wonderful that you've kept those family sewing tools.",
    "Your father's tools hung on the wall of the workshop.",
    "What a lovely garden.",
])
def test_no_tech_words(reply):
    assert not has_tech_words(reply)


@pytest.mark.parametrize("reply", [
    "Let me check my tools.",
    "I used a tool to look that up.",
    "The tool call failed.",
    "That is stored in my database.",
    "I am an AI.",
])
def test_tech_words(reply):
    assert has_tech_words(reply)


def test_valid_json_is_parsed_as_is():
    text = '```json\n{"invented_facts": [], "followups_specific": true, "warmth": 5, "notes": ""}\n```'
    assert parse_judge_json(text) == {
        "invented_facts": [], "followups_specific": True, "warmth": 5, "notes": "",
    }


def test_unescaped_quotes_in_invented_facts_are_repaired():
    # Shape of the real failures in evals/results/prompt_v4.json.
    text = """```json
{
  "invented_facts": [
    "What was your brother's name again?" (The companion asked this as if the person had not said it),
    "Your grandmother was so happy" - the companion introduced a reference
  ],
  "followups_specific": true,
  "respected_declined_topic": null,
  "warmth": 4,
  "notes": "Asked about the private part."
}
```"""
    verdict = parse_judge_json(text)
    assert "error" not in verdict
    assert verdict["repaired"] is True
    assert verdict["warmth"] == 4 and verdict["followups_specific"] is True
    assert len(verdict["invented_facts"]) == 2
    assert verdict["invented_facts"][0].startswith("What was your brother's name again?")


@pytest.mark.parametrize("text,error", [
    ("I cannot judge this.", "judge returned no JSON"),
    ('{"invented_facts": [}', "judge returned invalid JSON"),
])
def test_unusable_judge_output_is_an_error(text, error):
    assert parse_judge_json(text)["error"] == error


ASKER_VOICE = ["your grandfather", "your grandpa"]


@pytest.mark.parametrize("reply", [
    "What was your grandfather like at work?",
    "Your  Grandpa made every dress?",
])
def test_asker_voice_relation_is_caught(reply):
    assert says_any_phrase(reply, ASKER_VOICE)


@pytest.mark.parametrize("reply", [
    "What was your husband like at work?",
    "What did Kemal make in his shop?",
    "Selin's grandfather was a tailor.",
    "Your grandfathers' tools",          # whole words only
])
def test_own_relation_or_name_passes(reply):
    assert not says_any_phrase(reply, ASKER_VOICE)


ASKERS = ["Defne", "granddaughter", "your granddaughter"]


@pytest.mark.parametrize("reply", [
    "Defne loved your story about the plum orchard. And she has a question for you: what do you remember?",
    "Defne asks what you remember about your early married years.",
    "Your granddaughter wants to know about your wedding day.",
    "Defne would love to know more about it.",
    "Here is a question from Defne: what was your first home like?",
])
def test_attributed_question_is_caught(reply):
    assert attributes_question(reply, ASKERS)


@pytest.mark.parametrize("reply", [
    "Defne loved your plum story! I have a question for you: what do you remember about your early married years?",
    "Defne loved your story about the plum orchard. What do you remember about your early married years?",
    "She is so proud of you. I'd love to know more about the bakery.",
    "The baker asked for flour every morning, didn't he.",
])
def test_own_question_is_not_attributed(reply):
    assert not attributes_question(reply, ASKERS)

