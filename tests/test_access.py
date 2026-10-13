"""
Tests for core.access.can_see() — in-memory SQLite database.

Coverage matrix:
  AccessType × StoryStatus × viewer role
  ─────────────────────────────────────────────────────────────────────────────
  circle      published   → member sees it, non-member does not
  private     published   → only teller sees it
  selected    published   → teller sees it; person in person_ids sees it even
                            if not a member of the circle; others do not
  all_family  published   → person sharing any circle sees it
  ─────────────────────────────────────────────────────────────────────────────
  status: pending         → center/admin see it; plain member does not
                            (unless they are the teller)
  status: hidden          → ONLY teller sees it; admin does NOT (per doc)
  ─────────────────────────────────────────────────────────────────────────────
  teller always sees their own story (regardless of access type)
  non-member viewer is blocked for circle-type stories
"""

from __future__ import annotations

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use in-memory SQLite so tests are isolated and fast.
os.environ["EVOCA_DB_PATH"] = ":memory:"  # overridden below via engine fixture

from core.models import Base, Circle, Membership, Person, Story
from core.enums import (
    AccessType,
    CircleStatus,
    LifePeriod,
    PeriodSource,
    Role,
    SessionKind,
    SessionStart,
    StoryKind,
    StoryStatus,
)
from core.access import can_see, is_member, role, shares_any_circle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db():
    """Provide a fresh in-memory SQLite session per test function."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False,
                           expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def family(db):
    """
    Create a minimal family fixture and return a namespace of named objects.

    Circle A:
      - fatma  : center
      - ayse   : admin
      - elif_  : member
      - can    : member

    Circle B (for all_family test):
      - fatma  : center
      - cousin : member
    """
    fatma  = Person(name="Fatma",  birth_year=1948, language="en")
    ayse   = Person(name="Ayse",   birth_year=1975, language="en")
    elif_  = Person(name="Elif",   birth_year=2003, language="en")
    can    = Person(name="Can",    birth_year=2006, language="en")
    cousin = Person(name="Cousin", birth_year=1980, language="en")
    outsider = Person(name="Outsider", birth_year=1990, language="en")
    db.add_all([fatma, ayse, elif_, can, cousin, outsider])
    db.flush()

    circle_a = Circle(
        name="The Yilmaz Family",
        center_person_id=fatma.id,
        status=CircleStatus.active,
        chat_time="10:00",
        timezone="Europe/Istanbul",
    )
    circle_b = Circle(
        name="Extended Yilmaz",
        center_person_id=fatma.id,
        status=CircleStatus.active,
        chat_time="18:00",
        timezone="Europe/Istanbul",
    )
    db.add_all([circle_a, circle_b])
    db.flush()

    db.add_all([
        Membership(person_id=fatma.id,  circle_id=circle_a.id, role=Role.center),
        Membership(person_id=ayse.id,   circle_id=circle_a.id, role=Role.admin),
        Membership(person_id=elif_.id,  circle_id=circle_a.id, role=Role.member),
        Membership(person_id=can.id,    circle_id=circle_a.id, role=Role.member),
        # circle_b
        Membership(person_id=fatma.id,  circle_id=circle_b.id, role=Role.center),
        Membership(person_id=cousin.id, circle_id=circle_b.id, role=Role.member),
    ])
    db.commit()

    class F:
        pass

    f = F()
    f.db = db
    f.fatma    = fatma
    f.ayse     = ayse
    f.elif_    = elif_
    f.can      = can
    f.cousin   = cousin
    f.outsider = outsider
    f.circle_a = circle_a
    f.circle_b = circle_b
    return f


def _story(circle_id, teller_id, access_type, person_ids=None,
           status=StoryStatus.published) -> Story:
    """Helper: create a Story object (not yet added to db)."""
    return Story(
        circle_id=circle_id,
        teller_id=teller_id,
        kind=StoryKind.original,
        title="Test story",
        ai_summary="A summary.",
        sources=[],
        access={"type": access_type, "person_ids": person_ids or []},
        status=status,
        publish_at="2026-10-14T10:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# AccessType.circle
# ---------------------------------------------------------------------------

class TestCircleAccess:
    def test_member_can_see(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.elif_.id, story) is True
        assert can_see(f.db, f.ayse.id,  story) is True
        assert can_see(f.db, f.can.id,   story) is True
        assert can_see(f.db, f.fatma.id, story) is True  # teller is member too

    def test_non_member_cannot_see(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.outsider.id, story) is False

    def test_cousin_in_other_circle_cannot_see(self, family):
        """Cousin is in circle_b but NOT in circle_a."""
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.cousin.id, story) is False


# ---------------------------------------------------------------------------
# AccessType.private
# ---------------------------------------------------------------------------

class TestPrivateAccess:
    def test_teller_can_see_own_private_story(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.private)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.fatma.id, story) is True

    def test_admin_cannot_see_private_story(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.private)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.ayse.id, story) is False

    def test_member_cannot_see_private_story(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.private)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.elif_.id, story) is False

    def test_outsider_cannot_see_private_story(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.private)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.outsider.id, story) is False


# ---------------------------------------------------------------------------
# AccessType.selected
# ---------------------------------------------------------------------------

class TestSelectedAccess:
    def test_teller_can_see(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.selected,
                       person_ids=[f.ayse.id])
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.fatma.id, story) is True

    def test_selected_member_can_see(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.selected,
                       person_ids=[f.ayse.id])
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.ayse.id, story) is True

    def test_non_selected_member_cannot_see(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.selected,
                       person_ids=[f.ayse.id])
        f.db.add(story); f.db.flush()

        # Elif is a circle member but not in person_ids
        assert can_see(f.db, f.elif_.id, story) is False

    def test_selected_non_member_can_see(self, family):
        """
        A person listed in access.person_ids can see the story even if they are
        not a member of the circle. The doc's pseudo-code is:
            if t == "selected": return viewer_id == teller_id or viewer_id in access.person_ids
        There is no is_member() check for 'selected'.
        """
        f = family
        # outsider is not in circle_a at all, but is explicitly selected
        story = _story(f.circle_a.id, f.fatma.id, AccessType.selected,
                       person_ids=[f.outsider.id])
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.outsider.id, story) is True

    def test_unselected_outsider_cannot_see(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.selected,
                       person_ids=[f.ayse.id])
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.outsider.id, story) is False


# ---------------------------------------------------------------------------
# AccessType.all_family
# ---------------------------------------------------------------------------

class TestAllFamilyAccess:
    def test_person_sharing_any_circle_can_see(self, family):
        """cousin shares circle_b with fatma (the teller), so they can see."""
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.all_family)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.cousin.id, story) is True

    def test_outsider_sharing_no_circle_cannot_see(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.all_family)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.outsider.id, story) is False


# ---------------------------------------------------------------------------
# StoryStatus.pending
# ---------------------------------------------------------------------------

class TestPendingStatus:
    def test_center_sees_pending(self, family):
        f = family
        story = _story(f.circle_a.id, f.ayse.id, AccessType.circle,
                       status=StoryStatus.pending)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.fatma.id, story) is True  # fatma = center

    def test_admin_sees_pending(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle,
                       status=StoryStatus.pending)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.ayse.id, story) is True  # ayse = admin

    def test_plain_member_cannot_see_pending(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle,
                       status=StoryStatus.pending)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.elif_.id, story) is False  # elif = member

    def test_teller_sees_own_pending_story(self, family):
        """The teller always sees their own story, even while pending."""
        f = family
        story = _story(f.circle_a.id, f.elif_.id, AccessType.circle,
                       status=StoryStatus.pending)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.elif_.id, story) is True

    def test_non_member_cannot_see_pending(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle,
                       status=StoryStatus.pending)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.outsider.id, story) is False


# ---------------------------------------------------------------------------
# StoryStatus.hidden
# ---------------------------------------------------------------------------

class TestHiddenStatus:
    def test_teller_sees_own_hidden_story(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle,
                       status=StoryStatus.hidden)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.fatma.id, story) is True

    def test_admin_cannot_see_hidden_story(self, family):
        """
        A hidden story is only visible to the teller — not even the admin.
        This follows the doc's pseudo-code: first check is status==hidden
        and viewer != teller → False.
        """
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle,
                       status=StoryStatus.hidden)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.ayse.id, story) is False  # ayse = admin

    def test_member_cannot_see_hidden_story(self, family):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, AccessType.circle,
                       status=StoryStatus.hidden)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.elif_.id, story) is False

    def test_center_cannot_see_hidden_story_by_someone_else(self, family):
        """center sees hidden stories by others too? No — the rule is unconditional."""
        f = family
        # ayse posts a hidden story; fatma is center but not the teller
        story = _story(f.circle_a.id, f.ayse.id, AccessType.circle,
                       status=StoryStatus.hidden)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.fatma.id, story) is False


# ---------------------------------------------------------------------------
# Teller always sees their own story
# ---------------------------------------------------------------------------

class TestTellerAlwaysSees:
    @pytest.mark.parametrize("access_type", [
        AccessType.circle,
        AccessType.private,
        AccessType.selected,
        AccessType.all_family,
    ])
    def test_teller_sees_own_published_story(self, family, access_type):
        f = family
        story = _story(f.circle_a.id, f.fatma.id, access_type,
                       status=StoryStatus.published)
        f.db.add(story); f.db.flush()

        assert can_see(f.db, f.fatma.id, story) is True


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_role_returns_correct_role(self, family):
        f = family
        assert role(f.db, f.fatma.id, f.circle_a.id) == Role.center
        assert role(f.db, f.ayse.id,  f.circle_a.id) == Role.admin
        assert role(f.db, f.elif_.id, f.circle_a.id) == Role.member

    def test_role_returns_none_for_non_member(self, family):
        f = family
        assert role(f.db, f.outsider.id, f.circle_a.id) is None

    def test_is_member_true_for_member(self, family):
        f = family
        assert is_member(f.db, f.can.id, f.circle_a.id) is True

    def test_is_member_false_for_non_member(self, family):
        f = family
        assert is_member(f.db, f.outsider.id, f.circle_a.id) is False

    def test_shares_any_circle_true(self, family):
        f = family
        # cousin and fatma share circle_b
        assert shares_any_circle(f.db, f.cousin.id, f.fatma.id) is True

    def test_shares_any_circle_false(self, family):
        f = family
        assert shares_any_circle(f.db, f.outsider.id, f.fatma.id) is False
