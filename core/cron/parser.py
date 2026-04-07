"""
Cron Expression Parser — CC-aligned 5-field standard cron.
CC: src/utils/cron.ts

Supports: M H DoM Mon DoW
  - * (any), */N (step), N-M (range), N,M,... (list)
  - DoW: 0=Sun, 7=Sun alias (vixie-cron)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class CronFields:
    minute: list[int]       # 0-59
    hour: list[int]         # 0-23
    day_of_month: list[int] # 1-31
    month: list[int]        # 1-12
    day_of_week: list[int]  # 0-6 (0=Sun)


def parse_field(field: str, min_val: int, max_val: int) -> list[int]:
    """Parse a single cron field into a sorted list of values."""
    values = set()
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if base == "*":
                start = min_val
            elif "-" in base:
                start = int(base.split("-")[0])
            else:
                start = int(base)
            for v in range(start, max_val + 1, step):
                if min_val <= v <= max_val:
                    values.add(v)
        elif "-" in part:
            lo, hi = part.split("-", 1)
            for v in range(int(lo), int(hi) + 1):
                if min_val <= v <= max_val:
                    values.add(v)
        elif part == "*":
            values.update(range(min_val, max_val + 1))
        else:
            v = int(part)
            # DoW: 7 → 0 (Sunday alias)
            if max_val == 6 and v == 7:
                v = 0
            if min_val <= v <= max_val:
                values.add(v)
    return sorted(values)


def parse_cron(expr: str) -> CronFields:
    """Parse a 5-field cron expression. Raises ValueError on bad input."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Cron expression must have 5 fields, got {len(parts)}: '{expr}'")
    return CronFields(
        minute=parse_field(parts[0], 0, 59),
        hour=parse_field(parts[1], 0, 23),
        day_of_month=parse_field(parts[2], 1, 31),
        month=parse_field(parts[3], 1, 12),
        day_of_week=parse_field(parts[4], 0, 6),
    )


def matches(fields: CronFields, dt: datetime) -> bool:
    """Check if a datetime matches a cron expression.
    CC: when both DoM and DoW are constrained (not *), fire if EITHER matches."""
    if dt.minute not in fields.minute:
        return False
    if dt.hour not in fields.hour:
        return False
    if dt.month not in fields.month:
        return False

    dom_constrained = fields.day_of_month != list(range(1, 32))
    dow_constrained = fields.day_of_week != list(range(0, 7))

    if dom_constrained and dow_constrained:
        # CC/vixie-cron: either matches
        return dt.day in fields.day_of_month or dt.weekday_sunday() in fields.day_of_week
    else:
        if dom_constrained and dt.day not in fields.day_of_month:
            return False
        if dow_constrained and _weekday_sunday(dt) not in fields.day_of_week:
            return False
    return True


def _weekday_sunday(dt: datetime) -> int:
    """Convert Python weekday (Mon=0) to cron weekday (Sun=0)."""
    return (dt.weekday() + 1) % 7


def next_fire(fields: CronFields, after: datetime) -> Optional[datetime]:
    """Find the next datetime matching the cron expression after `after`.
    CC: minute-by-minute walk forward, bounded at 366 days."""
    # Start from the next minute
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    max_time = after + timedelta(days=366)

    while candidate < max_time:
        if candidate.month not in fields.month:
            # Jump to next month
            if candidate.month == 12:
                candidate = candidate.replace(year=candidate.year + 1, month=1, day=1, hour=0, minute=0)
            else:
                candidate = candidate.replace(month=candidate.month + 1, day=1, hour=0, minute=0)
            continue
        if candidate.hour not in fields.hour:
            candidate += timedelta(hours=1)
            candidate = candidate.replace(minute=0)
            continue
        if candidate.minute not in fields.minute:
            candidate += timedelta(minutes=1)
            continue

        # Check day constraints
        dom_constrained = fields.day_of_month != list(range(1, 32))
        dow_constrained = fields.day_of_week != list(range(0, 7))
        dow = _weekday_sunday(candidate)

        if dom_constrained and dow_constrained:
            if candidate.day not in fields.day_of_month and dow not in fields.day_of_week:
                candidate += timedelta(days=1)
                candidate = candidate.replace(hour=0, minute=0)
                continue
        else:
            if dom_constrained and candidate.day not in fields.day_of_month:
                candidate += timedelta(days=1)
                candidate = candidate.replace(hour=0, minute=0)
                continue
            if dow_constrained and dow not in fields.day_of_week:
                candidate += timedelta(days=1)
                candidate = candidate.replace(hour=0, minute=0)
                continue

        return candidate

    return None  # no match within 366 days
