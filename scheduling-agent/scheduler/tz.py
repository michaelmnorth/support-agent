"""Time zone helpers: IANA <-> Windows names (Microsoft Graph), friendly labels, dual-zone formatting."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Graph accepts Windows time zone names in event start/end and in the Prefer: outlook.timezone header.
# It also accepts IANA names in most places, but Windows names are the safest round-trip.
IANA_TO_WINDOWS: dict[str, str] = {
    "America/New_York": "Eastern Standard Time",
    "America/Detroit": "Eastern Standard Time",
    "America/Toronto": "Eastern Standard Time",
    "America/Chicago": "Central Standard Time",
    "America/Winnipeg": "Central Standard Time",
    "America/Denver": "Mountain Standard Time",
    "America/Edmonton": "Mountain Standard Time",
    "America/Phoenix": "US Mountain Standard Time",
    "America/Los_Angeles": "Pacific Standard Time",
    "America/Vancouver": "Pacific Standard Time",
    "America/Anchorage": "Alaskan Standard Time",
    "Pacific/Honolulu": "Hawaiian Standard Time",
    "America/Halifax": "Atlantic Standard Time",
    "America/Sao_Paulo": "E. South America Standard Time",
    "America/Mexico_City": "Central Standard Time (Mexico)",
    "America/Bogota": "SA Pacific Standard Time",
    "UTC": "UTC",
    "Etc/UTC": "UTC",
    "Europe/London": "GMT Standard Time",
    "Europe/Dublin": "GMT Standard Time",
    "Europe/Lisbon": "GMT Standard Time",
    "Europe/Paris": "Romance Standard Time",
    "Europe/Madrid": "Romance Standard Time",
    "Europe/Berlin": "W. Europe Standard Time",
    "Europe/Amsterdam": "W. Europe Standard Time",
    "Europe/Rome": "W. Europe Standard Time",
    "Europe/Zurich": "W. Europe Standard Time",
    "Europe/Stockholm": "W. Europe Standard Time",
    "Europe/Warsaw": "Central European Standard Time",
    "Europe/Athens": "GTB Standard Time",
    "Europe/Istanbul": "Turkey Standard Time",
    "Europe/Moscow": "Russian Standard Time",
    "Africa/Johannesburg": "South Africa Standard Time",
    "Africa/Lagos": "W. Central Africa Standard Time",
    "Africa/Cairo": "Egypt Standard Time",
    "Asia/Dubai": "Arabian Standard Time",
    "Asia/Kolkata": "India Standard Time",
    "Asia/Calcutta": "India Standard Time",
    "Asia/Karachi": "Pakistan Standard Time",
    "Asia/Dhaka": "Bangladesh Standard Time",
    "Asia/Bangkok": "SE Asia Standard Time",
    "Asia/Jakarta": "SE Asia Standard Time",
    "Asia/Singapore": "Singapore Standard Time",
    "Asia/Manila": "Singapore Standard Time",
    "Asia/Hong_Kong": "China Standard Time",
    "Asia/Shanghai": "China Standard Time",
    "Asia/Taipei": "Taipei Standard Time",
    "Asia/Seoul": "Korea Standard Time",
    "Asia/Tokyo": "Tokyo Standard Time",
    "Australia/Perth": "W. Australia Standard Time",
    "Australia/Adelaide": "Cen. Australia Standard Time",
    "Australia/Brisbane": "E. Australia Standard Time",
    "Australia/Sydney": "AUS Eastern Standard Time",
    "Australia/Melbourne": "AUS Eastern Standard Time",
    "Pacific/Auckland": "New Zealand Standard Time",
}
WINDOWS_TO_IANA: dict[str, str] = {}
for _iana, _win in IANA_TO_WINDOWS.items():
    WINDOWS_TO_IANA.setdefault(_win, _iana)

# People say "ET" / "PT", not "EST" / "EDT". Map common zones to a season-neutral label.
FRIENDLY_LABEL: dict[str, str] = {
    "America/New_York": "ET",
    "America/Detroit": "ET",
    "America/Toronto": "ET",
    "America/Chicago": "CT",
    "America/Winnipeg": "CT",
    "America/Denver": "MT",
    "America/Edmonton": "MT",
    "America/Phoenix": "MST (Arizona)",
    "America/Los_Angeles": "PT",
    "America/Vancouver": "PT",
    "America/Anchorage": "AKT",
    "Pacific/Honolulu": "HST",
    "Europe/London": "UK time",
    "Europe/Dublin": "Irish time",
    "Europe/Paris": "CET",
    "Europe/Berlin": "CET",
    "Europe/Madrid": "CET",
    "Europe/Amsterdam": "CET",
    "Asia/Kolkata": "IST",
    "Asia/Singapore": "SGT",
    "Asia/Tokyo": "JST",
    "Australia/Sydney": "AEST/AEDT",
    "UTC": "UTC",
}

# Loose aliases people type. Keys are lowercase.
ALIASES: dict[str, str] = {
    "et": "America/New_York", "est": "America/New_York", "edt": "America/New_York", "eastern": "America/New_York",
    "ct": "America/Chicago", "cst": "America/Chicago", "cdt": "America/Chicago", "central": "America/Chicago",
    "mt": "America/Denver", "mst": "America/Denver", "mdt": "America/Denver", "mountain": "America/Denver",
    "arizona": "America/Phoenix",
    "pt": "America/Los_Angeles", "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pacific": "America/Los_Angeles",
    "akst": "America/Anchorage", "hst": "Pacific/Honolulu",
    "gmt": "Europe/London", "bst": "Europe/London", "uk": "Europe/London", "london": "Europe/London",
    "cet": "Europe/Paris", "cest": "Europe/Paris",
    "ist": "Asia/Kolkata", "india": "Asia/Kolkata",
    "sgt": "Asia/Singapore", "jst": "Asia/Tokyo", "aest": "Australia/Sydney", "aedt": "Australia/Sydney",
    "utc": "UTC", "z": "UTC",
}


def resolve_zone(name: str) -> ZoneInfo:
    """Accept an IANA name, a Windows name, or a loose alias like 'PT' and return a ZoneInfo."""
    if not name:
        raise ValueError("empty time zone")
    candidate = name.strip()
    if candidate in WINDOWS_TO_IANA:
        candidate = WINDOWS_TO_IANA[candidate]
    elif candidate.lower() in ALIASES:
        candidate = ALIASES[candidate.lower()]
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError as e:
        raise ValueError(f"unknown time zone: {name!r}") from e


def to_windows(iana: str) -> str:
    """Windows zone name for Graph. Falls back to the IANA name, which Graph also accepts."""
    key = str(resolve_zone(iana).key)
    return IANA_TO_WINDOWS.get(key, key)


def label(zone: ZoneInfo | str, at: datetime | None = None) -> str:
    """Season-neutral label where we know one ('ET'), else the zone's abbreviation at that moment."""
    z = zone if isinstance(zone, ZoneInfo) else resolve_zone(zone)
    if z.key in FRIENDLY_LABEL:
        return FRIENDLY_LABEL[z.key]
    moment = at or datetime.now(z)
    return moment.astimezone(z).tzname() or z.key


