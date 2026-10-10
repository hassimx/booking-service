"""Booking assistant: turns a free-text request like
"haircut and beard tomorrow after 5" or "стрижка в субботу утром"
into a service, a day and a time window, then finds free times.

Gemini reads the request when GEMINI_API_KEY is set. Without a key, or if the
call fails, a small rule-based parser does the same job for common phrases.
The AI only understands the request; free times always come from the database.
"""

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Service
from app.scheduling import free_start_times
from app.timeutils import local_now

# words people use for a service, matched against the service name
SYNONYMS = {
    "haircut": ["haircut", "hair cut", "cut", "стрижк", "подстри", "постри"],
    "beard": ["beard", "бород"],
    "shave": ["shave", "брить", "бритьё", "бритье"],
    "kid": ["kid", "child", "son", "детск", "ребен", "ребён", "сын"],
    "fade": ["fade", "фейд"],
}

WEEKDAYS = [
    ("monday", "понедельник"),
    ("tuesday", "вторник"),
    ("wednesday", "сред"),
    ("thursday", "четверг"),
    ("friday", "пятниц"),
    ("saturday", "суббот"),
    ("sunday", "воскресень"),
]

PARTS_OF_DAY = {
    "morning": (time(0, 0), time(12, 0)),
    "утр": (time(0, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(17, 0)),
    "днём": (time(12, 0), time(17, 0)),
    "днем": (time(12, 0), time(17, 0)),
    "после обеда": (time(13, 0), time(23, 59)),
    "evening": (time(17, 0), time(23, 59)),
    "вечер": (time(17, 0), time(23, 59)),
}


@dataclass
class Request:
    service_ids: list[int] = field(default_factory=list)
    day: date | None = None
    after: time | None = None
    before: time | None = None
    source: str = "rules"
    weekday: bool = False  # the day came from a weekday name, so next week also fits


def groups_in(text: str) -> set[str]:
    return {key for key, words in SYNONYMS.items() if key in text or any(w in text for w in words)}


def rank_services(text: str, services: list[Service]) -> list[int]:
    """Best match first: the full service name, then the most shared words and the fewest extra ones."""
    wanted = groups_in(text)
    scored = []
    for service in services:
        name = service.name.lower()
        if name in text:
            scored.append((100, service.id))
            continue
        has = groups_in(name)
        matched = len(has & wanted)
        if matched:
            scored.append((matched * 10 - len(has - wanted) * 3, service.id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [service_id for _, service_id in scored]


def hour_from(text: str, pm_hint: bool) -> time | None:
    match = re.match(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    suffix = match.group(3)
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix is None and pm_hint and 1 <= hour <= 8:
        hour += 12  # "after 5" at a barbershop means 17:00
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def parse_with_rules(text: str, services: list[Service], today: date) -> Request:
    low = " " + text.lower().strip() + " "
    request = Request(source="rules")

    request.service_ids = rank_services(low, services)

    if re.search(r"day after tomorrow|послезавтра", low):
        request.day = today + timedelta(days=2)
    elif re.search(r"tomorrow|завтра", low):
        request.day = today + timedelta(days=1)
    elif re.search(r"today|сегодня", low):
        request.day = today
    else:
        for index, (en, ru) in enumerate(WEEKDAYS):
            if en in low or ru in low:
                ahead = (index - today.weekday()) % 7
                request.day = today + timedelta(days=ahead)
                request.weekday = True
                break
        date_match = re.search(r"(\d{1,2})[./](\d{1,2})(?![\d:])", low)
        if request.day is None and date_match:
            day, month = int(date_match.group(1)), int(date_match.group(2))
            try:
                found = date(today.year, month, day)
                if found < today:
                    found = date(today.year + 1, month, day)
                request.day = found
            except ValueError:
                pass

    for word, (start, end) in PARTS_OF_DAY.items():
        if word in low:
            request.after, request.before = start, end

    after = re.search(r"(?:after|from|после|с)\s+(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)", low)
    before = re.search(r"(?:before|until|till|до)\s+(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)", low)
    at = re.search(r"(?:\bat|\bв|\bна)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)(?!\s*(?:день|дн|day))", low)
    if after:
        request.after = hour_from(after.group(1), pm_hint=True)
    if before:
        request.before = hour_from(before.group(1), pm_hint=True)
    if at and not after and not before:
        exact = hour_from(at.group(1), pm_hint=True)
        if exact:
            request.after = exact
            request.before = (datetime.combine(date.min, exact) + timedelta(minutes=59)).time()
    return request


def parse_with_gemini(text: str, services: list[Service], today: date) -> Request | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    menu = [{"id": s.id, "name": s.name, "minutes": s.duration_minutes} for s in services]
    prompt = (
        "You read booking requests for a barbershop. Today is "
        f"{today.isoformat()} ({today.strftime('%A')}). Services: {json.dumps(menu, ensure_ascii=False)}.\n"
        "Reply with JSON only: {\"service_ids\": [the best matching service id first], "
        "\"date\": \"YYYY-MM-DD\" or null, \"after\": \"HH:MM\" or null, \"before\": \"HH:MM\" or null}. "
        "The request can be in English or Russian. If the client gives one time, set after to it and before "
        "to one hour later. Do not invent a date or time the client did not ask for.\n"
        f"Request: {text}"
    )
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    call = urllib.request.Request(
        url, data=body, headers={"content-type": "application/json", "x-goog-api-key": settings.gemini_api_key}
    )
    try:
        with urllib.request.urlopen(call, timeout=8) as response:
            data = json.load(response)
        raw = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        return None  # the rule parser takes over

    known = {s.id for s in services}

    def as_time(value):
        try:
            return time.fromisoformat(value) if value else None
        except (TypeError, ValueError):
            return None

    try:
        day = date.fromisoformat(raw["date"]) if raw.get("date") else None
    except (TypeError, ValueError):
        day = None
    return Request(
        service_ids=[i for i in raw.get("service_ids") or [] if i in known],
        day=day,
        after=as_time(raw.get("after")),
        before=as_time(raw.get("before")),
        source="ai",
    )


def suggest(db: Session, text: str, services: list[Service], limit: int = 3) -> dict:
    now = local_now()
    today = now.date()
    request = parse_with_gemini(text, services, today) or parse_with_rules(text, services, today)
    if not request.service_ids:
        return {"source": request.source, "service": None, "suggestions": [],
                "message": "I could not tell which service you want. Try naming it, for example \"haircut\"."}

    service = next(s for s in services if s.id == request.service_ids[0])
    if request.day is None:
        days = [today + timedelta(days=i) for i in range(8)]
    elif request.weekday and request.day == today:
        days = [today, today + timedelta(days=7)]  # "on saturday" late on a saturday means next week too
    else:
        days = [request.day]
    suggestions = []
    for day in days:
        if day < today:
            continue
        for start in free_start_times(db, service, day, now):
            t = start.time()
            if request.after and t < request.after:
                continue
            if request.before and t > request.before:
                continue
            suggestions.append({"date": day.isoformat(), "time": t.strftime("%H:%M")})
            if len(suggestions) >= limit:
                break
        if len(suggestions) >= limit:
            break

    message = None if suggestions else "No free time matches this request. Try another day or a wider time."
    return {
        "source": request.source,
        "service": {"id": service.id, "name": service.name},
        "suggestions": suggestions,
        "message": message,
    }
