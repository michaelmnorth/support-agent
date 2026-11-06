"""Pydantic models shared by the CLI, the MCP server, and the providers."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ShowAs(str, Enum):
    """Mirrors Microsoft Graph's event.showAs values."""

    free = "free"
    tentative = "tentative"
    busy = "busy"
    oof = "oof"
    working_elsewhere = "workingElsewhere"
    unknown = "unknown"


class BusyBlock(BaseModel):
    """One existing calendar item. Times must be timezone-aware ISO-8601."""

    start: datetime
    end: datetime
    subject: Optional[str] = None
    show_as: ShowAs = ShowAs.busy
    is_all_day: bool = False
    is_cancelled: bool = False

    @field_validator("start", "end")
    @classmethod
    def _must_be_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("calendar times must be timezone-aware (include an offset or Z)")
        return v

    def blocks_time(self, treat_tentative_as_busy: bool = True) -> bool:
        if self.is_cancelled:
            return False
        if self.show_as == ShowAs.free:
            return False
        if self.show_as == ShowAs.tentative and not treat_tentative_as_busy:
            return False
        return True


class Slot(BaseModel):
    """A proposed meeting time. Always stored in UTC-aware datetimes."""

    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


class Contact(BaseModel):
    name: str
    email: Optional[str] = None
    role: Optional[str] = None
    slack: Optional[str] = None
    timezone: Optional[str] = Field(default=None, description="IANA zone; overrides the client default")


class MeetingDefaults(BaseModel):
    duration_minutes: int = 30
    subject_template: str = "{customer} <> {owner_company}: {topic}"
    internal_attendees: list[str] = Field(default_factory=list, description="Emails always invited")
    client_working_hours: Optional[str] = Field(
        default=None,
        description="Client-side hours in the client's zone, e.g. '09:00-17:00'. Slots must fit inside.",
    )
    online_meeting_provider: Literal["teamsForBusiness", "none"] = "teamsForBusiness"


class ClientProfile(BaseModel):
    id: str
    customer: str
    timezone: str = Field(description="IANA zone, e.g. America/Chicago")
    contacts: list[Contact] = Field(default_factory=list)
    preferred_channel: Literal["email", "slack", "teams"] = "email"
    automation: Literal["draft_only", "ask_then_send", "auto_send"] = Field(
        default="ask_then_send",
        description=(
            "draft_only: leave a draft, never send. ask_then_send: show the owner, send on their yes. "
            "auto_send: send proposals and confirmations without asking (earn this per client)."
        ),
    )
    meeting_defaults: MeetingDefaults = Field(default_factory=MeetingDefaults)
    notes: Optional[str] = None
    source_path: Optional[str] = Field(default=None, exclude=True)

    def primary_contact(self) -> Optional[Contact]:
        return self.contacts[0] if self.contacts else None

    def find_contact(self, needle: str) -> Optional[Contact]:
        needle_l = needle.lower().strip()
        for c in self.contacts:
            if needle_l in (c.name or "").lower() or needle_l == (c.email or "").lower():
                return c
            if c.slack and needle_l == c.slack.lower().lstrip("@"):
                return c
        return None


class WorkingHours(BaseModel):
    """Ranges per weekday, each 'HH:MM-HH:MM' in the owner's zone. Empty list = day off."""

    monday: list[str] = ["09:00-17:00"]
    tuesday: list[str] = ["09:00-17:00"]
    wednesday: list[str] = ["09:00-17:00"]
    thursday: list[str] = ["09:00-17:00"]
    friday: list[str] = ["09:00-17:00"]
    saturday: list[str] = []
    sunday: list[str] = []

    def for_weekday(self, weekday: int) -> list[str]:
        names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return getattr(self, names[weekday])


class SchedulingRules(BaseModel):
    buffer_minutes: int = Field(default=30, description="Keep this far away from any meeting, both sides")
    slot_granularity_minutes: int = Field(default=30, description="Offer starts on these boundaries")
    default_duration_minutes: int = 30
    min_lead_time_hours: float = Field(default=24, description="Never offer anything sooner than this")
    lookahead_days: int = 7
    max_options: int = 4
    max_per_day: int = 2
    min_gap_between_options_hours: float = 2.0
    treat_tentative_as_busy: bool = True
    daily_blocks: list[str] = Field(default_factory=list, description="e.g. ['12:00-13:00'] lunch, owner zone")
    skip_dates: list[str] = Field(default_factory=list, description="YYYY-MM-DD holidays or PTO")


class Owner(BaseModel):
    name: str = "Michael"
    email: str = "owner@example.com"
    company: str = "Our Team"
    timezone: str = "America/New_York"


class ResponseStyle(BaseModel):
    email_signoff: str = "Thanks,\nMichael"
    slack_signoff: str = ""
    list_bullet: str = "•"
    show_both_zones: bool = True
    lead_with_client_zone: bool = True


class Preferences(BaseModel):
    owner: Owner = Field(default_factory=Owner)
    working_hours: WorkingHours = Field(default_factory=WorkingHours)
    scheduling: SchedulingRules = Field(default_factory=SchedulingRules)
    response: ResponseStyle = Field(default_factory=ResponseStyle)


class MeetingRequest(BaseModel):
    """What Claude extracts from an inbound email or Slack message before calling the tools."""

    client_id: Optional[str] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    requester_timezone: Optional[str] = Field(default=None, description="If the message states one")
    channel: Literal["email", "slack", "teams"] = "email"
    duration_minutes: Optional[int] = None
    topic: Optional[str] = None
    earliest: Optional[datetime] = Field(default=None, description="Requester said 'after Nov 10', etc.")
    latest: Optional[datetime] = None
    preferred_time_of_day: Optional[Literal["morning", "afternoon", "any"]] = "any"
    additional_attendees: list[str] = Field(default_factory=list)
    original_message_excerpt: Optional[str] = None


class Proposal(BaseModel):
    """Output of propose_times: structured slots plus a rendered draft Claude can send or edit."""

    client_id: Optional[str]
    owner_timezone: str
    client_timezone: str
    duration_minutes: int
    slots: list[Slot]
    slot_labels: list[str]
    draft: str
    channel: str
    warnings: list[str] = Field(default_factory=list)


class EventPayload(BaseModel):
    """A Microsoft Graph POST /me/events body, returned so Claude (or the Graph provider) can create it."""

    subject: str
    start: dict
    end: dict
    attendees: list[dict]
    isOnlineMeeting: bool
    onlineMeetingProvider: Optional[str]
    body: dict
    allowNewTimeProposals: bool = True
    transactionId: Optional[str] = None
