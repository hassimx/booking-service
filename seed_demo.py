import random
import sys
from datetime import datetime, time, timedelta

from sqlalchemy import delete, func, select

from app.database import Base, SessionLocal, engine
from app.models import Booking, BookingSlot, Service, WorkingHours
from app.scheduling import cancel_booking, create_booking, ensure_default_hours, free_start_times
from app.timeutils import local_now

# name, price, minutes
SERVICES = [
    ("Classic haircut", 5000, 45),
    ("Skin fade", 6500, 60),
    ("Beard trim", 3000, 30),
    ("Haircut and beard", 8500, 75),
    ("Hot towel shave", 5500, 45),
    ("Kids haircut", 3500, 30),
    ("Buzz cut", 3000, 30),
]
# how often each service is picked for the fake bookings
WEIGHTS = [5, 4, 3, 4, 1, 2, 2]

# weekday -> (open, close), a missing day is closed
HOURS = {
    0: (time(10, 0), time(20, 0)),
    1: (time(10, 0), time(20, 0)),
    2: (time(10, 0), time(20, 0)),
    3: (time(10, 0), time(20, 0)),
    4: (time(10, 0), time(21, 0)),
    5: (time(10, 0), time(18, 0)),
}

FIRST_NAMES = ["Alex", "Daniel", "Max", "Leo", "Adam", "Victor", "Oliver", "Ethan", "Marcus", "Noah",
               "Ivan", "Sam", "Tim", "Felix", "Hugo", "Arman", "Rustam", "Dmitry"]
LAST_NAMES = ["Hart", "Reed", "Stone", "Lane", "Ford", "Moore", "Grey", "West", "Clark", "Frost",
              "Wells", "Brook", "Hale", "Pierce", "Fox", "Day"]

BOOKINGS = 40
CANCELLED = 5


def main():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        has_data = db.scalar(select(func.count(Service.id))) or db.scalar(select(func.count(Booking.id)))
        if has_data:
            if "--reset" not in sys.argv:
                print("The database already has data. Run with --reset to delete it and add the demo data.")
                return
            db.execute(delete(BookingSlot))
            db.execute(delete(Booking))
            db.execute(delete(Service))
            db.commit()

        ensure_default_hours(db)
        for hours in db.scalars(select(WorkingHours)):
            hours.is_open = hours.weekday in HOURS
            if hours.is_open:
                hours.open_time, hours.close_time = HOURS[hours.weekday]
        services = [Service(name=n, price=p, duration_minutes=m) for n, p, m in SERVICES]
        db.add_all(services)
        db.commit()

        rng = random.Random(7)
        today = local_now().date()
        open_days = [d for d in (today + timedelta(days=i) for i in range(14)) if d.weekday() in HOURS]
        # pretend it is midnight, so the morning of today can have bookings too
        start_of_today = datetime.combine(today, time.min)

        created = []
        attempts = 0
        while len(created) < BOOKINGS and attempts < 2000:
            attempts += 1
            service = rng.choices(services, WEIGHTS)[0]
            # closer days are busier
            day = rng.choices(open_days, [15 - (d - today).days for d in open_days])[0]
            starts = free_start_times(db, service, day, now=start_of_today)
            if not starts:
                continue
            number = len(created) + 1
            created.append(
                create_booking(
                    db,
                    service,
                    rng.choice(starts),
                    f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                    f"+7700000{number:04d}",
                    now=start_of_today,
                )
            )

        for booking in rng.sample(created, CANCELLED):
            cancel_booking(db, booking)

        print(f"Added {len(services)} services and {len(created)} fake bookings ({CANCELLED} cancelled).")


if __name__ == "__main__":
    main()
