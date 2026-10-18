"""
Sign-in with personal invite links (docs/ARCHITECTURE.md "Access control",
Identity, and "REST API").

  create_invite         POST   /api/admin/invites, POST /api/circles (the creator)
  revoke_invite         DELETE /api/admin/invites/{person_id}
  revoke_person_links   DELETE /api/admin/members/{person_id}
  invite_info           GET    /api/invites/{token}
  accept_invite         POST   /api/invites/{token}/accept
  session_for_token     every endpoint that takes a bearer token (server/auth.py)
  logout                POST   /api/auth/logout

Rules applied here:
- Tokens are secrets.token_urlsafe(32). Only their SHA-256 hashes are stored
  and looked up; a token is returned once, when it is made, and never logged.
- One active link per (circle, person): a new link revokes the old one.
- Revoking a link revokes every session made from it.
- A revoked, wrong or unknown invite token is the same NotFound; a link whose
  person is no longer a member looks the same.

Functions take an open SQLAlchemy session and commit their own writes.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.clock import now_utc
from core.models import AuthSession, Circle, InviteLink, Membership, Person
from core.services.admin import MEMBER_NOT_FOUND, NotFound, require_admin

INVITE_NOT_FOUND = "Invite not found."
JOIN_PATH = "/join/"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _revoke_links(db: DbSession, links: list[InviteLink]) -> None:
    """Revoke the links and every session made from them (no commit)."""
    now = now_utc().isoformat()
    for link in links:
        link.revoked_at = now
        (db.query(AuthSession)
         .filter(AuthSession.invite_id == link.id, AuthSession.revoked_at.is_(None))
         .update({AuthSession.revoked_at: now}, synchronize_session=False))
    db.flush()


def _active_links(db: DbSession, circle_id: str, person_id: str) -> list[InviteLink]:
    return (db.query(InviteLink)
            .filter(InviteLink.circle_id == circle_id, InviteLink.person_id == person_id,
                    InviteLink.revoked_at.is_(None))
            .all())


def _make_link(db: DbSession, circle_id: str, person_id: str, created_by: str) -> tuple[InviteLink, str]:
    """Revoke the person's active link (and its sessions), add a new one (no commit)."""
    _revoke_links(db, _active_links(db, circle_id, person_id))
    token = new_token()
    link = InviteLink(circle_id=circle_id, person_id=person_id, token_hash=hash_token(token),
                      created_by=created_by)
    db.add(link)
    db.flush()
    return link, token


def _make_session(db: DbSession, link: InviteLink) -> str:
    """Add a sign-in session for the link's person (no commit); returns its token."""
    token = new_token()
    db.add(AuthSession(person_id=link.person_id, circle_id=link.circle_id,
                       token_hash=hash_token(token), invite_id=link.id))
    db.flush()
    return token


def _invite_dict(link: InviteLink, token: str) -> dict[str, Any]:
    return {"invite_url_path": JOIN_PATH + token, "token": token, "person_id": link.person_id}


def create_invite(db: DbSession, viewer_id: str, circle_id: str, person_id: Any) -> dict[str, Any]:
    """An admin makes a personal link for any member of the circle, the center included."""
    require_admin(db, viewer_id, circle_id)
    if not isinstance(person_id, str) or db.get(Membership, (person_id, circle_id)) is None:
        raise NotFound(MEMBER_NOT_FOUND)
    link, token = _make_link(db, circle_id, person_id, viewer_id)
    db.commit()
    return _invite_dict(link, token)


def creator_sign_in(db: DbSession, circle_id: str, creator_id: str) -> dict[str, str]:
    """The creator of a new circle: their own link and a session made from it (no admin check; commits)."""
    link, invite_token = _make_link(db, circle_id, creator_id, creator_id)
    session_token = _make_session(db, link)
    db.commit()
    return {"session_token": session_token, "invite_url_path": JOIN_PATH + invite_token}


def revoke_invite(db: DbSession, viewer_id: str, circle_id: str, person_id: str) -> dict[str, Any]:
    """Revoke the person's active link and its sessions; NotFound if there is none."""
    require_admin(db, viewer_id, circle_id)
    links = _active_links(db, circle_id, person_id)
    if not links:
        raise NotFound(INVITE_NOT_FOUND)
    _revoke_links(db, links)
    db.commit()
    return {"person_id": person_id, "revoked": True}


def revoke_person_links(db: DbSession, circle_id: str, person_id: str) -> None:
    """Revoke the person's links in the circle and their sessions (no commit; member removal)."""
    _revoke_links(db, _active_links(db, circle_id, person_id))


def _valid_link(db: DbSession, token: Any) -> tuple[InviteLink, Membership]:
    if not isinstance(token, str) or not token:
        raise NotFound(INVITE_NOT_FOUND)
    link = db.query(InviteLink).filter(InviteLink.token_hash == hash_token(token)).first()
    if link is None or link.revoked_at is not None:
        raise NotFound(INVITE_NOT_FOUND)
    m = db.get(Membership, (link.person_id, link.circle_id))
    if m is None:
        raise NotFound(INVITE_NOT_FOUND)
    return link, m


def invite_info(db: DbSession, token: str) -> dict[str, Any]:
    """{circle_name, person_name, role} for an active link."""
    link, m = _valid_link(db, token)
    circle = db.get(Circle, link.circle_id)
    person = db.get(Person, link.person_id)
    return {"circle_name": circle.name, "person_name": person.name, "role": m.role}


def accept_invite(db: DbSession, token: str) -> dict[str, Any]:
    """A new sign-in session; the link stays usable until revoked."""
    link, _ = _valid_link(db, token)
    session_token = _make_session(db, link)
    db.commit()
    return {"session_token": session_token, "person_id": link.person_id, "circle_id": link.circle_id}


def session_for_token(db: DbSession, token: str) -> AuthSession | None:
    """The active session for a bearer token, or None (unknown or revoked).

    Its invite link must be active and its membership must exist too, so a
    session that raced a revoke or a member removal fails closed."""
    if not token:
        return None
    return (db.query(AuthSession)
            .join(InviteLink, InviteLink.id == AuthSession.invite_id)
            .join(Membership, (Membership.person_id == AuthSession.person_id)
                  & (Membership.circle_id == AuthSession.circle_id))
            .filter(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None),
                    InviteLink.revoked_at.is_(None))
            .first())


def logout(db: DbSession, session_id: str) -> dict[str, Any]:
    sess = db.get(AuthSession, session_id)
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = now_utc().isoformat()
        db.commit()
    return {"logged_out": True}
