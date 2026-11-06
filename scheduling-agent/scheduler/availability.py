"""Free-slot computation. Pure functions, no I/O, fully unit-tested.

Rules implemented here (so they can never be "forgotten" by the model):
  * Every busy block is padded by `buffer_minutes` on both sides. Nothing is offered inside the padded block.
  * Only inside the owner's working hours (per weekday, owner zone), minus daily blocks (lunch) and skip dates.
  * Optionally also inside the client's working hours in the client's zone.
  * Never sooner than `min_lead_time_hours` from now, never before `earliest` / after `latest` if given.
  * Slot starts land on `slot_granularity_minutes` boundaries in the owner's local time.
  * The final shortlist is spread across days (max_per_day, min gap between options, max_options).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

from .models import BusyBlock, ClientProfile, Preferences, Slot
from .tz import resolve_zone

UTC = timezone.utc


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"interval end before start: {self}")

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60

    def intersect(self, other: "Interval") -> Optional["Interval"]:
        s, e = max(self.start, other.start), min(self.end, other.end)
        return Interval(s, e) if s < e else None


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Union of intervals, sorted, touching/overlapping ones merged."""
    out: list[Interval] = []
    for iv in sorted(intervals, key=lambda i: i.start):
        if out and iv.start <= out[-1].end:
            out[-1] = Interval(out[-1].start, max(out[-1].end, iv.end))
        else:
            out.append(iv)
    return out


def pad(intervals: Iterable[Interval], minutes: int) -> list[Interval]:
    d = timedelta(minutes=minutes)
    return merge(Interval(i.start - d, i.end + d) for i in intervals)


def subtract(base: Sequence[Interval], blockers: Sequence[Interval]) -> list[Interval]:
    """base minus blockers, as a sorted list of what is left."""
    result: list[Interval] = []
    blocked = merge(blockers)
    for b in merge(base):
        cursor = b.start
        for blk in blocked:
            if blk.end <= cursor:
                continue
            if blk.start >= b.end:
                break
            if blk.start > cursor:
                result.append(Interval(cursor, blk.start))
            cursor = max(cursor, blk.end)
            if cursor >= b.end:
                break
        if cursor < b.end:
            result.append(Interval(cursor, b.end))
    return result


def intersect_all(a: Sequence[Interval], b: Sequence[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for x in merge(a):
        for y in merge(b):
            hit = x.intersect(y)
            if hit:
                out.append(hit)
    return merge(out)


def _parse_range(spec: str) -> tuple[time, time]:
    try:
        a, b = spec.replace(" ", "").split("-")
        h1, m1 = (int(x) for x in a.split(":"))
        h2, m2 = (int(x) for x in b.split(":"))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"bad time range {spec!r}; expected 'HH:MM-HH:MM'") from e
    return time(h1, m1), time(h2, m2)


def day_ranges(day: date, specs: Sequence[str], zone: ZoneInfo) -> list[Interval]:
    """'09:00-17:00' strings on a given local date in `zone`, as UTC intervals (DST-safe)."""
    out: list[Interval] = []
    for spec in specs:
        t1, t2 = _parse_range(spec)
        start = datetime.combine(day, t1, tzinfo=zone)
        end = datetime.combine(day, t2, tzinfo=zone)
        if end <= start:  # crosses midnight
            end += timedelta(days=1)
        out.append(Interval(start.astimezone(UTC), end.astimezone(UTC)))
    return out


def busy_intervals(blocks: Iterable[BusyBlock], treat_tentative_as_busy: bool) -> list[Interval]:
    out: list[Interval] = []
    for b in blocks:
        if not b.blocks_time(treat_tentative_as_busy):
            continue
        out.append(Interval(b.start.astimezone(UTC), b.end.astimezone(UTC)))
    return merge(out)


def _ceil_to_granularity(dt_local: datetime, granularity: int) -> datetime:
    """Round a local datetime up to the next HH:MM boundary that is a multiple of `granularity` minutes."""
    minutes_into_day = dt_local.hour * 60 + dt_local.minute
    remainder = minutes_into_day % granularity
    has_subminute = dt_local.second or dt_local.microsecond
    if remainder == 0 and not has_subminute:
        return dt_local.replace(second=0, microsecond=0)
    bump = granularity - remainder if remainder else granularity
    base = dt_local.replace(second=0, microsecond=0)
    return base + timedelta(minutes=bump)


def enumerate_slots(free: Sequence[Interval], duration_minutes: int, granularity: int, owner_zone: ZoneInfo) -> list[Slot]:
    """Every start on a local granularity boundary where start+duration fits in a free interval."""
    dur = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=granularity)
    slots: list[Slot] = []
    for iv in free:
        local_start = _ceil_to_granularity(iv.start.astimezone(owner_zone), granularity)
        cursor = local_start.astimezone(UTC)
        while cursor + dur <= iv.end:
            slots.append(Slot(start=cursor, end=cursor + dur))
            # step in local time so DST transitions keep :00/:30 alignment
            cursor = (cursor.astimezone(owner_zone) + step).astimezone(UTC)
    return slots


