import os
import tempfile
from datetime import time, timedelta

import pytest

# settings are read once, so they have to be set before the app is imported
ADMIN_USERNAME = "owner"
ADMIN_PASSWORD = "correct horse battery"

from app.security import hash_password  # noqa: E402

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = ADMIN_USERNAME
os.environ["ADMIN_PASSWORD_HASH"] = hash_password(ADMIN_PASSWORD)
os.environ["TIMEZONE"] = "Asia/Almaty"
os.environ["COOKIE_SECURE"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Service, WorkingHours  # noqa: E402
from app.security import login_limiter  # noqa: E402
from app.timeutils import local_now  # noqa: E402

PHONE = "+7 700 000 00 01"


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_limiter.clear()
    with TestClient(app) as test_client:
        # every weekday open 10:00-20:00, so tests do not depend on today's date
        with SessionLocal() as db:
            for hours in db.scalars(select(WorkingHours)):
                hours.is_open = True
                hours.open_time = time(10, 0)
                hours.close_time = time(20, 0)
            db.add_all(
                [
                    Service(name="Haircut", price=5000, duration_minutes=60),
                    Service(name="Beard trim", price=3000, duration_minutes=30),
                ]
            )
            db.commit()
        yield test_client


@pytest.fixture
def admin(client):
    response = client.post("/api/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    return client


@pytest.fixture
def day():
    return local_now().date() + timedelta(days=3)


HAIRCUT = 1
BEARD = 2


def book(client, service_id, day, at, phone=PHONE, name="Test Client"):
    return client.post(
        "/api/bookings",
        json={
            "service_id": service_id,
            "start_time": f"{day}T{at}:00",
            "client_name": name,
            "client_phone": phone,
        },
    )


def free_times(client, service_id, day):
    response = client.get("/api/slots", params={"service_id": service_id, "date": str(day)})
    assert response.status_code == 200
    return response.json()["times"]
