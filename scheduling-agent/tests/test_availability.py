from datetime import datetime, timedelta, timezone

from conftest import ET, PT, UTC, busy, et
from scheduler import availability as av
from scheduler.models import ClientProfile, MeetingDefaults


def starts_local(slots):
    return sorted(s.start.astimezone(ET).strftime("%a %H:%M") for s in slots)


def window(day_start: datetime, days=1):
    return day_start, day_start + timedelta(days=days)


# ---------- interval primitives ----------------------------------------------------------------

def test_merge_and_pad_combine_back_to_back_meetings():
    a = av.Interval(et(2026, 11, 2, 10), et(2026, 11, 2, 11))
    b = av.Interval(et(2026, 11, 2, 11), et(2026, 11, 2, 12))
    merged = av.merge([b, a])
    assert merged == [av.Interval(et(2026, 11, 2, 10), et(2026, 11, 2, 12))]
    padded = av.pad(merged, 30)
    assert padded[0].start == et(2026, 11, 2, 9, 30) and padded[0].end == et(2026, 11, 2, 12, 30)


def test_subtract_splits_and_clips():
    base = [av.Interval(et(2026, 11, 2, 9), et(2026, 11, 2, 17))]
    blockers = [av.Interval(et(2026, 11, 2, 8), et(2026, 11, 2, 9, 30)),
                av.Interval(et(2026, 11, 2, 12), et(2026, 11, 2, 13)),
                av.Interval(et(2026, 11, 2, 16, 30), et(2026, 11, 2, 18))]
    free = av.subtract(base, blockers)
    assert free == [av.Interval(et(2026, 11, 2, 9, 30), et(2026, 11, 2, 12)),
                    av.Interval(et(2026, 11, 2, 13), et(2026, 11, 2, 16, 30))]


# ---------- the 30-minute buffer rule -----------------------------------------------------------

def test_buffer_excludes_30_min_either_side(prefs, now):
    meeting = busy(et(2026, 11, 2, 10), et(2026, 11, 2, 11), subject="standup")
    slots = av.find_free_slots([meeting], prefs, 30, *window(et(2026, 11, 2, 0)), now=now)
    starts = starts_local(slots)
    # 9:00-9:30 ends exactly when the buffer starts (9:30): allowed. 11:30 starts exactly when buffer ends: allowed.
    assert "Mon 09:00" in starts and "Mon 11:30" in starts
    for forbidden in ("Mon 09:30", "Mon 10:00", "Mon 10:30", "Mon 11:00"):
        assert forbidden not in starts, forbidden


def test_longer_meeting_needs_room_before_buffer(prefs, now):
    meeting = busy(et(2026, 11, 2, 10), et(2026, 11, 2, 11))
    slots = av.find_free_slots([meeting], prefs, 60, *window(et(2026, 11, 2, 0)), now=now)
    starts = starts_local(slots)
    assert "Mon 09:00" not in starts  # 9:00-10:00 would touch the 9:30 buffer
    assert "Mon 11:30" in starts


def test_tentative_respected_by_default_and_can_be_ignored(prefs, now):
    tent = busy(et(2026, 11, 2, 10), et(2026, 11, 2, 11), show_as="tentative")
    assert "Mon 10:00" not in starts_local(av.find_free_slots([tent], prefs, 30, *window(et(2026, 11, 2, 0)), now=now))
    prefs.scheduling.treat_tentative_as_busy = False
    assert "Mon 10:00" in starts_local(av.find_free_slots([tent], prefs, 30, *window(et(2026, 11, 2, 0)), now=now))


def test_free_and_cancelled_events_do_not_block(prefs, now):
    free_allday = busy(et(2026, 11, 2, 0), et(2026, 11, 3, 0), show_as="free", is_all_day=True)
    cancelled = busy(et(2026, 11, 2, 10), et(2026, 11, 2, 11), is_cancelled=True)
    slots = av.find_free_slots([free_allday, cancelled], prefs, 30, *window(et(2026, 11, 2, 0)), now=now)
    assert "Mon 10:00" in starts_local(slots)


def test_oof_all_day_blocks_whole_day(prefs, now):
    pto = busy(et(2026, 11, 6, 0), et(2026, 11, 7, 0), show_as="oof", is_all_day=True)
    assert av.find_free_slots([pto], prefs, 30, *window(et(2026, 11, 6, 0)), now=now) == []


# ---------- working hours, lead time, blocks ----------------------------------------------------

def test_only_inside_working_hours_and_never_on_weekends(prefs, now):
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0), days=7), now=now)
    locals_ = [s.start.astimezone(ET) for s in slots]
    assert all(9 <= d.hour < 17 for d in locals_)
    assert all(d.weekday() < 5 for d in locals_)
    assert all((s.end.astimezone(ET).hour, s.end.astimezone(ET).minute) <= (17, 0) for s in slots)


def test_lead_time_blocks_the_next_24h(prefs):
    now = et(2026, 11, 2, 8)  # Monday 8am
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0), days=2), now=now)
    first = min(s.start for s in slots)
    assert first >= et(2026, 11, 3, 8)
    assert first.astimezone(ET).strftime("%a %H:%M") == "Tue 09:00"