def find_free_slots(
    busy: Iterable[BusyBlock],
    prefs: Preferences,
    duration_minutes: int,
    window_start: datetime,
    window_end: datetime,
    *,
    now: Optional[datetime] = None,
    client: Optional[ClientProfile] = None,
    client_timezone: Optional[str] = None,
    earliest: Optional[datetime] = None,
    latest: Optional[datetime] = None,
    time_of_day: Optional[str] = None,
) -> list[Slot]:
    """All valid slots (not yet shortlisted). Inputs may be any aware datetimes; output is UTC."""
    rules = prefs.scheduling
    owner_zone = resolve_zone(prefs.owner.timezone)
    now = (now or datetime.now(UTC)).astimezone(UTC)
    window_start = window_start.astimezone(UTC)
    window_end = window_end.astimezone(UTC)

    # 1. Owner working hours across every local date touched by the window.
    first_day = window_start.astimezone(owner_zone).date() - timedelta(days=1)
    last_day = window_end.astimezone(owner_zone).date() + timedelta(days=1)
    working: list[Interval] = []
    blocks: list[Interval] = []
    d = first_day
    while d <= last_day:
        if d.isoformat() not in rules.skip_dates:
            working += day_ranges(d, prefs.working_hours.for_weekday(d.weekday()), owner_zone)
        blocks += day_ranges(d, rules.daily_blocks, owner_zone)
        d += timedelta(days=1)
    working = intersect_all(working, [Interval(window_start, window_end)])

    # 2. Client working hours, in the client's zone, if the profile specifies them.
    cz_name = client_timezone or (client.timezone if client else None)
    client_hours = client.meeting_defaults.client_working_hours if client else None
    if cz_name and client_hours:
        cz = resolve_zone(cz_name)
        cw: list[Interval] = []
        d = window_start.astimezone(cz).date() - timedelta(days=1)
        stop = window_end.astimezone(cz).date() + timedelta(days=1)
        while d <= stop:
            if d.weekday() < 5:  # client weekdays; refine later if a client works weekends
                cw += day_ranges(d, [client_hours], cz)
            d += timedelta(days=1)
        working = intersect_all(working, cw)

    # 3. Morning / afternoon preference, judged in the CLIENT's zone when we know it (it is their day).
    if time_of_day in ("morning", "afternoon"):
        pref_zone = resolve_zone(cz_name) if cz_name else owner_zone
        spec = ["00:00-12:00"] if time_of_day == "morning" else ["12:00-23:59"]
        pw: list[Interval] = []
        d = window_start.astimezone(pref_zone).date() - timedelta(days=1)
        stop = window_end.astimezone(pref_zone).date() + timedelta(days=1)
        while d <= stop:
            pw += day_ranges(d, spec, pref_zone)
            d += timedelta(days=1)
        working = intersect_all(working, pw)

    # 4. Remove padded busy time, daily blocks, and anything too soon / too late.
    padded_busy = pad(busy_intervals(busy, rules.treat_tentative_as_busy), rules.buffer_minutes)
    not_before = now + timedelta(hours=rules.min_lead_time_hours)
    if earliest is not None:
        not_before = max(not_before, earliest.astimezone(UTC))
    too_soon = [Interval(datetime.min.replace(tzinfo=UTC), not_before)]
    too_late = [Interval(latest.astimezone(UTC), datetime.max.replace(tzinfo=UTC))] if latest else []
    free = subtract(working, padded_busy + blocks + too_soon + too_late)

    return enumerate_slots(free, duration_minutes, rules.slot_granularity_minutes, owner_zone)