def convert(dt: datetime, zone: ZoneInfo | str) -> datetime:
    z = zone if isinstance(zone, ZoneInfo) else resolve_zone(zone)
    if dt.tzinfo is None:
        raise ValueError("cannot convert a naive datetime")
    return dt.astimezone(z)


def _fmt_time(dt: datetime) -> str:
    # 9:00 AM, 2:30 PM. No leading zero; Windows strftime lacks %-I so do it by hand.
    hour12 = dt.hour % 12 or 12
    return f"{hour12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _fmt_range(start: datetime, end: datetime) -> str:
    s, e = _fmt_time(start), _fmt_time(end)
    # Collapse the first AM/PM when both match: "2:00-2:30 PM"
    if s[-2:] == e[-2:]:
        s = s[:-3]
    return f"{s}–{e}"


def format_slot(start: datetime, end: datetime, primary_zone: str, secondary_zone: str | None = None,
                show_both: bool = True) -> str:
    """'Tue, Nov 3 - 11:00-11:30 AM PT (2:00-2:30 PM ET)'. Primary zone leads; date is the primary zone's date."""
    p = resolve_zone(primary_zone)
    ps, pe = start.astimezone(p), end.astimezone(p)
    text = f"{ps.strftime('%a, %b')} {ps.day} · {_fmt_range(ps, pe)} {label(p, ps)}"
    if show_both and secondary_zone:
        s = resolve_zone(secondary_zone)
        if s.key != p.key:
            ss, se = start.astimezone(s), end.astimezone(s)
            day_note = ""
            if ss.date() != ps.date():
                day_note = f" {ss.strftime('%a')}"
            text += f" ({_fmt_range(ss, se)} {label(s, ss)}{day_note})"
    return text


def utc_offset_hours(zone: str, at: datetime) -> float:
    off = at.astimezone(resolve_zone(zone)).utcoffset()
    return (off.total_seconds() / 3600.0) if off else 0.0
