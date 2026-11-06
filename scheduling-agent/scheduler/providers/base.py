from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol

from ..models import BusyBlock, EventPayload


class CalendarProvider(Protocol):
    """The small surface the scheduler needs. Keep it minimal so a Graph, mock, or Google adapter is trivial."""

    name: str

    def get_busy(self, start: datetime, end: datetime) -> list[BusyBlock]: ...

    def create_event(self, payload: EventPayload) -> dict:
        """Create the event and send invites. Returns the provider's event record (id, webLink, joinUrl...)."""
        ...

    def create_draft(self, *, to: list[str], subject: str, body: str, reply_to_message_id: Optional[str] = None) -> dict:
        """Create an unsent draft in the owner's mailbox. Returns {id, webLink}."""
        ...

    def send_mail(self, *, to: list[str], subject: str, body: str, reply_to_message_id: Optional[str] = None) -> dict:
        ...
