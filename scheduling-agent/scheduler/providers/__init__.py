"""Calendar / mail providers.

  mock   reads fixtures/calendar_sample.json and writes created events back to it (for demos and tests)
  graph  Microsoft Graph via MSAL delegated auth (for the 'runs locally on my computer' path)
  none   no provider: Claude supplies the busy list itself (from the Claude Enterprise M365 connector)

Select with SCHEDULER_PROVIDER=mock|graph|none (default: mock).
"""
from __future__ import annotations

import os

from .base import CalendarProvider


def get_provider(name: str | None = None) -> CalendarProvider | None:
    kind = (name or os.environ.get("SCHEDULER_PROVIDER", "mock")).lower()
    if kind == "mock":
        from .mock import MockProvider

        return MockProvider()
    if kind == "graph":
        from .graph import GraphProvider

        return GraphProvider.from_env()
    if kind == "none":
        return None
    raise ValueError(f"unknown provider {kind!r}; use mock, graph, or none")
