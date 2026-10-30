"""The use-cases, independent of transport (CLI, MCP, or direct import).

Each function takes plain data in and returns pydantic models out, so the same code backs:
  * `python -m scheduler.cli ...`  (Claude Code / Cowork skill running a script)
  * the MCP server                 (Claude Desktop / Claude Code tool calls)
  * a future Agent SDK loop        (fully local automation)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from . import availability
from .config import find_client, load_clients, load_preferences
from .models import BusyBlock, ClientProfile, EventPayload, MeetingRequest, Preferences, Proposal, Slot
from .providers import get_provider
from .templates import render_confirmation, render_proposal
from .tz import format_slot, resolve_zone, to_windows

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def coerce_busy(items: Iterable[dict] | None) -> list[BusyBlock]:
    """Accept Graph calendarView items or our own simple {start,end,...} dicts."""
    out: list[BusyBlock] = []
    for raw in items or []:
        if "start" in raw and isinstance(raw["start"], dict):
            # Microsoft Graph shape: {"start": {"dateTime": "...", "timeZone": "..."}, "showAs": "busy", ...}
            s = _graph_dt(raw["start"])
            e = _graph_dt(raw["end"])
            out.append(
                BusyBlock(
                    start=s,
                    end=e,
                    subject=raw.get("subject"),
                    show_as=raw.get("showAs", "busy"),
                    is_all_day=bool(raw.get("isAllDay", False)),
                    is_cancelled=bool(raw.get("isCancelled", False)),
                )
            )
        else:
            out.append(BusyBlock.model_validate(raw))
    return out


def _graph_dt(obj: dict) -> datetime:
    """Graph returns naive dateTime strings plus a timeZone name (often 'UTC', or whatever Prefer asked for)."""
    raw = obj["dateTime"]
    # Graph gives 7 fractional digits; Python handles up to 6.
    if "." in raw:
        head, frac = raw.split(".", 1)
        raw = f"{head}.{frac[:6]}"
    dt = datetime.fromisoformat(raw.replace("Z", ""))
    zone = resolve_zone(obj.get("timeZone") or "UTC")
    return dt.replace(tzinfo=zone) if dt.tzinfo is None else dt.astimezone(zone)


def resolve_client(client_ref: Optional[str], clients: Optional[list[ClientProfile]] = None) -> Optional[ClientProfile]:
    if not client_ref:
        return None
    return find_client(client_ref, clients)


def gather_busy(prefs: Preferences, window_start: datetime, window_end: datetime, busy: Optional[list[dict]],
                provider_name: Optional[str]) -> tuple[list[BusyBlock], list[str]]:
    """Busy blocks either supplied by the caller (Claude via the M365 connector) or fetched from a provider."""
    warnings: list[str] = []
    if busy is not None:
        return coerce_busy(busy), warnings
    provider = get_provider(provider_name)
    if provider is None:
        warnings.append("No busy list supplied and provider is 'none'; treating the calendar as empty.")
        return [], warnings
    return provider.get_busy(window_start - timedelta(hours=1), window_end + timedelta(hours=1)), warnings


def propose(
    request: MeetingRequest,
    *,
    busy: Optional[list[dict]] = None,
    prefs: Optional[Preferences] = None,
    provider_name: Optional[str] = None,
    lookahead_days: Optional[int] = None,
    max_options: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Proposal:
    prefs = prefs or load_preferences()
    now = now or _now()
    client = resolve_client(request.client_id)
    duration = request.duration_minutes or (client.meeting_defaults.duration_minutes if client else None) \
        or prefs.scheduling.default_duration_minutes
    client_zone = request.requester_timezone or (client.timezone if client else None) or prefs.owner.timezone

    warnings: list[str] = []
    if request.client_id and client is None:
        warnings.append(f"No client profile matched {request.client_id!r}; using the owner's zone ({prefs.owner.timezone}).")
    if not request.requester_timezone and client is None:
        warnings.append("Requester time zone unknown; defaulted to the owner's zone. Confirm with the requester.")

    days = lookahead_days or prefs.scheduling.lookahead_days
    window_start = max(now, request.earliest) if request.earliest else now
    window_end = window_start + timedelta(days=days)
    if request.latest and request.latest < window_end:
        window_end = request.latest

    blocks, w = gather_busy(prefs, window_start, window_end, busy, provider_name)
    warnings += w

    all_slots = availability.find_free_slots(
        blocks, prefs, duration, window_start, window_end,
        now=now, client=client, client_timezone=client_zone,
        earliest=request.earliest, latest=request.latest, time_of_day=request.preferred_time_of_day,
    )
    picks = availability.shortlist(all_slots, prefs, max_options=max_options)
    if not picks and request.preferred_time_of_day in ("morning", "afternoon"):
        warnings.append(f"Nothing matched the '{request.preferred_time_of_day}' preference; widened to any time of day.")
        all_slots = availability.find_free_slots(
            blocks, prefs, duration, window_start, window_end,
            now=now, client=client, client_timezone=client_zone,
            earliest=request.earliest, latest=request.latest,
        )
        picks = availability.shortlist(all_slots, prefs, max_options=max_options)
    if not picks:
        warnings.append(f"No free {duration}-minute slot in the next {days} days that satisfies every rule.")

    draft = render_proposal(
        picks, prefs, channel=request.channel, recipient_name=request.requester_name, client=client,
        client_zone=client_zone, duration=duration, topic=request.topic,
    )
    labels = [format_slot(s.start, s.end, client_zone, prefs.owner.timezone) for s in picks]
    return Proposal(
        client_id=client.id if client else request.client_id,
        owner_timezone=prefs.owner.timezone,
        client_timezone=client_zone,
        duration_minutes=duration,
        slots=picks,
        slot_labels=labels,
        draft=draft,
        channel=request.channel,
        warnings=warnings,
    )


def check(start: datetime, duration_minutes: int, *, busy: Optional[list[dict]] = None,
          client_ref: Optional[str] = None, prefs: Optional[Preferences] = None,
          provider_name: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    """Validate a time the other party proposed. Returns {ok, problems, slot_label}."""
    prefs = prefs or load_preferences()
    client = resolve_client(client_ref)
    end = start + timedelta(minutes=duration_minutes)
    blocks, warnings = gather_busy(prefs, start - timedelta(days=1), end + timedelta(days=1), busy, provider_name)
    problems = availability.check_slot(start, duration_minutes, blocks, prefs, client=client, now=now)
    cz = client.timezone if client else prefs.owner.timezone
    return {
        "ok": not problems,
        "problems": problems,
        "warnings": warnings,
        "slot_label": format_slot(start, end, cz, prefs.owner.timezone),
    }


def build_event_payload(
    start: datetime,
    duration_minutes: int,
    *,
    subject: str,
    attendees: list[str],
    optional_attendees: Optional[list[str]] = None,
    body_text: str = "",
    teams: bool = True,
    owner_timezone: str = "America/New_York",
) -> EventPayload:
    """Exactly the JSON Microsoft Graph wants for POST /me/events. Times are expressed in the owner's zone."""
    zone = resolve_zone(owner_timezone)
    s = start.astimezone(zone)
    e = (start + timedelta(minutes=duration_minutes)).astimezone(zone)
    win = to_windows(owner_timezone)

    def att(email: str, kind: str) -> dict:
        return {"emailAddress": {"address": email}, "type": kind}

    return EventPayload(
        subject=subject,
        start={"dateTime": s.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": win},
        end={"dateTime": e.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": win},
        attendees=[att(a, "required") for a in attendees] + [att(a, "optional") for a in (optional_attendees or [])],
        isOnlineMeeting=teams,
        onlineMeetingProvider="teamsForBusiness" if teams else None,
        body={"contentType": "text", "content": body_text},
        allowNewTimeProposals=True,
        transactionId=str(uuid.uuid4()),
    )


def confirm(
    start: datetime,
    duration_minutes: int,
    *,
    client_ref: Optional[str],
    attendee_emails: list[str],
    topic: Optional[str] = None,
    recipient_name: Optional[str] = None,
    channel: str = "email",
    busy: Optional[list[dict]] = None,
    create: bool = False,
    prefs: Optional[Preferences] = None,
    provider_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Validate the chosen time, build the Graph event payload, render the confirmation reply, optionally create it."""
    prefs = prefs or load_preferences()
    client = resolve_client(client_ref)
    validation = check(start, duration_minutes, busy=busy, client_ref=client_ref, prefs=prefs,
                       provider_name=provider_name, now=now)
    cz = client.timezone if client else prefs.owner.timezone
    internal = list(client.meeting_defaults.internal_attendees) if client else []
    all_attendees = list(dict.fromkeys([*attendee_emails, *internal]))
    subject_tpl = client.meeting_defaults.subject_template if client else "{customer}: {topic}"
    subject = subject_tpl.format(
        customer=client.customer if client else "Meeting",
        owner_company=prefs.owner.company,
        topic=topic or "Call",
        owner=prefs.owner.name,
    )
    teams = (client.meeting_defaults.online_meeting_provider if client else "teamsForBusiness") == "teamsForBusiness"
    payload = build_event_payload(
        start, duration_minutes, subject=subject, attendees=all_attendees,
        body_text=f"Scheduled via {prefs.owner.name}'s scheduling assistant." + (f"\n\nTopic: {topic}" if topic else ""),
        teams=teams, owner_timezone=prefs.owner.timezone,
    )
    slot = Slot(start=start.astimezone(UTC), end=(start + timedelta(minutes=duration_minutes)).astimezone(UTC))
    reply = render_confirmation(slot, prefs, channel=channel, recipient_name=recipient_name, client_zone=cz, teams=teams)

    result: dict = {
        "ok": validation["ok"],
        "problems": validation["problems"],
        "slot_label": validation["slot_label"],
        "event_payload": payload.model_dump(mode="json"),
        "confirmation_reply": reply,
        "created": None,
    }
    if create:
        if not validation["ok"]:
            result["created"] = {"error": "refused: time violates scheduling rules", "problems": validation["problems"]}
        else:
            provider = get_provider(provider_name)
            if provider is None:
                result["created"] = {"error": "provider is 'none'; create the event with the M365 connector using event_payload"}
            else:
                result["created"] = provider.create_event(payload)
    return result


def list_clients_summary() -> list[dict]:
    return [
        {
            "id": c.id,
            "customer": c.customer,
            "timezone": c.timezone,
            "preferred_channel": c.preferred_channel,
            "automation": c.automation,
            "notes": c.notes,
            "contacts": [{"name": ct.name, "email": ct.email, "slack": ct.slack} for ct in c.contacts],
            "default_duration": c.meeting_defaults.duration_minutes,
        }
        for c in load_clients()
    ]
