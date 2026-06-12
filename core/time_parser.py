"""
Date/time parser for natural language temporal expressions.
Handles 100+ variants of date/time references found in military intelligence queries.
"""

import re
from datetime import datetime, timedelta, date
from typing import Optional

# ── Reference point: "now" ──────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now()

# ── Month mapping ────────────────────────────────────────────────────────────
MONTHS = {
    "january": 1, "jan": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# ── Helpers ──────────────────────────────────────────────────────────────────
def _month_num(name: str) -> Optional[int]:
    return MONTHS.get(name.lower().strip(".,"))

def _year_from_2digit(y: int) -> int:
    return 2000 + y if y < 100 else y

def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)

def _end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=0)


# ── Main parser ──────────────────────────────────────────────────────────────
def parse_time_expression(question: str) -> Optional[dict]:
    """
    Parse a natural language question for temporal expressions.
    Returns {"gte": "ISO", "lte": "ISO"} or None if no temporal found.

    Handles:
    - "last/past/previous/prior N days/weeks/months/years"
    - "since last ...", "from ... to/till/until ..."
    - "between ... and ..."
    - "on 12th of Aug 2025", "dated 2024-09-12"
    - "DD-MM-YYYY", "DD/MM/YYYY", "DD.MM.YYYY"
    - "MM-DD-YYYY", "YYYY-MM-DD"
    - "Q1/Q2/Q3/Q4 2024", "last/this/next quarter"
    - "last/this/next month/year"
    - "june 2025", "only 2023", "march to april"
    - "YTD", "MTD", "QTD", "WTD"
    - "today", "yesterday", "tomorrow"
    - "monday to friday", "tuesday through thursday"
    """
    text = question.strip()
    ql = text.lower().replace(",", " ")
    now = _now()

    # ── 1. Special abbreviations ─────────────────────────────────────────────
    if re.search(r"\bytd\b", ql):
        return {"gte": _iso(datetime(now.year, 1, 1)), "lte": _iso(now)}
    if re.search(r"\bmtd\b", ql):
        return {"gte": _iso(datetime(now.year, now.month, 1)), "lte": _iso(now)}
    if re.search(r"\bqtd\b", ql):
        q_start_month = ((now.month - 1) // 3) * 3 + 1
        return {"gte": _iso(datetime(now.year, q_start_month, 1)), "lte": _iso(now)}
    if re.search(r"\bwtd\b", ql):
        monday = now - timedelta(days=now.weekday())
        return {"gte": _iso(_start_of_day(monday)), "lte": _iso(now)}

    # ── 2. Today / Yesterday / Tomorrow ──────────────────────────────────────
    if re.search(r"\btoday\b", ql):
        return {"gte": _iso(_start_of_day(now)), "lte": _iso(_end_of_day(now))}
    if re.search(r"\byesterday\b", ql):
        y = now - timedelta(days=1)
        return {"gte": _iso(_start_of_day(y)), "lte": _iso(_end_of_day(y))}
    if re.search(r"\btomorrow\b", ql):
        t = now + timedelta(days=1)
        return {"gte": _iso(_start_of_day(t)), "lte": _iso(_end_of_day(t))}

    # ── 4. "last/this/next month/year" (must come before generic "last N months")
    m = re.search(r"\b(last|this|next)\s+month\b", ql)
    if m:
        word = m.group(1)
        if word == "this":
            return _month_range(now.year, now.month)
        elif word == "last":
            m_num = now.month - 1
            y = now.year
            if m_num < 1:
                m_num = 12
                y -= 1
            return _month_range(y, m_num)
        elif word == "next":
            m_num = now.month + 1
            y = now.year
            if m_num > 12:
                m_num = 1
                y += 1
            return _month_range(y, m_num)

    m = re.search(r"\b(last|this|next)\s+year\b", ql)
    if m:
        word = m.group(1)
        if word == "this":
            return {"gte": _iso(datetime(now.year, 1, 1)), "lte": _iso(now)}
        elif word == "last":
            return {"gte": _iso(datetime(now.year - 1, 1, 1)), "lte": _iso(datetime(now.year - 1, 12, 31, 23, 59, 59))}
        elif word == "next":
            return {"gte": _iso(datetime(now.year + 1, 1, 1)), "lte": _iso(datetime(now.year + 1, 12, 31, 23, 59, 59))}

    # ── 5. "last/past/previous/prior N days/weeks/months/years" ──────────────
    # Also handles "last couple of weeks/months"
    m = re.search(
        r"\b(last|past|previous|prior)\s+(\d+|a\s+couple\s+of\s+|a\s+couple\s+|a\s+few\s+|several\s+)?(day|days|week|weeks|month|months|year|years|fortnight|fortnights)\b",
        ql,
    )
    if m:
        num_str = (m.group(2) or "1").strip()
        num = _word_to_num(num_str)
        unit = m.group(3)
        return _relative_range(now, num, unit)

    # ── 6. "coming/upcoming/next N days/weeks/years" ─────────────────────────
    m = re.search(
        r"\b(coming|upcoming|next)\s+(\d+|a|one|two|three|four|five|six|a\s+couple|a\s+few|several)\s+(day|days|week|weeks|month|months|year|years)\b",
        ql,
    )
    if m:
        num = _word_to_num(m.group(2).strip())
        unit = m.group(3)
        delta = _to_timedelta(num, unit)
        return {"gte": _iso(now), "lte": _iso(now + delta)}

    # (section 5 merged into section 4 above)

    # ── 6. "since last ..." ──────────────────────────────────────────────────
    m = re.search(r"\bsince\s+last\s+(week|month|year|quarter)\b", ql)
    if m:
        unit = m.group(1)
        return _since_last(now, unit)

    m = re.search(r"\bsince\s+(\w+\s+\d{1,2})\b", ql)
    if m:
        return _since_date_text(now, m.group(1))

    # ── 7. "since Monday" / day of week ──────────────────────────────────────
    m = re.search(r"\bsince\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", ql)
    if m:
        target_day = DAY_NAMES.index(m.group(1))
        days_back = (now.weekday() - target_day) % 7
        if days_back == 0:
            days_back = 7
        start = now - timedelta(days=days_back)
        return {"gte": _iso(_start_of_day(start)), "lte": _iso(now)}

    # ── 8. Quarters ──────────────────────────────────────────────────────────
    m = re.search(r"\b(q[1-4])\s*(\d{4})\b", ql)
    if m:
        q = int(m.group(1)[1])
        year = int(m.group(2))
        return _quarter_range(year, q)

    m = re.search(r"\b(\w+)\s+quarter\s+(?:of\s+)?(\d{4})\b", ql)
    if m:
        q_word = m.group(1).lower()
        year = int(m.group(2))
        qm = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
        q = qm.get(q_word)
        if q:
            return _quarter_range(year, q)

    m = re.search(r"\b(last|this|next)\s+quarter\b", ql)
    if m:
        word = m.group(1)
        current_q = (now.month - 1) // 3 + 1
        if word == "this":
            return _quarter_range(now.year, current_q)
        elif word == "last":
            q = current_q - 1
            year = now.year
            if q < 1:
                q = 4
                year -= 1
            return _quarter_range(year, q)
        elif word == "next":
            q = current_q + 1
            year = now.year
            if q > 4:
                q = 1
                year += 1
            return _quarter_range(year, q)

    # (sections 9-10 moved up to section 4 above to take priority)

    # ── 11. "only 2023" / "in 2023" / "during 2023" / "year 2023" ────────
    m = re.search(r"\b(only|in|during|year)\s+(\d{4})\b", ql)
    if m:
        year = int(m.group(2))
        return {"gte": _iso(datetime(year, 1, 1)), "lte": _iso(datetime(year, 12, 31, 23, 59, 59))}

    # ── 12. "from sep 2024 till now" (must come before month+year) ──────────
    m = re.search(
        r"\bfrom\s+(" + "|".join(MONTHS.keys()) + r")\s+(\d{4})\s+(till|to)\s+(now|date)\b",
        ql,
    )
    if m:
        m_num = MONTHS[m.group(1)]
        year = int(m.group(2))
        return {"gte": _iso(datetime(year, m_num, 1)), "lte": _iso(now)}

    # ── 12b. "june 2025 till now" / "june 2025 till date" ──────────────────
    m = re.search(
        r"\b(" + "|".join(MONTHS.keys()) + r")\s+(\d{4})\s+(till|date|now)\b",
        ql,
    )
    if m:
        m_num = MONTHS[m.group(1)]
        year = int(m.group(2))
        return {"gte": _iso(datetime(year, m_num, 1)), "lte": _iso(now)}

    # ── 13. "march 2025" / "apr 2026" ──────────────────────────────────────
    m = re.search(
        r"\b(" + "|".join(MONTHS.keys()) + r")\s+(\d{4})\b", ql
    )
    if m:
        month_name = m.group(1)
        year = int(m.group(2))
        m_num = MONTHS.get(month_name.lower())
        if m_num:
            return _month_range(year, m_num)

    # ── 14. "2023-2025" / "between 2021 and 2023" ─────────────────────────
    m = re.search(r"\b(20\d{2})\s*[-–to]+\s*(20\d{2})\b", ql)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return {"gte": _iso(datetime(y1, 1, 1)), "lte": _iso(datetime(y2, 12, 31, 23, 59, 59))}

    m = re.search(r"\bbetween\s+(20\d{2})\s+and\s+(20\d{2})\b", ql)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        return {"gte": _iso(datetime(y1, 1, 1)), "lte": _iso(datetime(y2, 12, 31, 23, 59, 59))}

    # ── 14. "march to april" / "march to april 2025" ──────────────────────
    m = re.search(
        r"\b(" + "|".join(MONTHS.keys()) + r")\s+(to|through|–|-)\s+(" + "|".join(MONTHS.keys()) + r")(?:\s+(\d{4}))?\b",
        ql,
    )
    if m:
        m1 = MONTHS[m.group(1)]
        m2 = MONTHS[m.group(3)]
        year = int(m.group(4)) if m.group(4) else now.year
        return {
            "gte": _iso(datetime(year, m1, 1)),
            "lte": _iso(_last_day(year, m2)),
        }

    # ── 14. "from ... to/till/until ..." ─────────────────────────────────────
    m = re.search(r"\bfrom\s+(.+?)\s+(to|till|until|through)\s+(.+?)(?:\.|$|\?)", ql)
    if m:
        start_str = m.group(1).strip()
        end_str = m.group(3).strip()
        start_dt = _parse_date_phrase(start_str, now)
        end_dt = _parse_date_phrase(end_str, now)
        if start_dt and end_dt:
            return {"gte": _iso(_start_of_day(start_dt)), "lte": _iso(_end_of_day(end_dt))}

    # (duplicate section 12b removed — moved up between 12 and 13)
    # (duplicate section 16 removed — merged into section 12 above)

    # ── 17. "till/until now" ─────────────────────────────────────────────────
    m = re.search(r"\b(till|to|until)\s+(now|date)\b", ql)
    if m:
        # Try to find a start date elsewhere in the question
        start_dt = _find_implicit_start(ql)
        if start_dt:
            return {"gte": _iso(start_dt), "lte": _iso(now)}

    # ── 18. "on 12th of Aug 2025" / "on 16th January" / "dated 2024-09-12" ─
    # With year
    m = re.search(r"\bon\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(\w+)\s+(\d{4})\b", ql)
    if m:
        day, month_word, year = int(m.group(1)), m.group(2), int(m.group(3))
        m_num = _month_num(month_word)
        if m_num:
            dt = datetime(year, m_num, day)
            return {"gte": _iso(_start_of_day(dt)), "lte": _iso(_end_of_day(dt))}

    m = re.search(r"\bon\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)\s+(\d{4})\b", ql)
    if m:
        day, month_word, year = int(m.group(1)), m.group(2), int(m.group(3))
        m_num = _month_num(month_word)
        if m_num:
            dt = datetime(year, m_num, day)
            return {"gte": _iso(_start_of_day(dt)), "lte": _iso(_end_of_day(dt))}

    # Without year — assume current year
    m = re.search(r"\bon\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(\w+)\b", ql)
    if m:
        day, month_word = int(m.group(1)), m.group(2)
        m_num = _month_num(month_word)
        if m_num:
            try:
                dt = datetime(now.year, m_num, day)
                return {"gte": _iso(_start_of_day(dt)), "lte": _iso(_end_of_day(dt))}
            except ValueError:
                pass

    m = re.search(r"\bdated\s+(\d{4}-\d{2}-\d{2})\b", ql)
    if m:
        dt = datetime.strptime(m.group(1), "%Y-%m-%d")
        return {"gte": _iso(_start_of_day(dt)), "lte": _iso(_end_of_day(dt))}

    # ── 19. Absolute date formats: DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY ──────
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", ql)
    if m:
        d1, d2, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Try DD-MM-YYYY first; if invalid, try MM-DD-YYYY
        dt = _try_date(y, d2, d1) or _try_date(y, d1, d2)
        if dt:
            start = _start_of_day(dt)
            # Check if this is part of a range
            if re.search(r"\b(from|between)\b", ql):
                return {"gte": _iso(start), "lte": _iso(_end_of_day(dt))}
            return {"gte": _iso(start), "lte": _iso(_end_of_day(dt))}

    # ── 20. "monday to friday" / "tuesday through thursday" ────────────────
    m = re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(to|through|–|-)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        ql,
    )
    if m:
        d1 = DAY_NAMES.index(m.group(1))
        d2 = DAY_NAMES.index(m.group(3))
        # Most recent occurrence of this range
        today = now.weekday()
        # Find the most recent d1
        days_since_d1 = (today - d1) % 7
        if days_since_d1 == 0 and today != d1:
            days_since_d1 = 7
        start = now - timedelta(days=days_since_d1)
        end = start + timedelta(days=(d2 - d1) % 7)
        return {"gte": _iso(_start_of_day(start)), "lte": _iso(_end_of_day(end))}

    # ── 21. "this weekend" / "last weekend" / "next weekend" ──────────────
    m = re.search(r"\b(last|this|next)\s+weekend\b", ql)
    if m:
        word = m.group(1)
        today = now.weekday()
        if word == "this":
            sat = now + timedelta(days=(5 - today) % 7)
        elif word == "last":
            sat = now - timedelta(days=(today - 5) % 7 + 7 if today < 5 else today - 5)
        else:  # next
            sat = now + timedelta(days=(5 - today) % 7 + 7 if today >= 5 else (5 - today) % 7)
        sun = sat + timedelta(days=1)
        return {"gte": _iso(_start_of_day(sat)), "lte": _iso(_end_of_day(sun))}

    # (section 22 removed — merged into section 12b above)    # ── 23. Fallback: any 4-digit year ──────────────────────────────────────
    years = re.findall(r"\b(20\d{2})\b", ql)
    if len(years) == 1:
        year = int(years[0])
        return {"gte": _iso(datetime(year, 1, 1)), "lte": _iso(datetime(year, 12, 31, 23, 59, 59))}
    elif len(years) == 2:
        y1, y2 = int(years[0]), int(years[1])
        return {"gte": _iso(datetime(y1, 1, 1)), "lte": _iso(datetime(y2, 12, 31, 23, 59, 59))}

    return None  # No temporal expression found


