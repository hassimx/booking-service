import pytest

from app.security import hash_password, verify_password
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME, BEARD, HAIRCUT, book, free_times


def test_wrong_password_is_rejected(client):
    response = client.post("/api/admin/login", json={"username": ADMIN_USERNAME, "password": "nope"})
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert client.get("/api/admin/me").status_code == 401


def test_wrong_username_is_rejected(client):
    response = client.post("/api/admin/login", json={"username": "someone", "password": ADMIN_PASSWORD})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/admin/me"),
        ("GET", "/api/admin/bookings?date=2030-01-01"),
        ("POST", "/api/admin/bookings/1/cancel"),
        ("GET", "/api/admin/services"),
        ("POST", "/api/admin/services"),
        ("PATCH", "/api/admin/services/1"),
        ("GET", "/api/admin/hours"),
        ("PUT", "/api/admin/hours"),
    ],
)
def test_admin_api_needs_login(client, method, path):
    response = client.request(method, path, json={})
    assert response.status_code == 401


def test_login_and_logout(client):
    login = client.post("/api/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert login.status_code == 200
    assert client.get("/api/admin/me").status_code == 200

    assert client.post("/api/admin/logout").status_code == 204
    assert client.get("/api/admin/me").status_code == 401


def test_too_many_wrong_passwords_lock_the_login(client):
    for _ in range(5):
        client.post("/api/admin/login", json={"username": ADMIN_USERNAME, "password": "nope"})
    # even the right password is refused for a while
    response = client.post("/api/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 429


def test_password_is_stored_as_hash():
    stored = hash_password("secret")
    assert "secret" not in stored
    assert verify_password("secret", stored)
    assert not verify_password("other", stored)
    assert not verify_password("secret", "not-a-hash")


def test_day_list_and_status_filter(admin, day):
    book(admin, HAIRCUT, day, "10:00")
    code = book(admin, BEARD, day, "12:00", phone="+7 700 000 00 02").json()["code"]
    admin.post(f"/api/bookings/{code}/cancel", json={"client_phone": "+7 700 000 00 02"})

    def names(status):
        rows = admin.get("/api/admin/bookings", params={"date": str(day), "status": status}).json()
        return [row["service"]["name"] for row in rows]

    assert names("active") == ["Haircut"]
    assert names("cancelled") == ["Beard trim"]
    assert names("all") == ["Haircut", "Beard trim"]


def test_admin_cancel_frees_the_time(admin, day):
    book(admin, HAIRCUT, day, "10:00")
    booking_id = admin.get("/api/admin/bookings", params={"date": str(day)}).json()[0]["id"]

    assert admin.post(f"/api/admin/bookings/{booking_id}/cancel").status_code == 200
    assert "10:00" in free_times(admin, HAIRCUT, day)
    assert admin.post(f"/api/admin/bookings/{booking_id}/cancel").status_code == 409


def test_hidden_service_cannot_be_booked(admin, day):
    assert admin.patch(f"/api/admin/services/{BEARD}", json={"is_active": False}).status_code == 200

    public = admin.get("/api/services").json()
    assert [service["name"] for service in public] == ["Haircut"]
    assert book(admin, BEARD, day, "10:00").status_code == 404
    # the owner still sees it
    assert len(admin.get("/api/admin/services").json()) == 2


def test_add_and_edit_service(admin):
    created = admin.post("/api/admin/services", json={"name": "Kids cut", "price": 2500, "duration_minutes": 30})
    assert created.status_code == 201
    service_id = created.json()["id"]

    edited = admin.patch(f"/api/admin/services/{service_id}", json={"price": 2800})
    assert edited.json()["price"] == 2800
    assert edited.json()["name"] == "Kids cut"


@pytest.mark.parametrize(
    "body",
    [
        {"name": "X", "price": 100, "duration_minutes": 30},
        {"name": "Shave", "price": -5, "duration_minutes": 30},
        {"name": "Shave", "price": 100, "duration_minutes": 20},
        {"name": "Shave", "price": 100, "duration_minutes": 0},
    ],
)
def test_bad_service_is_rejected(admin, body):
    assert admin.post("/api/admin/services", json=body).status_code == 422


def test_closing_a_weekday_removes_its_times(admin, day):
    week = admin.get("/api/admin/hours").json()
    for row in week:
        if row["weekday"] == day.weekday():
            row["is_open"] = False
    assert admin.put("/api/admin/hours", json={"days": week}).status_code == 200

    assert free_times(admin, HAIRCUT, day) == []
    assert book(admin, HAIRCUT, day, "10:00").status_code == 422


def test_hours_must_close_after_opening(admin):
    week = admin.get("/api/admin/hours").json()
    week[0]["open_time"] = "18:00:00"
    week[0]["close_time"] = "12:00:00"
    assert admin.put("/api/admin/hours", json={"days": week}).status_code == 422


def test_hours_need_all_seven_days(admin):
    week = admin.get("/api/admin/hours").json()
    assert admin.put("/api/admin/hours", json={"days": week[:6]}).status_code == 422
