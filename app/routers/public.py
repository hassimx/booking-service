import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.models import Booking, Service, WorkingHours
from app.scheduling import (
    BadTimeError,
    SlotTakenError,
    cancel_booking,
    create_booking,
    free_start_times,
)
from app.schemas import BookingCreate, BookingLookup, BookingOut, PhoneIn, ServiceOut, ShopOut, SlotsOut
from app.timeutils import local_now

router = APIRouter(tags=["public"])


def get_active_service(db: Session, service_id: int) -> Service:
    service = db.get(Service, service_id)
    if service is None or not service.is_active:
        raise HTTPException(404, "Service not found")
    return service


def find_booking(db: Session, code: str, phone: str) -> Booking | None:
    booking = db.scalar(
        select(Booking).options(joinedload(Booking.service)).where(Booking.code == code.strip().upper())
    )
    if booking is None or not secrets.compare_digest(booking.client_phone, phone):
        return None
    return booking


@router.get("/shop", response_model=ShopOut, summary="Shop info and working hours")
def shop_info(db: Session = Depends(get_db)):
    settings = get_settings()
    return {
        "currency": settings.currency,
        "timezone": settings.timezone,
        "today": local_now().date(),
        "days_ahead": settings.days_ahead,
        "hours": db.scalars(select(WorkingHours).order_by(WorkingHours.weekday)).all(),
    }


@router.get("/services", response_model=list[ServiceOut], summary="List services that can be booked")
def list_services(db: Session = Depends(get_db)):
    return db.scalars(select(Service).where(Service.is_active).order_by(Service.id)).all()


@router.get("/slots", response_model=SlotsOut, summary="List free start times for a service on one day")
def list_free_times(
    service_id: int,
    day: date = Query(alias="date"),
    db: Session = Depends(get_db),
):
    service = get_active_service(db, service_id)
    starts = free_start_times(db, service, day)
    return {"date": day, "service_id": service.id, "times": [s.strftime("%H:%M") for s in starts]}


@router.post(
    "/bookings",
    response_model=BookingOut,
    status_code=201,
    summary="Create a booking",
    responses={
        409: {"description": "This time is already taken"},
        422: {"description": "Bad input, or the time is in the past or outside working hours"},
    },
)
def book(data: BookingCreate, db: Session = Depends(get_db)):
    service = get_active_service(db, data.service_id)
    try:
        return create_booking(db, service, data.start_time, data.client_name, data.client_phone)
    except BadTimeError as error:
        raise HTTPException(422, str(error))
    except SlotTakenError:
        raise HTTPException(409, "Sorry, this time is already taken. Please pick another one.")


# POST instead of GET so the phone number does not end up in URLs and server logs
@router.post("/bookings/lookup", response_model=BookingOut, summary="Find a booking by code and phone")
def lookup_booking(data: BookingLookup, db: Session = Depends(get_db)):
    booking = find_booking(db, data.code, data.client_phone)
    if booking is None:
        raise HTTPException(404, "No booking found for this code and phone number")
    return booking


@router.post(
    "/bookings/{code}/cancel",
    response_model=BookingOut,
    summary="Cancel a booking by code and phone",
    responses={409: {"description": "Already cancelled, or the booking has already started"}},
)
def cancel_my_booking(code: str, data: PhoneIn, db: Session = Depends(get_db)):
    booking = find_booking(db, code, data.client_phone)
    if booking is None:
        raise HTTPException(404, "No booking found for this code and phone number")
    if booking.status != "active":
        raise HTTPException(409, "This booking is already cancelled")
    if booking.start_time <= local_now():
        raise HTTPException(409, "This booking has already started, please call us")
    cancel_booking(db, booking)
    return booking
