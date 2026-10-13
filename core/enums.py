"""
Enumerations — exact values from docs/PROJECT.md "Veri modeli > Enumlar".
Do not rename or add values without updating the doc first.
"""

from enum import Enum


class Role(str, Enum):
    center = "center"
    admin = "admin"
    member = "member"


class CircleStatus(str, Enum):
    active = "active"
    memorial = "memorial"  # Vision scope


class LifePeriod(str, Enum):
    childhood = "childhood"
    youth = "youth"
    marriage_early_years = "marriage_early_years"
    raising_children = "raising_children"
    midlife = "midlife"
    retirement = "retirement"


class PeriodSource(str, Enum):
    ai = "ai"
    family = "family"  # family always takes precedence


class SessionKind(str, Enum):
    solo = "solo"
    gathering = "gathering"


class SessionStart(str, Enum):
    invitation = "invitation"
    spontaneous = "spontaneous"
    panel_recording = "panel_recording"


class StoryKind(str, Enum):
    original = "original"
    retelling = "retelling"


class StoryStatus(str, Enum):
    pending = "pending"
    published = "published"
    hidden = "hidden"


class AccessType(str, Enum):
    circle = "circle"
    private = "private"
    selected = "selected"
    all_family = "all_family"


class LinkReason(str, Enum):
    same_place = "same_place"
    same_event = "same_event"
    continuation = "continuation"
    answer_to = "answer_to"


class LinkSource(str, Enum):
    ai = "ai"
    family = "family"


class LinkStatus(str, Enum):
    suggested = "suggested"
    confirmed = "confirmed"
    removed = "removed"


class QuestionSource(str, Enum):
    family = "family"
    follow_up = "follow_up"
    gap = "gap"


class QuestionStatus(str, Enum):
    waiting = "waiting"
    asked = "asked"
    answered = "answered"
    filtered = "filtered"


class InvitationStatus(str, Enum):
    sent = "sent"
    accepted = "accepted"
    postponed = "postponed"
    declined = "declined"
    skipped = "skipped"


class Emoji(str, Enum):
    heart = "heart"
    laugh = "laugh"
    sad = "sad"
    pray = "pray"
