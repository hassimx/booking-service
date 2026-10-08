import re
from datetime import date, datetime, time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.timeutils import GRID_MINUTES


def clean_phone(raw: str) -> str:
    text = raw.strip()
    if not re.fullmatch(r"\+?[\d\s().-]+", text):
        raise ValueError("Phone can only have digits, spaces and the symbols + - ( )")
    digits = re.sub(r"\D", "", text)
    # 8 is the local way to write +7
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if not 11 <= len(digits) <= 15:
        raise ValueError("Enter the phone with country code, for example +7 700 000 00 01")
    return "+" + digits


def check_grid(minutes: int) -> int:
    if minutes % GRID_MINUTES != 0:
        raise ValueError(f"Must be a multiple of {GRID_MINUTES} minutes")
    return minutes


class StatusFilter(str, Enum):
    active = "active"
    cancelled = "cancelled"
    all = "all"


class ServiceIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=60, examples=["Classic haircut"])
    price: int = Field(ge=0, le=1_000_000, examples=[5000])
    duration_minutes: int = Field(ge=15, le=480, examples=[45])
    is_active: bool = True

    _check_duration = field_validator("duration_minutes")(check_grid)


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=60)
    price: int | None = Field(default=None, ge=0, le=1_000_000)
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    is_active: bool | None = None

    @field_validator("duration_minutes")
    @classmethod
    def check_duration(cls, value):
        return value if value is None else check_grid(value)


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: int
    duration_minutes: int
    is_active: bool


class BookingCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    service_id: int = Field(examples=[1])
    start_time: datetime = Field(description="Local time of the shop, no timezone", examples=["2026-10-12T10:00:00"])
    client_name: str = Field(min_length=2, max_length=60, examples=["Alex Demo"])
    client_phone: str = Field(examples=["+7 700 000 00 01"])

    @field_validator("start_time")
    @classmethod
    def no_timezone(cls, value):
        if value.tzinfo is not None:
            raise ValueError("Send the local time of the shop without a timezone")
        return value

    _check_phone = field_validator("client_phone")(clean_phone)


class BookingLookup(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=3, max_length=16, examples=["NORD-7K3F9Q"])
    client_phone: str = Field(examples=["+7 700 000 00 01"])

    _check_phone = field_validator("client_phone")(clean_phone)


class PhoneIn(BaseModel):
    client_phone: str = Field(examples=["+7 700 000 00 01"])

    _check_phone = field_validator("client_phone")(clean_phone)


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    status: str
    start_time: datetime
    end_time: datetime
    client_name: str
    client_phone: str
    service: ServiceOut


class AdminBookingOut(BookingOut):
    id: int
    created_at: datetime


class SlotsOut(BaseModel):
    date: date
    service_id: int
    times: list[str]


class HoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 is Monday")
    is_open: bool
    open_time: time
    close_time: time

    @field_validator("open_time", "close_time")
    @classmethod
    def check_time(cls, value):
        if value.second or value.microsecond:
            raise ValueError("Use hours and minutes only")
        check_grid(value.hour * 60 + value.minute)
        return value

    @model_validator(mode="after")
    def check_order(self):
        if self.is_open and self.close_time <= self.open_time:
            raise ValueError("Closing time must be after opening time")
        return self


class HoursOut(HoursIn):
    model_config = ConfigDict(from_attributes=True)


class HoursWeek(BaseModel):
    days: list[HoursIn] = Field(min_length=7, max_length=7)

    @field_validator("days")
    @classmethod
    def one_per_weekday(cls, days):
        if sorted(day.weekday for day in days) != list(range(7)):
            raise ValueError("Send each weekday from 0 to 6 exactly once")
        return days


class ShopOut(BaseModel):
    currency: str
    timezone: str
    today: date
    days_ahead: int
    hours: list[HoursOut]


class LoginIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)
