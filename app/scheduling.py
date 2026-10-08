import secrets
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Booking, BookingSlot, Service, WorkingHours
from app.timeutils import GRID_MINUTES, START_STEP_MINUTES, local_now

# no 0/O and 1/I, easy to read out on the phone
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class SlotTakenError(Exception):
    pass


class BadTimeError(Exception):
    pass


def grid_cells(start: datetime, minutes: int) -> list[datetime]:
    return [start + timedelta(minutes=m) for m in range(0, minutes, GRID_MINUTES)]


# start times that fit the working hours and are in the future (taken or not)
def candidate_starts(db: Session, service: Service, day: date, now: datetime) -> list[datetime]:
    hours = db.get(WorkingHours, day.weekday())
    if hours is None or not hours.is_open:
        return []
    if day > now.date() + timedelta(days=get_settings().days_ahead):
        return []
    closing = datetime.combine(day, hours.close_time)
    length = timedelta(minutes=service.duration_minutes)
    starts = []
    start = datetime.combine(day, hours.open_time)
    while start + length <= closing:
        if start > now:
            starts.append(start)
        start += timedelta(minutes=START_STEP_MINUTES)
    return starts


def slots_taken(db: Session, cells: list[datetime]) -> bool:
    found = db.scalar(select(BookingSlot.slot_start).where(BookingSlot.slot_start.in_(cells)).limit(1))
    return found is not None


def free_start_times(db: Session, service: Service, day: date, now: datetime | None = None) -> list[datetime]:
    starts = candidate_starts(db, service, day, now or local_now())
    if not starts:
        return []
    day_start = datetime.combine(day, time.min)
    taken = set(
        db.scalars(
            select(BookingSlot.slot_start).where(
                BookingSlot.slot_start >= day_start,
                BookingSlot.slot_start < day_start + timedelta(days=1),
            )
        )
    )
    return [s for s in starts if not any(c in taken for c in grid_cells(s, service.duration_minutes))]


def new_code(db: Session) -> str:
    while True:
        code = "NORD-" + "".join(secrets.choice(CODE_LETTERS) for _ in range(6))
        if db.scalar(select(Booking.id).where(Booking.code == code)) is None:
            return code


def create_booking(
    db: Session,
    service: Service,
    start_time: datetime,
    client_name: str,
    client_phone: str,
    now: datetime | None = None,
) -> Booking:
    now = now or local_now()
    if start_time not in candidate_starts(db, service, start_time.date(), now):
        raise BadTimeError("This time is in the past or outside working hours")

    cells = grid_cells(start_time, service.duration_minutes)
    # friendly early check. The real protection is the primary key on booking_slots below,
    # because two requests can both pass this check at the same moment.
    if slots_taken(db, cells):
        raise SlotTakenError()

    booking = Booking(
        code=new_code(db),
        service_id=service.id,
        client_name=client_name,
        client_phone=client_phone,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=service.duration_minutes),
        created_at=now,
    )
    db.add(booking)
    db.flush()
    db.add_all(BookingSlot(slot_start=cell, booking_id=booking.id) for cell in cells)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise SlotTakenError()
    return booking


def cancel_booking(db: Session, booking: Booking) -> None:
    booking.status = "cancelled"
    db.execute(delete(BookingSlot).where(BookingSlot.booking_id == booking.id))
    db.commit()


def ensure_default_hours(db: Session) -> None:
    existing = set(db.scalars(select(WorkingHours.weekday)))
    for weekday in range(7):
        if weekday not in existing:
            db.add(
                WorkingHours(
                    weekday=weekday,
                    is_open=weekday != 6,
                    open_time=time(10, 0),
                    close_time=time(19, 0),
                )
            )
    db.commit()
