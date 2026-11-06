import asyncio
import json
from datetime import datetime, timezone

from conftest import ET, ROOT, et
from scheduler import service
from scheduler.config import find_client, load_clients, load_preferences
from scheduler.models import MeetingRequest

GRAPH_BUSY = [  # what the Microsoft 365 connector / calendarView returns
    {"subject": "Standup", "start": {"dateTime": "2026-11-02T15:00:00.0000000", "timeZone": "UTC"},
     "end": {"dateTime": "2026-11-02T16:00:00.0000000", "timeZone": "UTC"}, "showAs": "busy"},
    {"subject": "Focus", "start": {"dateTime": "2026-11-03T00:00:00.0000000", "timeZone": "Eastern Standard Time"},
     "end": {"dateTime": "2026-11-04T00:00:00.0000000", "timeZone": "Eastern Standard Time"}, "showAs": "free",
     "isAllDay": True},
]


def test_clients_load_both_layouts_and_match_by_email_domain():
    clients = load_clients(ROOT / "clients")
    ids = {c.id for c in clients}
    assert {"acme-corp", "globex-industries"} <= ids
    globex = find_client("globex", clients)
    assert globex.customer == "Globex Industries" and globex.timezone == "Europe/London"
    assert find_client("someone@acme.example", clients).id == "acme-corp"
    assert find_client("oliver", clients).id == "globex-industries"
    assert find_client("nobody", clients) is None


def test_preferences_file_loads():
    p = load_preferences(ROOT / "preferences.yaml")
    assert p.owner.timezone == "America/New_York" and p.scheduling.buffer_minutes == 30


def test_propose_with_graph_shaped_busy_and_client_profile(prefs, now):
    req = MeetingRequest(client_id="acme", requester_name="Jane Doe", channel="email", topic="kickoff")
    out = service.propose(req, busy=GRAPH_BUSY, prefs=prefs, now=now, lookahead_days=5)
    assert out.client_id == "acme-corp" and out.client_timezone == "America/Los_Angeles"
    assert out.duration_minutes == 30 and 1 <= len(out.slots) <= 4
    assert out.draft.startswith("Hi Jane,") and "PT (" in out.draft
    # standup Mon 10-11 ET: nothing between 9:30 and 11:30 ET on Monday
    for s in out.slots:
        local = s.start.astimezone(ET)
        if local.date().isoformat() == "2026-11-02":
            assert not (datetime(2026, 11, 2, 9, 30, tzinfo=ET) <= local < datetime(2026, 11, 2, 11, 30, tzinfo=ET))
            assert local.hour >= 11  # Acme opens 8:30 PT = 11:30 ET
    assert out.warnings == []


def test_propose_unknown_client_warns_and_defaults(prefs, now):
    out = service.propose(MeetingRequest(client_id="unknown-co", requester_name="X"), busy=[], prefs=prefs, now=now)
    assert any("No client profile" in w for w in out.warnings)
    assert out.client_timezone == "America/New_York"


def test_propose_without_busy_and_provider_none_treats_calendar_empty(prefs, now, monkeypatch):
    monkeypatch.setenv("SCHEDULER_PROVIDER", "none")
    out = service.propose(MeetingRequest(requester_name="X"), prefs=prefs, now=now)
    assert len(out.slots) == 4 and any("treating the calendar as empty" in w for w in out.warnings)


def test_confirm_builds_graph_payload_and_refuses_bad_times(prefs, now):
    good = service.confirm(et(2026, 11, 3, 14), 30, client_ref="acme", attendee_emails=["jane.doe@acme.example"],
                           topic="Kickoff", recipient_name="Jane Doe", busy=GRAPH_BUSY, prefs=prefs, now=now)
    assert good["ok"] and good["problems"] == []
    payload = good["event_payload"]
    assert payload["subject"] == "Acme <> Our Team: Kickoff"
    assert payload["start"] == {"dateTime": "2026-11-03T14:00:00", "timeZone": "Eastern Standard Time"}
    assert payload["end"]["dateTime"] == "2026-11-03T14:30:00"
    assert payload["isOnlineMeeting"] is True and payload["onlineMeetingProvider"] == "teamsForBusiness"
    assert payload["attendees"] == [{"emailAddress": {"address": "jane.doe@acme.example"}, "type": "required"}]
    assert payload["transactionId"]
    assert "11:00–11:30 AM PT" in good["confirmation_reply"]

    bad = service.confirm(et(2026, 11, 2, 11), 30, client_ref="acme", attendee_emails=["jane.doe@acme.example"],
                          busy=GRAPH_BUSY, prefs=prefs, now=now, create=True)
    assert not bad["ok"] and bad["created"]["error"].startswith("refused")


def test_confirm_create_with_mock_provider_writes_event(prefs, now, tmp_path, monkeypatch):
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({"events": []}))
    monkeypatch.setenv("SCHEDULER_MOCK_CALENDAR", str(cal))
    out = service.confirm(et(2026, 11, 3, 14), 30, client_ref="acme", attendee_emails=["jane.doe@acme.example"],
                          prefs=prefs, now=now, create=True, provider_name="mock")
    assert out["created"]["invitesSent"] and out["created"]["onlineMeeting"]["joinUrl"]
    saved = json.loads(cal.read_text())["events"]
    assert len(saved) == 1 and saved[0]["start"] == "2026-11-03T19:00:00+00:00"
    # And now that time is taken: proposing again must avoid it and its buffer.
    again = service.check(et(2026, 11, 3, 14, 30), 30, client_ref="acme", prefs=prefs, now=now, provider_name="mock")
    assert not again["ok"]


def test_mcp_server_exposes_tools():
    from scheduler import mcp_server

    tools = asyncio.run(mcp_server.server.list_tools())
    names = {t.name for t in tools}
    assert names == {"list_clients", "propose_times", "check_time", "confirm_meeting", "convert_time"}
    schema = next(t for t in tools if t.name == "propose_times").input_schema
    assert "busy" in schema["properties"] and "client" in schema["properties"]


def test_mcp_convert_time_tool():
    from scheduler import mcp_server

    out = mcp_server.convert_time("2026-11-03T14:00:00-05:00", "Europe/London")
    assert out["converted"] == "2026-11-03T19:00:00+00:00" and out["zone_label"] == "UK time"


def test_cli_propose_and_check(capsys, now):
    from scheduler import cli

    rc = cli.main(["propose", "--client", "globex", "--name", "Oliver Hughes", "--channel", "slack",
                   "--provider", "none", "--now", now.isoformat()])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["client_timezone"] == "Europe/London" and data["duration_minutes"] == 45
    assert data["draft"].startswith("Hey Oliver!")
    for lbl in data["slot_labels"]:
        assert "UK time" in lbl and "ET" in lbl

    rc = cli.main(["check", "--start", "2026-11-07T10:00:00-05:00", "--provider", "none", "--now", now.isoformat()])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
