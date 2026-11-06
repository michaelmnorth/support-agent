"""MCP server exposing the scheduler as tools (stdio transport).

Register with Claude Code from the scheduling-agent/ folder:
    claude mcp add --transport stdio scheduler -- python -m scheduler.mcp_server
or in .mcp.json (project scope, committed):
    {"mcpServers": {"scheduler": {"type": "stdio", "command": "python", "args": ["-m", "scheduler.mcp_server"],
                                  "cwd": "scheduling-agent", "env": {"SCHEDULER_PROVIDER": "none"}}}}

Design note: with SCHEDULER_PROVIDER=none the tools never touch a calendar themselves. Claude reads the
calendar through the Microsoft 365 connector and passes the events in as `busy`. That keeps all
credentials inside the sanctioned connector and keeps this server pure computation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from mcp.server.mcpserver import MCPServer

from . import service
from .models import MeetingRequest
from .tz import convert, format_slot, label, resolve_zone

server = MCPServer(
    name="scheduler",
    instructions=(
        "Deterministic scheduling helpers. Always call propose_times to pick times and check_time before "
        "confirming a time someone else suggested. Never compute free slots or time zone conversions yourself."
    ),
)


def _dt(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("datetime must include a UTC offset, e.g. 2026-11-04T14:00:00-05:00")
    return d


@server.tool()
def list_clients() -> list[dict]:
    """List known client profiles (id, customer, time zone, contacts, preferred channel)."""
    return service.list_clients_summary()


@server.tool()
def propose_times(
    client: Optional[str] = None,
    requester_name: Optional[str] = None,
    requester_email: Optional[str] = None,
    requester_timezone: Optional[str] = None,
    channel: Literal["email", "slack", "teams"] = "email",
    duration_minutes: Optional[int] = None,
    topic: Optional[str] = None,
    earliest: Optional[str] = None,
    latest: Optional[str] = None,
    time_of_day: Literal["morning", "afternoon", "any"] = "any",
    lookahead_days: Optional[int] = None,
    max_options: Optional[int] = None,
    busy: Optional[list[dict]] = None,
) -> dict:
    """Find meeting options that respect the owner's rules and render a draft reply.

    Args:
        client: client id, customer name, or a contact's email. Supplies the time zone and defaults.
        requester_name: who asked (used for the greeting).
        requester_timezone: only if the message states one; otherwise the client profile's zone is used.
        channel: which draft template to use.
        duration_minutes: defaults to the client's default, then the owner's default.
        earliest/latest: ISO-8601 with offset; constraints the requester gave ("after the 10th").
        busy: calendar events from the Microsoft 365 connector (Graph calendarView items or
              [{"start": iso, "end": iso, "show_as": "busy"}]). Omit to use the configured provider.
    Returns slots (UTC), human labels in both zones, the draft text, and warnings to surface.
    """
    req = MeetingRequest(
        client_id=client, requester_name=requester_name, requester_email=requester_email,
        requester_timezone=requester_timezone, channel=channel, duration_minutes=duration_minutes, topic=topic,
        earliest=_dt(earliest) if earliest else None, latest=_dt(latest) if latest else None,
        preferred_time_of_day=time_of_day,
    )
    return service.propose(req, busy=busy, lookahead_days=lookahead_days, max_options=max_options).model_dump(mode="json")


@server.tool()
def check_time(start: str, duration_minutes: int = 30, client: Optional[str] = None,
               busy: Optional[list[dict]] = None) -> dict:
    """Validate a specific start time (ISO-8601 with offset) against buffers, hours, lead time and client hours."""
    return service.check(_dt(start), duration_minutes, busy=busy, client_ref=client)


@server.tool()
def confirm_meeting(
    start: str,
    duration_minutes: int,
    attendee_emails: list[str],
    client: Optional[str] = None,
    topic: Optional[str] = None,
    recipient_name: Optional[str] = None,
    channel: Literal["email", "slack", "teams"] = "email",
    busy: Optional[list[dict]] = None,
    create: bool = False,
) -> dict:
    """Build the Teams invite (Graph POST /me/events payload) and the confirmation reply for a chosen time.

    With create=false (default) nothing is created: use the returned event_payload with the Microsoft 365
    connector. With create=true the configured provider creates it (mock or graph). Refuses if the time
    violates the rules.
    """
    return service.confirm(
        _dt(start), duration_minutes, client_ref=client, attendee_emails=attendee_emails, topic=topic,
        recipient_name=recipient_name, channel=channel, busy=busy, create=create,
    )


@server.tool()
def convert_time(time: str, to_timezone: str, duration_minutes: int = 30) -> dict:
    """Convert an ISO-8601 time (with offset) into another zone and return a human label."""
    t = _dt(time)
    target = resolve_zone(to_timezone)
    converted = convert(t, target)
    end = converted.fromtimestamp(converted.timestamp() + duration_minutes * 60, tz=target)
    return {
        "converted": converted.isoformat(),
        "zone": target.key,
        "zone_label": label(target, converted),
        "label": format_slot(converted, end, target.key),
    }


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
