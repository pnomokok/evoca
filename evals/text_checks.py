"""
Pure text helpers for the eval runner (no side effects, so tests can import them).

has_tech_words(reply)   — the companion talked about its machinery ("database",
                          "my tools", "a tool call", ...). Plain "tools" is
                          fine: "the sewing tools you used" is a memory.
parse_judge_json(text)  — the judge's JSON verdict, tolerant of the judge
                          writing unescaped quotes inside the invented_facts list.
says_any_phrase(text, phrases) — the text contains one of the phrases as whole
                          words, any spacing or case ("your grandfather", but
                          not "your grandfathers'").
attributes_question(text, askers) — the text says someone asked a question
                          ("she has a question", "Defne asks", "your
                          granddaughter wants to know"); askers are the family's
                          first names and relations.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TECH_WORDS = re.compile(
    r"\b(?:database|stored|system|function|json|AI)\b"
    # "tool" only when it is about the companion's own machinery:
    r"|\b(?:my|a|an)\s+tools?\b"
    r"|\btools?\s+(?:call|calls|result|results)\b"
    r"|\b(?:use|uses|using|used|call|calls|calling|called|check|checking)\s+(?:a\s+|the\s+|my\s+)?tools?\b",
    re.IGNORECASE,
)


def has_tech_words(reply: str) -> bool:
    return bool(_TECH_WORDS.search(reply))


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_INVENTED_LIST = re.compile(r'("invented_facts"\s*:\s*\[)(.*?)(\]\s*,\s*")', re.DOTALL)


def _list_items(body: str) -> list[str]:
    """One fact per line; strip the surrounding quotes and trailing commas."""
    items = []
    for line in body.splitlines():
        line = line.strip().rstrip(",").strip()
        if line.startswith('"'):
            line = line[1:]
        if line.endswith('"'):
            line = line[:-1]
        if line:
            items.append(line)
    return items


def parse_judge_json(text: str) -> dict[str, Any]:
    """Parse the judge's verdict; on broken JSON, repair the invented_facts list.

    Returns {"error": ..., "raw": ...} if nothing usable is found.
    """
    match = _JSON_OBJECT.search(text)
    if not match:
        return {"error": "judge returned no JSON", "raw": text[:300]}
    body = match.group(0)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass

    # The usual breakage: a fact quoting the companion with unescaped quotes.
    # Take the list out, parse the rest, then put the facts back as strings.
    found = _INVENTED_LIST.search(body)
    if found:
        repaired = body[:found.start(2)] + body[found.end(2):]
        try:
            verdict = json.loads(repaired)
        except json.JSONDecodeError:
            verdict = None
        if verdict is not None:
            verdict["invented_facts"] = _list_items(found.group(2))
            verdict["repaired"] = True
            return verdict
    return {"error": "judge returned invalid JSON", "raw": text[:300]}


def says_any_phrase(text: str, phrases: list[str]) -> bool:
    if not phrases:
        return False
    alternatives = (r"\s+".join(map(re.escape, p.split())) for p in phrases)
    return bool(re.search(r"\b(?:" + "|".join(alternatives) + r")\b", text, re.IGNORECASE))


_ASKING = (r"(?:also\s+)?(?:has|had|have)\s+(?:a|another|one)\s+(?:little\s+)?question"
           r"|asks|asked|(?:would|'d)\s+(?:love|like)\s+to\s+know|wants\s+to\s+know|wanted\s+to\s+know"
           r"|is\s+wondering|was\s+wondering|is\s+curious|was\s+curious")


def attributes_question(text: str, askers: list[str]) -> bool:
    named = [r"\s+".join(map(re.escape, a.split())) for a in askers if a.strip()]
    subject = r"\b(?:" + "|".join(["she", "he", "they", *named]) + r")\s+(?:" + _ASKING + r")\b"
    if re.search(subject, text, re.IGNORECASE):
        return True
    if not named:
        return False
    return bool(re.search(r"\bquestion\s+from\s+(?:" + "|".join(named) + r")\b", text, re.IGNORECASE))
