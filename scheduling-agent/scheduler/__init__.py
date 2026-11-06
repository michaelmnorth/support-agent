"""Scheduling assistant core: deterministic availability, time zones, client profiles, templates.

The LLM (Claude) handles the fuzzy parts: reading an email or Slack message, figuring
out who is asking and for how long, and writing in the owner's voice. Everything here
is the part that must be exact: never offering a time that collides with (or sits within
the buffer of) an existing meeting, honoring working hours, and converting time zones.
"""

__version__ = "0.1.0"
