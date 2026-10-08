from datetime import datetime, time

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    price: Mapped[int]
    duration_minutes: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class WorkingHours(Base):
    __tablename__ = "working_hours"

    weekday: Mapped[int] = mapped_column(primary_key=True)  # 0 = Monday
    is_open: Mapped[bool] = mapped_column(default=True)
    open_time: Mapped[time]
    close_time: Mapped[time]


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (CheckConstraint("end_time > start_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    client_name: Mapped[str] = mapped_column(String(60))
    client_phone: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[datetime] = mapped_column(index=True)
    end_time: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(12), default="active")
    created_at: Mapped[datetime]

    service: Mapped[Service] = relationship()


# One row per 15 minutes that a booking uses. The primary key is the slot time,
# so the database itself refuses two bookings on the same slot. A unique start_time
# on bookings would not be enough: 10:00 for 60 min and 10:30 for 30 min overlap.
# Cancelling a booking deletes its rows, which frees the time.
class BookingSlot(Base):
    __tablename__ = "booking_slots"

    slot_start: Mapped[datetime] = mapped_column(primary_key=True, autoincrement=False)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"))
