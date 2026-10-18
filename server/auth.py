"""
Who is calling: one FastAPI dependency for every panel, admin, audio, photo
and device endpoint (docs/ARCHITECTURE.md "Access control", Identity).

1. Authorization: Bearer <session_token>  the session gives the person and the
   circle; an X-Circle-Id that differs is the endpoint's own non-member 403.
2. No bearer token, EVOCA_DEMO_MODE=1     X-Person-Id and X-Circle-Id, exactly
   as in the hackathon build (the web client's person picker).
3. Anything else                          401, one body for every case.

Membership is still checked by each endpoint, as before. Tokens are looked up
by their hash (core.services.auth) and never logged; redact_token_paths keeps
invite tokens out of the uvicorn access log.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Header, HTTPException

import core.db as cdb
from core.clock import demo_mode
from core.services import auth as auth_svc

SIGN_IN_REQUIRED = "Sign-in required."
NOT_A_MEMBER = "Not a member of any circle."


@dataclass(frozen=True)
class Viewer:
    person_id: str
    circle_id: str                  # "" = the first membership (demo headers only)
    auth_session_id: str | None = None


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail=SIGN_IN_REQUIRED, headers={"WWW-Authenticate": "Bearer"})


def bearer_token(authorization: str) -> str | None:
    scheme, _, token = authorization.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def viewer_dependency(forbidden: Callable[[], HTTPException]):
    """A dependency that returns the Viewer; forbidden() is the endpoint's non-member 403."""

    def resolve(
        authorization: Annotated[str, Header(alias="authorization")] = "",
        x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
        x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
    ) -> Viewer:
        if authorization:
            token = bearer_token(authorization)
            if token is None:
                raise unauthorized()
            with cdb.SessionLocal() as db:
                sess = auth_svc.session_for_token(db, token)
            if sess is None:
                raise unauthorized()
            if x_circle_id and x_circle_id != sess.circle_id:
                raise forbidden()
            return Viewer(sess.person_id, sess.circle_id, sess.id)
        if demo_mode():
            return Viewer(x_person_id, x_circle_id)
        raise unauthorized()

    return resolve


panel_viewer = viewer_dependency(lambda: HTTPException(status_code=403, detail=NOT_A_MEMBER))


# ---------------------------------------------------------------------------
# Access log: never write an invite token
# ---------------------------------------------------------------------------

_TOKEN_PATH = re.compile(r"(/api/invites/|/join/)[^/?\s\"]+")


class RedactTokens(logging.Filter):
    """Replace the token in /api/invites/<token> and /join/<token> in log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(_TOKEN_PATH.sub(r"\1<redacted>", a) if isinstance(a, str) else a
                                for a in record.args)
        if isinstance(record.msg, str):
            record.msg = _TOKEN_PATH.sub(r"\1<redacted>", record.msg)
        return True


def redact_token_paths() -> None:
    log = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactTokens) for f in log.filters):
        log.addFilter(RedactTokens())
