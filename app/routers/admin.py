import hmac
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.models import Booking, Service, WorkingHours
from app.scheduling import cancel_booking
from app.schemas import (
    AdminBookingOut,
    HoursOut,
    HoursWeek,
    LoginIn,
    ServiceIn,
    ServiceOut,
    ServiceUpdate,
    StatusFilter,
)
from app.security import login_limiter, verify_password

# login and logout are open, everything else on this router needs a session
auth_router = APIRouter(tags=["admin"])


def require_admin(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(401, "Please log in")


router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


@auth_router.post("/login", summary="Log in and get the session cookie")
def login(data: LoginIn, request: Request):
    settings = get_settings()
    if not settings.admin_username or not settings.admin_password_hash:
        raise HTTPException(503, "Admin login is not set up. See .env.example")

    client = request.client.host if request.client else "unknown"
    if login_limiter.is_blocked(client):
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes")

    # both checks always run, so the answer takes the same time for a wrong username
    right_name = hmac.compare_digest(data.username.encode(), settings.admin_username.encode())
    right_password = verify_password(data.password, settings.admin_password_hash)
    if not (right_name and right_password):
        login_limiter.add_failure(client)
        raise HTTPException(401, "Wrong username or password")

    login_limiter.clear(client)
    request.session.clear()
    request.session["admin"] = True
    return {"username": settings.admin_username}


@auth_router.post("/logout", status_code=204, summary="Log out")
def logout(request: Request):
    request.session.clear()


@router.get("/me", summary="Check that the session is valid")
def me():
    return {"username": get_settings().admin_username}


@router.get("/bookings", response_model=list[AdminBookingOut], summary="List the bookings of one day")
def list_bookings(
    day: date = Query(alias="date"),
    status: StatusFilter = StatusFilter.active,
    db: Session = Depends(get_db),
):
    day_start = datetime.combine(day, time.min)
    query = (
        select(Booking)
        .options(joinedload(Booking.service))
        .where(Booking.start_time >= day_start, Booking.start_time < day_start + timedelta(days=1))
        .order_by(Booking.start_time)
    )
    if status != StatusFilter.all:
        query = query.where(Booking.status == status.value)
    return db.scalars(query).all()


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBookingOut, summary="Cancel any booking")
def cancel_any_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    if booking.status != "active":
        raise HTTPException(409, "This booking is already cancelled")
    cancel_booking(db, booking)
    return booking


@router.get("/services", response_model=list[ServiceOut], summary="List all services, hidden ones too")
def list_all_services(db: Session = Depends(get_db)):
    return db.scalars(select(Service).order_by(Service.id)).all()


@router.post("/services", response_model=ServiceOut, status_code=201, summary="Add a service")
def add_service(data: ServiceIn, db: Session = Depends(get_db)):
    service = Service(**data.model_dump())
    db.add(service)
    db.commit()
    return service


@router.patch("/services/{service_id}", response_model=ServiceOut, summary="Edit, hide or show a service")
def edit_service(service_id: int, data: ServiceUpdate, db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    if service is None:
        raise HTTPException(404, "Service not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            raise HTTPException(422, f"{field} cannot be empty")
        setattr(service, field, value)
    db.commit()
    return service


@router.get("/hours", response_model=list[HoursOut], summary="Get working hours for all weekdays")
def get_hours(db: Session = Depends(get_db)):
    return db.scalars(select(WorkingHours).order_by(WorkingHours.weekday)).all()


# changing hours does not touch bookings that already exist
@router.put("/hours", response_model=list[HoursOut], summary="Save working hours for all weekdays")
def set_hours(data: HoursWeek, db: Session = Depends(get_db)):
    for day in data.days:
        row = db.get(WorkingHours, day.weekday)
        row.is_open = day.is_open
        row.open_time = day.open_time
        row.close_time = day.close_time
    db.commit()
    return db.scalars(select(WorkingHours).order_by(WorkingHours.weekday)).all()
