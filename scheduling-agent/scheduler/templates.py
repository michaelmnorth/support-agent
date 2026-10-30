"""Render replies in the owner's format.

Templates live in templates/*.txt and use Python str.format placeholders, so the owner can
edit the wording without touching code. Claude may still rewrite the draft for tone, but the
time lines come from here so they are never mis-converted.

Placeholders available in every template:
  {first_name}       recipient first name (or 'there')
  {owner_first}      owner first name
  {options}          bullet list of slot lines (already formatted, one per line)
  {client_zone}      friendly label for the client's zone, e.g. PT
  {owner_zone}       friendly label for the owner's zone, e.g. ET
  {duration}         e.g. 30
  {topic}            meeting topic or 'a call'
  {bullet}           the bullet character from preferences
  {signoff}          email_signoff or slack_signoff from preferences
  {chosen}           (confirmation only) the single formatted slot
  {teams_note}       (confirmation only) sentence about the Teams invite
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import home
from .models import ClientProfile, Preferences, Slot
from .tz import format_slot, label

DEFAULTS: dict[str, str] = {
    "propose_email": (
        "Hi {first_name},\n\n"
        "Happy to get this on the calendar. Here are a few times that work on my end for {topic} "
        "({duration} min). Times are in {client_zone}, with {owner_zone} in parentheses:\n\n"
        "{options}\n\n"
        "If none of those work, send over a couple of windows that do and I will make it fit. "
        "Once you pick one I will send a Teams invite.\n\n"
        "{signoff}"
    ),
    "propose_slack": (
        "Hey {first_name}! A few times that work for {topic} ({duration} min), in {client_zone} "
        "({owner_zone} in parentheses):\n"
        "{options}\n"
        "Let me know which works and I will send the Teams invite.{signoff}"
    ),
    "propose_teams": (
        "Hi {first_name}, a few options for {topic} ({duration} min), shown in {client_zone} "
        "({owner_zone} in parentheses):\n"
        "{options}\n"
        "Pick whichever is easiest and I will send the invite.{signoff}"
    ),
    "confirm_email": (
        "Hi {first_name},\n\n"
        "Perfect. We are set for {chosen}. {teams_note}\n\n"
        "Talk soon,\n{owner_first}"
    ),
    "confirm_slack": "Locked in: {chosen}. {teams_note}",
    "confirm_teams": "Locked in: {chosen}. {teams_note}",
    "none_available": (
        "Hi {first_name},\n\n"
        "I do not have anything open in that window that fits a {duration}-minute call. "
        "Could you share a couple of times that work on your side (any zone is fine), and I will confirm?\n\n"
        "{signoff}"
    ),
    "owner_ping": (
        "Scheduling request from {requester} ({channel}) for {topic}, {duration} min.\n"
        "Proposed (client zone {client_zone} / yours {owner_zone}):\n{options}\n"
        "Reply 'send' to send the draft, 'edit' to change it, or 'skip'."
    ),
}


def _templates_dir() -> Path:
    return home() / "templates"


def load_template(name: str) -> str:
    p = _templates_dir() / f"{name}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").rstrip("\n")
    return DEFAULTS[name]


def _first_name(full: Optional[str]) -> str:
    if not full:
        return "there"
    return full.strip().split()[0]


def slot_lines(slots: list[Slot], prefs: Preferences, client_zone: Optional[str]) -> list[str]:
    owner_zone = prefs.owner.timezone
    cz = client_zone or owner_zone
    primary, secondary = (cz, owner_zone) if prefs.response.lead_with_client_zone else (owner_zone, cz)
    return [format_slot(s.start, s.end, primary, secondary, show_both=prefs.response.show_both_zones) for s in slots]


def render_proposal(slots: list[Slot], prefs: Preferences, *, channel: str, recipient_name: Optional[str],
                    client: Optional[ClientProfile], client_zone: Optional[str], duration: int,
                    topic: Optional[str]) -> str:
    cz = client_zone or (client.timezone if client else prefs.owner.timezone)
    lines = slot_lines(slots, prefs, cz)
    bullet = prefs.response.list_bullet
    options = "\n".join(f"{bullet} {ln}" for ln in lines)
    signoff = prefs.response.email_signoff if channel == "email" else prefs.response.slack_signoff
    if channel != "email" and signoff:
        signoff = "\n" + signoff
    name = "none_available" if not slots else f"propose_{channel}"
    return load_template(name).format(
        first_name=_first_name(recipient_name),
        owner_first=_first_name(prefs.owner.name),
        options=options,
        client_zone=label(cz, slots[0].start if slots else None),
        owner_zone=label(prefs.owner.timezone, slots[0].start if slots else None),
        duration=duration,
        topic=topic or "a call",
        bullet=bullet,
        signoff=signoff,
    )


def render_confirmation(slot: Slot, prefs: Preferences, *, channel: str, recipient_name: Optional[str],
                        client_zone: Optional[str], teams: bool = True) -> str:
    cz = client_zone or prefs.owner.timezone
    primary, secondary = (cz, prefs.owner.timezone) if prefs.response.lead_with_client_zone else (prefs.owner.timezone, cz)
    chosen = format_slot(slot.start, slot.end, primary, secondary, show_both=prefs.response.show_both_zones)
    teams_note = "A Teams invite is on its way." if teams else "Calendar invite is on its way."
    return load_template(f"confirm_{channel}").format(
        first_name=_first_name(recipient_name),
        owner_first=_first_name(prefs.owner.name),
        chosen=chosen,
        teams_note=teams_note,
        client_zone=label(cz, slot.start),
        owner_zone=label(prefs.owner.timezone, slot.start),
        options="",
        duration=slot.duration_minutes,
        topic="",
        bullet=prefs.response.list_bullet,
        signoff="",
    )


def render_owner_ping(slots: list[Slot], prefs: Preferences, *, requester: str, channel: str,
                      client_zone: Optional[str], duration: int, topic: Optional[str]) -> str:
    cz = client_zone or prefs.owner.timezone
    lines = slot_lines(slots, prefs, cz)
    bullet = prefs.response.list_bullet
    return load_template("owner_ping").format(
        requester=requester,
        channel=channel,
        topic=topic or "a call",
        duration=duration,
        client_zone=label(cz),
        owner_zone=label(prefs.owner.timezone),
        options="\n".join(f"{bullet} {ln}" for ln in lines),
        first_name="",
        owner_first=_first_name(prefs.owner.name),
        bullet=bullet,
        signoff="",
    )