def test_daily_block_and_skip_dates(prefs, now):
    prefs.scheduling.daily_blocks = ["12:00-13:00"]
    prefs.scheduling.skip_dates = ["2026-11-03"]
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0), days=2), now=now)
    starts = starts_local(slots)
    assert "Mon 12:00" not in starts and "Mon 12:30" not in starts and "Mon 11:30" in starts and "Mon 13:00" in starts
    assert not any(s.startswith("Tue") for s in starts)


def test_earliest_and_latest_constraints(prefs, now):
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0), days=3), now=now,
                               earliest=et(2026, 11, 3, 14), latest=et(2026, 11, 3, 16))
    assert starts_local(slots) == ["Tue 14:00", "Tue 14:30", "Tue 15:00", "Tue 15:30"]


# ---------- time zones -----------------------------------------------------------------------------

def test_client_working_hours_intersect_in_their_zone(prefs, now):
    client = ClientProfile(id="acme", customer="Acme", timezone="America/Los_Angeles",
                           meeting_defaults=MeetingDefaults(client_working_hours="08:30-17:00"))
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0)), now=now, client=client)
    starts = starts_local(slots)
    # 08:30 PT = 11:30 ET (both on standard time after Nov 1). Owner stops at 17:00 ET.
    assert starts[0] == "Mon 11:30" and starts[-1] == "Mon 16:30"


def test_uk_client_limits_to_morning_eastern(prefs, now):
    client = ClientProfile(id="globex", customer="Globex", timezone="Europe/London",
                           meeting_defaults=MeetingDefaults(client_working_hours="09:00-17:30"))
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0)), now=now, client=client)
    starts = starts_local(slots)
    # 17:30 UK = 12:30 ET in November (UK on GMT, US on EST). Last 30-min start is 12:00 ET.
    assert starts == ["Mon 09:00", "Mon 09:30", "Mon 10:00", "Mon 10:30", "Mon 11:00", "Mon 11:30", "Mon 12:00"]


def test_slots_stay_aligned_across_us_dst_change(prefs):
    now = et(2026, 10, 28, 9)
    slots = av.find_free_slots([], prefs, 30, et(2026, 10, 30, 0), et(2026, 11, 3, 0), now=now)
    fri = [s for s in slots if s.start.astimezone(ET).weekday() == 4]
    mon = [s for s in slots if s.start.astimezone(ET).weekday() == 0]
    assert fri[0].start == datetime(2026, 10, 30, 13, 0, tzinfo=UTC)  # 9:00 EDT
    assert mon[0].start == datetime(2026, 11, 2, 14, 0, tzinfo=UTC)   # 9:00 EST
    assert all(s.start.astimezone(ET).minute in (0, 30) for s in slots)


def test_morning_preference_judged_in_client_zone(prefs, now):
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0)), now=now,
                               client_timezone="America/Los_Angeles", time_of_day="morning")
    # Morning in PT ends 12:00 PT = 15:00 ET, so the last start is 14:30 ET.
    assert starts_local(slots)[-1] == "Mon 14:30"
    assert starts_local(slots)[0] == "Mon 09:00"


# ---------- shortlist -----------------------------------------------------------------------------

def test_shortlist_spreads_across_days_then_fills(prefs, now):
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0), days=5), now=now)
    picks = av.shortlist(slots, prefs, max_options=4, max_per_day=2)
    days = {s.start.astimezone(ET).date() for s in picks}
    assert len(picks) == 4 and len(days) == 4  # four different days first
    picks6 = av.shortlist(slots, prefs, max_options=6, max_per_day=2)
    assert len(picks6) == 6 and len({s.start.astimezone(ET).date() for s in picks6}) == 5


def test_shortlist_same_day_options_are_hours_apart(prefs, now):
    prefs.scheduling.min_gap_between_options_hours = 3
    slots = av.find_free_slots([], prefs, 30, *window(et(2026, 11, 2, 0)), now=now)
    picks = av.shortlist(slots, prefs, max_options=2, max_per_day=2)
    assert len(picks) == 2 and picks[1].start - picks[0].start >= timedelta(hours=3)


# ---------- validating a time proposed by the other side ------------------------------------------

def test_check_slot_reports_each_violation(prefs, now):
    meeting = busy(et(2026, 11, 2, 10), et(2026, 11, 2, 11))
    assert av.check_slot(et(2026, 11, 2, 13), 30, [meeting], prefs, now=now) == []
    problems = av.check_slot(et(2026, 11, 2, 11), 30, [meeting], prefs, now=now)
    assert any("within 30 min" in p for p in problems)
    assert any("outside working hours" in p for p in av.check_slot(et(2026, 11, 2, 18), 30, [], prefs, now=now))
    assert any("weekend" in p or "outside working hours" in p for p in av.check_slot(et(2026, 11, 7, 10), 30, [], prefs, now=now))
    assert any("lead time" in p for p in av.check_slot(et(2026, 10, 30, 15), 30, [], prefs, now=now))
    client = ClientProfile(id="g", customer="G", timezone="Europe/London",
                           meeting_defaults=MeetingDefaults(client_working_hours="09:00-17:30"))
    assert any("client's hours" in p for p in av.check_slot(et(2026, 11, 2, 15), 30, [], prefs, client=client, now=now))
