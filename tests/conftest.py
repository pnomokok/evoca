"""Shared fixtures.

The existing API tests identify the viewer with X-Person-Id, which the backend
accepts only in demo mode (docs/ARCHITECTURE.md "Access control", Identity), so
every test runs with EVOCA_DEMO_MODE=1 unless it removes it (tests/test_auth.py
does, for the outside-demo-mode rules).

Demo mode also turns on the demo clock offset. Only tests/test_demo.py is about
that offset; everywhere else it stays zero, as before, so an offset cached by
one test never moves the clock of the next.
"""

from datetime import timedelta

import pytest

from core import clock


@pytest.fixture(autouse=True)
def _demo_mode(request, monkeypatch):
    monkeypatch.setenv("EVOCA_DEMO_MODE", "1")
    if request.module.__name__ != "tests.test_demo":
        monkeypatch.setattr(clock, "demo_offset", lambda: timedelta(0))
