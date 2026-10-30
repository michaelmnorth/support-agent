"""Command line entry point. Every command prints JSON so Claude can read it from a Bash/PowerShell call.

Examples (run from the scheduling-agent/ folder):

  python -m scheduler.cli clients
  python -m scheduler.cli propose --client acme --duration 30 --name "Jane Doe" --channel email
  python -m scheduler.cli propose --client acme --busy-file busy.json          # busy list from the M365 connector
  python -m scheduler.cli check --start 2026-11-04T14:00:00-05:00 --duration 30 --client acme
  python -m scheduler.cli confirm --start 2026-11-04T14:00:00-05:00 --duration 30 --client acme \
         --attendee jane@acme.com --topic "Kickoff" --create
  python -m scheduler.cli convert --time 2026-11-04T14:00:00-05:00 --to America/Los_Angeles
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import service
from .models import MeetingRequest
from .tz import convert, format_slot, label, resolve_zone


def _dt(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise argparse.ArgumentTypeError("datetime must include an offset, e.g. 2026-11-04T14:00:00-05:00")
    return d


def _load_busy(path: Optional[str]) -> Optional[list[dict]]:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "value" in data:  # raw Graph response
        return data["value"]
    if isinstance(data, dict) and "events" in data:
        return data["events"]
    return data


def _print(obj) -> None:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    try:  # Windows consoles default to cp1252; the bullets and en-dashes need UTF-8.
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="scheduler", description="Deterministic scheduling helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("clients", help="List known client profiles")

    pr = sub.add_parser("propose", help="Find times and render a draft reply")
    pr.add_argument("--client", help="client id / customer name / contact email")
    pr.add_argument("--name", help="requester full name")
    pr.add_argument("--email", help="requester email")
    pr.add_argument("--tz", help="requester time zone if stated (IANA, Windows, or PT/ET alias)")
    pr.add_argument("--channel", choices=["email", "slack", "teams"], default="email")
    pr.add_argument("--duration", type=int)
    pr.add_argument("--topic")
    pr.add_argument("--earliest", type=_dt)
    pr.add_argument("--latest", type=_dt)
    pr.add_argument("--time-of-day", choices=["morning", "afternoon", "any"], default="any")
    pr.add_argument("--days", type=int, help="lookahead days (default from preferences)")
    pr.add_argument("--max", type=int, help="max options (default from preferences)")
    pr.add_argument("--busy-file", help="JSON file: Graph calendarView response, or [{start,end,show_as}]")
    pr.add_argument("--provider", choices=["mock", "graph", "none"])
    pr.add_argument("--now", type=_dt, help="override 'now' (testing)")

    ck = sub.add_parser("check", help="Validate a time the other party proposed")
    ck.add_argument("--start", type=_dt, required=True)
    ck.add_argument("--duration", type=int, default=30)
    ck.add_argument("--client")
    ck.add_argument("--busy-file")
    ck.add_argument("--provider", choices=["mock", "graph", "none"])
    ck.add_argument("--now", type=_dt)

    cf = sub.add_parser("confirm", help="Build the invite payload and confirmation reply; --create sends it")
    cf.add_argument("--start", type=_dt, required=True)
    cf.add_argument("--duration", type=int, default=30)
    cf.add_argument("--client")
    cf.add_argument("--attendee", action="append", default=[], help="repeatable")
    cf.add_argument("--topic")
    cf.add_argument("--name", help="recipient name for the confirmation text")
    cf.add_argument("--channel", choices=["email", "slack", "teams"], default="email")
    cf.add_argument("--busy-file")
    cf.add_argument("--provider", choices=["mock", "graph", "none"])
    cf.add_argument("--create", action="store_true", help="actually create the event via the provider")
    cf.add_argument("--now", type=_dt)

    cv = sub.add_parser("convert", help="Convert a time between zones")
    cv.add_argument("--time", type=_dt, required=True)
    cv.add_argument("--to", required=True)
    cv.add_argument("--duration", type=int, default=30)

    a = p.parse_args(argv)

    if a.cmd == "clients":
        _print(service.list_clients_summary())
    elif a.cmd == "propose":
        req = MeetingRequest(
            client_id=a.client, requester_name=a.name, requester_email=a.email, requester_timezone=a.tz,
            channel=a.channel, duration_minutes=a.duration, topic=a.topic, earliest=a.earliest, latest=a.latest,
            preferred_time_of_day=a.time_of_day,
        )
        _print(service.propose(req, busy=_load_busy(a.busy_file), provider_name=a.provider,
                               lookahead_days=a.days, max_options=a.max, now=a.now))
    elif a.cmd == "check":
        _print(service.check(a.start, a.duration, busy=_load_busy(a.busy_file), client_ref=a.client,
                             provider_name=a.provider, now=a.now))
    elif a.cmd == "confirm":
        _print(service.confirm(a.start, a.duration, client_ref=a.client, attendee_emails=a.attendee, topic=a.topic,
                               recipient_name=a.name, channel=a.channel, busy=_load_busy(a.busy_file),
                               create=a.create, provider_name=a.provider, now=a.now))
    elif a.cmd == "convert":
        target = resolve_zone(a.to)
        end = a.time.__class__.fromtimestamp(a.time.timestamp() + a.duration * 60, tz=target)
        _print({
            "input": a.time.isoformat(),
            "converted": convert(a.time, target).isoformat(),
            "label": format_slot(a.time, end, str(target.key), str(a.time.tzinfo) if a.time.tzinfo else None),
            "zone_label": label(target, a.time),
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
