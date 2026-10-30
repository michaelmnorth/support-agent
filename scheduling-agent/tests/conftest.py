import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SCHEDULER_PROVIDER", "none")
os.environ["SCHEDULER_HOME"] = str(ROOT)

from scheduler.models import BusyBlock, Preferences  # noqa: E402

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
UK = ZoneInfo("Europe/London")
UTC = timezone.utc


def et(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


@pytest.fixture
def prefs():
    """Deterministic preferences independent of preferences.yaml."""
    p = Preferences()
    p.owner.timezone = "America/New_York"
    p.owner.name = "Michael North"
    p.scheduling.buffer_minutes = 30
    p.scheduling.slot_granularity_minutes = 30
    p.scheduling.min_lead_time_hours = 24
    p.scheduling.daily_blocks = []
    p.scheduling.max_options = 4
    p.scheduling.max_per_day = 2
    return p


@pytest.fixture
def now():
    # Friday 2026-10-30 09:00 ET (EDT, UTC-4). DST ends Sunday 2026-11-01.
    return et(2026, 10, 30, 9)


def busy(start, end, **kw):
    return BusyBlock(start=start, end=end, **kw)
