from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import scheduling
from app.database import SessionLocal
from app.main import app
from app.models import Booking, BookingSlot
from tests.conftest import BEARD, HAIRCUT, PHONE, book, free_times


def test_same_time_twice_is_rejected(client, day):
    first = book(client, HAIRCUT, day, "10:00")
    second = book(client, HAIRCUT, day, "10:00", phone="+7 700 000 00 02")
    assert first.status_code == 201
    assert second.status_code == 409
    assert "already taken" in second.json()["detail"]


def test_overlap_by_duration_is_rejected(client, day):
    assert book(client, HAIRCUT, day, "10:00").status_code == 201  # 10:00-11:00
    assert book(client, BEARD, day, "10:30").status_code == 409  # starts inside it
    assert book(client, BEARD, day, "11:00").status_code == 201  # starts right when it ends
    # a long service must not run into a booking that starts later
    assert book(client, HAIRCUT, day, "10:30").status_code == 409


def test_taken_times_are_not_offered(client, day):
    book(client, HAIRCUT, day, "10:00")
    assert "10:00" not in free_times(client, BEARD, day)
    assert "10:30" not in free_times(client, BEARD, day)
    assert "11:00" in free_times(client, BEARD, day)
    # a one hour service starting at 10:30 would run into the booking at 11:00 too
    book(client, BEARD, day, "11:00")
    assert "10:30" not in free_times(client, HAIRCUT, day)
    assert "11:30" in free_times(client, HAIRCUT, day)


def test_cancel_frees_the_time(client, day):
    created = book(client, HAIRCUT, day, "10:00").json()
    assert "10:00" not in free_times(client, HAIRCUT, day)

    cancelled = client.post(f"/api/bookings/{created['code']}/cancel", json={"client_phone": PHONE})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    assert "10:00" in free_times(client, HAIRCUT, day)
    assert book(client, HAIRCUT, day, "10:00", phone="+7 700 000 00 02").status_code == 201


def test_cannot_cancel_twice(client, day):
    code = book(client, HAIRCUT, day, "10:00").json()["code"]
    client.post(f"/api/bookings/{code}/cancel", json={"client_phone": PHONE})
    again = client.post(f"/api/bookings/{code}/cancel", json={"client_phone": PHONE})
    assert again.status_code == 409


def test_database_refuses_the_same_slot_twice(client, day):
    booking_id = book(client, HAIRCUT, day, "10:00").json()
    slot = datetime.combine(day, datetime.min.time()).replace(hour=10)
    with SessionLocal() as db:
        first_booking = db.query(Booking).filter_by(code=booking_id["code"]).one()
        db.add(BookingSlot(slot_start=slot, booking_id=first_booking.id))
        with pytest.raises(IntegrityError):
            db.commit()


def test_race_is_caught_by_the_database(client, day, monkeypatch):
    # pretend the check before the insert saw a free slot, like two requests at once
    monkeypatch.setattr(scheduling, "slots_taken", lambda db, cells: False)
    assert book(client, HAIRCUT, day, "10:00").status_code == 201
    second = book(client, HAIRCUT, day, "10:00", phone="+7 700 000 00 02")
    assert second.status_code == 409

    with SessionLocal() as db:
        assert db.query(Booking).count() == 1


def test_many_requests_at_once_book_the_slot_once(client, day):
    def try_book(number):
        with TestClient(app) as other:
            return book(other, HAIRCUT, day, "12:00", phone=f"+7 700 000 01 {number:02d}").status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(try_book, range(8)))

    assert results.count(201) == 1
    assert results.count(409) == 7


@pytest.mark.parametrize(
    "phone",
    ["abc", "12345", "+7 700 000", "+7 700 000 00 01 ext 5", "+" + "1" * 16, ""],
)
def test_bad_phone_is_rejected(client, day, phone):
    response = book(client, HAIRCUT, day, "10:00", phone=phone)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "phone",
    ["+7 700 000 00 01", "87000000001", "+7(700)000-00-01", "7 700 000 00 01"],
)
def test_phone_is_saved_in_one_format(client, day, phone):
    response = book(client, HAIRCUT, day, "10:00", phone=phone)
    assert response.status_code == 201
    assert response.json()["client_phone"] == "+77000000001"


def test_short_name_is_rejected(client, day):
    assert book(client, HAIRCUT, day, "10:00", name="A").status_code == 422


def test_lookup_needs_the_right_phone(client, day):
    code = book(client, HAIRCUT, day, "10:00").json()["code"]
    right = client.post("/api/bookings/lookup", json={"code": code, "client_phone": "87000000001"})
    wrong = client.post("/api/bookings/lookup", json={"code": code, "client_phone": "+7 700 000 00 99"})
    assert right.status_code == 200
    assert right.json()["code"] == code
    assert wrong.status_code == 404


def test_cannot_cancel_with_wrong_phone(client, day):
    code = book(client, HAIRCUT, day, "10:00").json()["code"]
    response = client.post(f"/api/bookings/{code}/cancel", json={"client_phone": "+7 700 000 00 99"})
    assert response.status_code == 404
    assert "10:00" not in free_times(client, HAIRCUT, day)


def test_past_time_is_rejected(client):
    response = book(client, HAIRCUT, "2020-01-06", "10:00")
    assert response.status_code == 422


def test_booking_must_end_before_closing(client, day):
    assert "19:00" in free_times(client, HAIRCUT, day)
    assert "19:30" not in free_times(client, HAIRCUT, day)
    assert book(client, HAIRCUT, day, "19:30").status_code == 422
    assert book(client, BEARD, day, "19:30").status_code == 201


def test_time_between_steps_is_rejected(client, day):
    assert book(client, BEARD, day, "10:15").status_code == 422


def test_unknown_service_is_404(client, day):
    assert book(client, 999, day, "10:00").status_code == 404
