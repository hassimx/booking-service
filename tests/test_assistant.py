from datetime import date, timedelta

from app.assistant import parse_with_rules
from app.models import Service

from tests.conftest import BEARD, HAIRCUT, book

SERVICES = [
    Service(id=1, name="Haircut", price=5000, duration_minutes=60),
    Service(id=2, name="Beard trim", price=3000, duration_minutes=30),
]
MONDAY = date(2026, 10, 12)


def test_english_tomorrow_after_five():
    request = parse_with_rules("haircut tomorrow after 5", SERVICES, MONDAY)
    assert request.service_ids == [1]
    assert request.day == MONDAY + timedelta(days=1)
    assert request.after.hour == 17


def test_russian_weekday_and_part_of_day():
    request = parse_with_rules("стрижка и борода в субботу утром", SERVICES, MONDAY)
    assert request.service_ids == [1, 2]
    assert request.day == date(2026, 10, 17)
    assert request.before.hour == 12


def test_exact_time():
    request = parse_with_rules("beard at 14:30 today", SERVICES, MONDAY)
    assert request.service_ids == [2]
    assert request.day == MONDAY
    assert (request.after.hour, request.after.minute) == (14, 30)


def test_assistant_skips_taken_times(client, day):
    assert book(client, HAIRCUT, day, "17:00").status_code == 201
    text = f"haircut {day.day:02d}.{day.month:02d} after 5"
    answer = client.post("/api/assistant", json={"text": text}).json()
    assert answer["source"] == "rules"
    assert answer["service"]["id"] == HAIRCUT
    times = [s["time"] for s in answer["suggestions"]]
    assert "17:00" not in times and "17:30" not in times
    assert times[0] == "18:00"


def test_assistant_unknown_service(client):
    answer = client.post("/api/assistant", json={"text": "manicure tomorrow"}).json()
    assert answer["service"] is None
    assert answer["suggestions"] == []


def test_assistant_beard_by_name(client, day):
    answer = client.post("/api/assistant", json={"text": "борода"}).json()
    assert answer["service"]["id"] == BEARD
    assert len(answer["suggestions"]) == 3