# ── Utility functions ────────────────────────────────────────────────────────

def _word_to_num(word: str) -> int:
    word = word.lower().strip()
    mapping = {
        "a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "a couple": 2, "a few": 3, "several": 4, "many": 6,
        "a couple of": 2,
    }
    if word in mapping:
        return mapping[word]
    try:
        return int(word)
    except ValueError:
        return 1


def _to_timedelta(num: int, unit: str) -> timedelta:
    unit = unit.lower().rstrip("s")
    if unit == "day":
        return timedelta(days=num)
    elif unit == "week":
        return timedelta(weeks=num)
    elif unit == "month":
        return timedelta(days=num * 30)
    elif unit == "year":
        return timedelta(days=num * 365)
    elif unit == "fortnight":
        return timedelta(weeks=2 * num)
    return timedelta(days=num * 30)


def _relative_range(now: datetime, num: int, unit: str) -> dict:
    delta = _to_timedelta(num, unit)
    start = now - delta
    return {"gte": _iso(_start_of_day(start)), "lte": _iso(now)}


def _since_last(now: datetime, unit: str) -> dict:
    unit = unit.lower()
    if unit == "week":
        monday = now - timedelta(days=now.weekday())
        return {"gte": _iso(_start_of_day(monday)), "lte": _iso(now)}
    elif unit == "month":
        return {"gte": _iso(datetime(now.year, now.month, 1)), "lte": _iso(now)}
    elif unit == "year":
        return {"gte": _iso(datetime(now.year, 1, 1)), "lte": _iso(now)}
    elif unit == "quarter":
        q_start = ((now.month - 1) // 3) * 3 + 1
        return {"gte": _iso(datetime(now.year, q_start, 1)), "lte": _iso(now)}
    return {"gte": _iso(now - timedelta(days=30)), "lte": _iso(now)}


def _since_date_text(now: datetime, text: str) -> dict:
    start = _parse_date_phrase(text)
    if start:
        return {"gte": _iso(_start_of_day(start)), "lte": _iso(now)}
    return {"gte": _iso(now - timedelta(days=30)), "lte": _iso(now)}


def _quarter_range(year: int, q: int) -> dict:
    start_month = (q - 1) * 3 + 1
    end_month = start_month + 2
    return {
        "gte": _iso(datetime(year, start_month, 1)),
        "lte": _iso(_last_day(year, end_month)),
    }


def _month_range(year: int, month: int) -> dict:
    return {
        "gte": _iso(datetime(year, month, 1)),
        "lte": _iso(_last_day(year, month)),
    }


def _last_day(year: int, month: int) -> datetime:
    if month == 12:
        return datetime(year + 1, 1, 1) - timedelta(seconds=1)
    return datetime(year, month + 1, 1) - timedelta(seconds=1)


def _try_date(year: int, month: int, day: int) -> Optional[datetime]:
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _parse_date_phrase(text: str, now: datetime | None = None) -> Optional[datetime]:
    """Parse phrases like '12th of aug 2024', 'september 2024', '2024-09-12',
    'august', '16th january' (assumes current year if not given)."""
    if now is None:
        now = _now()
    text = text.lower().strip().rstrip(".,;:!?")

    # "till now" / "till date"
    if text in ("now", "date", "today"):
        return now

    # "12th of aug 2024" or "16th January 2025"
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(\w+)\s+(\d{4})", text)
    if m:
        day, mon, year = int(m.group(1)), _month_num(m.group(2)), int(m.group(3))
        if day and mon and year:
            try:
                return datetime(year, mon, day)
            except ValueError:
                pass

    # "16th aug 2024" (without "of")
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)\s+(\d{4})", text)
    if m:
        day, mon, year = int(m.group(1)), _month_num(m.group(2)), int(m.group(3))
        if day and mon and year:
            try:
                return datetime(year, mon, day)
            except ValueError:
                pass

    # "aug 2024" / "september 2024"
    m = re.match(r"(\w+)\s+(\d{4})", text)
    if m:
        mon = _month_num(m.group(1))
        year = int(m.group(2))
        if mon:
            return datetime(year, mon, 1)

    # "august" / "sep" (month name only, assume current year)
    if _month_num(text):
        return datetime(now.year, _month_num(text), 1)

    # "16th aug" / "12th of january" (day + month, assume current year)
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(\w+)$", text)
    if m:
        day = int(m.group(1))
        mon = _month_num(m.group(2))
        if mon:
            try:
                return datetime(now.year, mon, day)
            except ValueError:
                pass

    # "2024" (year only)
    m = re.match(r"^(\d{4})$", text)
    if m:
        return datetime(int(m.group(1)), 1, 1)

    # "DD-MM-YYYY" / "DD/MM/YYYY"
    m = re.match(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if m:
        d1, d2, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        dt = _try_date(y, d2, d1) or _try_date(y, d1, d2)
        if dt:
            return dt

    # "YYYY-MM-DD"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    return None


def _find_implicit_start(ql: str) -> Optional[datetime]:
    """Try to find a start date in the question for 'till now' patterns."""
    # Look for "since last X"
    m = re.search(r"\bsince\s+last\s+(week|month|year|quarter)\b", ql)
    if m:
        return _since_last(_now(), m.group(1))["gte"] and datetime.fromisoformat(
            _since_last(_now(), m.group(1))["gte"].replace("T", " ")
        )
    # Look for month year or date patterns
    m = re.search(
        r"\b(" + "|".join(MONTHS.keys()) + r")\s+(\d{4})\b", ql
    )
    if m:
        return datetime(int(m.group(2)), MONTHS[m.group(1)], 1)
    return None


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_cases = [
        ("last six months", "detect since last six months"),
        ("12th aug to 18th sep", "observed from 12th of aug to 18th of september"),
        ("16th january", "detect the modification on 16th of january"),
        ("last 2 weeks", "modify the instrument using last couple of weeks from today"),
        ("june 2025 till now", "manage profile of june 2025 till now"),
        ("only 2023", "only 2023 profiles"),
        ("last quarter", "what is happening in last quarter"),
        ("last six weeks", "any new updates on signals in last six weeks"),
        ("past 7 days", "past 7 days"),
        ("previous 3 weeks", "previous 3 weeks"),
        ("Q3 2024", "Q3 2024"),
        ("last month", "last month"),
        ("YTD", "YTD"),
        ("today", "today"),
        ("monday to friday", "monday to friday"),
        ("2023-2025", "from 2023 to 2025"),
        ("march 2025", "march 2025"),
        ("sep 2024 to now", "from sep 2024 till now"),
    ]

    for label, q in test_cases:
        result = parse_time_expression(q)
        if result:
            gte = result["gte"][:10]
            lte = result["lte"][:10]
            print(f"  {label:30s} → {gte} to {lte}")
        else:
            print(f"  {label:30s} → NOT PARSED")