def shortlist(slots: Sequence[Slot], prefs: Preferences, *, max_options: Optional[int] = None,
              max_per_day: Optional[int] = None) -> list[Slot]:
    """Spread options across days and across the day, so the recipient gets real variety."""
    rules = prefs.scheduling
    max_options = max_options or rules.max_options
    max_per_day = max_per_day or rules.max_per_day
    owner_zone = resolve_zone(prefs.owner.timezone)
    gap = timedelta(hours=rules.min_gap_between_options_hours)

    by_day: dict[date, list[Slot]] = {}
    for s in sorted(slots, key=lambda s: s.start):
        by_day.setdefault(s.start.astimezone(owner_zone).date(), []).append(s)

    per_day_picks: dict[date, list[Slot]] = {}
    for day, day_slots in by_day.items():
        picks: list[Slot] = []
        # Alternate: earliest, then latest, then fill middle. Gives morning + afternoon on the same day.
        ordered = [day_slots[0]] + ([day_slots[-1]] if len(day_slots) > 1 else []) + day_slots[1:-1]
        for cand in ordered:
            if len(picks) >= max_per_day:
                break
            if all(abs(cand.start - p.start) >= gap for p in picks):
                picks.append(cand)
        per_day_picks[day] = sorted(picks, key=lambda s: s.start)

    # Round-robin across days so two days do not hog all options.
    chosen: list[Slot] = []
    round_idx = 0
    while len(chosen) < max_options:
        added = False
        for day in sorted(per_day_picks):
            picks = per_day_picks[day]
            if round_idx < len(picks) and len(chosen) < max_options:
                chosen.append(picks[round_idx])
                added = True
        if not added:
            break
        round_idx += 1
    return sorted(chosen, key=lambda s: s.start)


def check_slot(start: datetime, duration_minutes: int, busy: Iterable[BusyBlock], prefs: Preferences,
               *, client: Optional[ClientProfile] = None, now: Optional[datetime] = None) -> list[str]:
    """Why a specific proposed time is NOT acceptable. Empty list means it is fine.

    Used when the other side proposes a time: we validate instead of trusting the model's arithmetic.
    """
    problems: list[str] = []
    rules = prefs.scheduling
    owner_zone = resolve_zone(prefs.owner.timezone)
    start = start.astimezone(UTC)
    end = start + timedelta(minutes=duration_minutes)
    now = (now or datetime.now(UTC)).astimezone(UTC)

    if start < now + timedelta(hours=rules.min_lead_time_hours):
        problems.append(f"starts sooner than the {rules.min_lead_time_hours:g}h lead time")

    local = start.astimezone(owner_zone)
    if local.date().isoformat() in rules.skip_dates:
        problems.append(f"{local.date()} is a skip date (PTO/holiday)")
    wh = day_ranges(local.date(), prefs.working_hours.for_weekday(local.weekday()), owner_zone)
    if not any(iv.start <= start and end <= iv.end for iv in wh):
        problems.append(f"outside working hours on {local.strftime('%A')} ({prefs.owner.timezone})")
    for blk in day_ranges(local.date(), rules.daily_blocks, owner_zone):
        if blk.intersect(Interval(start, end)):
            problems.append("overlaps a daily block (e.g. lunch)")

    for iv in pad(busy_intervals(busy, rules.treat_tentative_as_busy), rules.buffer_minutes):
        if iv.intersect(Interval(start, end)):
            real_start = (iv.start + timedelta(minutes=rules.buffer_minutes)).astimezone(owner_zone)
            real_end = (iv.end - timedelta(minutes=rules.buffer_minutes)).astimezone(owner_zone)
            problems.append(
                f"within {rules.buffer_minutes} min of an existing meeting "
                f"({real_start:%a %b %d %I:%M %p}–{real_end:%I:%M %p})"
            )
            break

    if client and client.meeting_defaults.client_working_hours:
        cz = resolve_zone(client.timezone)
        cl = start.astimezone(cz)
        if cl.weekday() >= 5:
            problems.append(f"falls on a weekend for the client ({client.timezone})")
        else:
            cw = day_ranges(cl.date(), [client.meeting_defaults.client_working_hours], cz)
            if not any(iv.start <= start and end <= iv.end for iv in cw):
                problems.append(
                    f"outside the client's hours {client.meeting_defaults.client_working_hours} {client.timezone}"
                )
    return problems
