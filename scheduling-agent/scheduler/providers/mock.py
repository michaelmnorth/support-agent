"""File-backed fake calendar for demos and tests."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import home
from ..models import BusyBlock, EventPayload
from ..tz import resolve_zone


class MockProvider:
    name = "mock"

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or os.environ.get("SCHEDULER_MOCK_CALENDAR", home() / "fixtures" / "calendar_sample.json"))
        self.sent: list[dict] = []
        self.drafts: list[dict] = []

    def _load(self) -> dict:
        if not self.path.exists():
            return {"events": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_busy(self, start: datetime, end: datetime) -> list[BusyBlock]:
        out: list[BusyBlock] = []
        for e in self._load().get("events", []):
            b = BusyBlock.model_validate(e)
            if b.end > start and b.start < end:
                out.append(b)
        return out

    def create_event(self, payload: EventPayload) -> dict:
        data = self._load()
        start_zone = resolve_zone(payload.start["timeZone"])
        end_zone = resolve_zone(payload.end["timeZone"])
        start = datetime.fromisoformat(payload.start["dateTime"]).replace(tzinfo=start_zone)
        end = datetime.fromisoformat(payload.end["dateTime"]).replace(tzinfo=end_zone)
        event_id = f"mock-{uuid.uuid4().hex[:8]}"
        data.setdefault("events", []).append(
            {
                "id": event_id,
                "start": start.astimezone(timezone.utc).isoformat(),
                "end": end.astimezone(timezone.utc).isoformat(),
                "subject": payload.subject,
                "show_as": "busy",
                "attendees": [a["emailAddress"]["address"] for a in payload.attendees],
                "online_meeting": payload.isOnlineMeeting,
            }
        )
        self._save(data)
        return {
            "id": event_id,
            "webLink": f"https://outlook.office.com/calendar/item/{event_id}",
            "onlineMeeting": {"joinUrl": f"https://teams.microsoft.com/l/meetup-join/mock/{event_id}"} if payload.isOnlineMeeting else None,
            "invitesSent": True,
        }

    def create_draft(self, *, to: list[str], subject: str, body: str, reply_to_message_id: Optional[str] = None) -> dict:
        d = {"id": f"draft-{uuid.uuid4().hex[:8]}", "to": to, "subject": subject, "body": body, "replyTo": reply_to_message_id}
        self.drafts.append(d)
        return {"id": d["id"], "webLink": f"https://outlook.office.com/mail/drafts/{d['id']}"}

    def send_mail(self, *, to: list[str], subject: str, body: str, reply_to_message_id: Optional[str] = None) -> dict:
        m = {"id": f"msg-{uuid.uuid4().hex[:8]}", "to": to, "subject": subject, "body": body, "replyTo": reply_to_message_id}
        self.sent.append(m)
        return {"id": m["id"], "status": "sent"}
