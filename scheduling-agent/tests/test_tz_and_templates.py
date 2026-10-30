from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from conftest import ET, et
from scheduler import tz
from scheduler.models import Slot
from scheduler.templates import render_confirmation, render_proposal


def test_resolve_zone_accepts_iana_windows_and_aliases():
    assert tz.resolve_zone("America/Chicago").key == "America/Chicago"
    assert tz.resolve_zone("Eastern Standard Time").key == "America/New_York"
    assert tz.resolve_zone("PT").key == "America/Los_Angeles"
    assert tz.resolve_zone("gmt").key == "Europe/London"
    with pytest.raises(ValueError):
        tz.resolve_zone("Mars/Olympus")


def test_to_windows_roundtrip_and_fallback():
    assert tz.to_windows("America/New_York") == "Eastern Standard Time"
    assert tz.to_windows("Asia/Kolkata") == "India Standard Time"
    assert tz.to_windows("America/Argentina/Buenos_Aires") == "America/Argentina/Buenos_Aires"  # Graph also takes IANA


def test_labels_are_season_neutral_for_us_zones():
    assert tz.label("America/New_York") == "ET"
    assert tz.label("America/Los_Angeles") == "PT"
    assert tz.label("Asia/Dubai", et(2026, 11, 2, 9)) == "+04"


def test_format_slot_dual_zone():
    start = et(2026, 11, 3, 14)
    text = tz.format_slot(start, start + timedelta(minutes=30), "America/Los_Angeles", "America/New_York")
    assert text == "Tue, Nov 3 · 11:00–11:30 AM PT (2:00–2:30 PM ET)"


def test_format_slot_marks_day_rollover():
    start = et(2026, 11, 3, 16)  # 4pm ET Tue = 8am Wed in Sydney
    text = tz.format_slot(start, start + timedelta(minutes=30), "America/New_York", "Australia/Sydney")
    assert text.startswith("Tue, Nov 3 · 4:00–4:30 PM ET (8:00–8:30 AM AEST/AEDT Wed)")


def test_format_slot_collapses_am_pm_only_when_same():
    start = et(2026, 11, 3, 11, 30)
    assert "11:30 AM–12:00 PM ET" in tz.format_slot(start, start + timedelta(minutes=30), "America/New_York")


def test_render_proposal_email_and_slack(prefs):
    slots = [Slot(start=et(2026, 11, 3, 14), end=et(2026, 11, 3, 14, 30)),
             Slot(start=et(2026, 11, 4, 10), end=et(2026, 11, 4, 10, 30))]
    email = render_proposal(slots, prefs, channel="email", recipient_name="Jane Doe", client=None,
                            client_zone="America/Los_Angeles", duration=30, topic="kickoff")
    assert email.startswith("Hi Jane,")
    assert "• Tue, Nov 3 · 11:00–11:30 AM PT (2:00–2:30 PM ET)" in email
    assert "• Wed, Nov 4 · 7:00–7:30 AM PT (10:00–10:30 AM ET)" in email
    assert email.rstrip().endswith("Thanks,\nMichael")
    slack = render_proposal(slots, prefs, channel="slack", recipient_name=None, client=None,
                            client_zone="America/Los_Angeles", duration=30, topic=None)
    assert slack.startswith("Hey there!") and "a call" in slack and "Teams invite" in slack


def test_render_none_available(prefs):
    text = render_proposal([], prefs, channel="email", recipient_name="Raj Patel", client=None,
                           client_zone="America/Los_Angeles", duration=45, topic=None)
    assert "Hi Raj" in text and "45-minute" in text


def test_render_confirmation(prefs):
    slot = Slot(start=et(2026, 11, 3, 14), end=et(2026, 11, 3, 14, 30))
    text = render_confirmation(slot, prefs, channel="email", recipient_name="Jane Doe", client_zone="America/Los_Angeles")
    assert "We are set for Tue, Nov 3 · 11:00–11:30 AM PT (2:00–2:30 PM ET)." in text
    assert "Teams invite" in text
