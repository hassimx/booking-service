# Nord booking

Online booking for a small barbershop. Clients pick a service and a free time, the owner manages bookings, services and working hours in an admin page.

Nord is a made-up barbershop. The demo data (names, phone numbers, bookings) is made up too.

Built with Python, FastAPI, SQLAlchemy and plain HTML, CSS and JavaScript. It uses SQLite by default and can switch to PostgreSQL.

![Booking page](docs/img/booking.png)

![Admin page](docs/img/admin.png)

![Swagger docs](docs/img/swagger.png)

## Run it locally

You need Python 3.11 or newer. I tested it on Python 3.14.

Windows (PowerShell):

```
git clone https://github.com/hassimx/booking-service.git
cd booking-service
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python create_env.py
.venv\Scripts\python seed_demo.py
.venv\Scripts\python -m uvicorn app.main:app --reload
```

macOS / Linux:

```
git clone https://github.com/hassimx/booking-service.git
cd booking-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python create_env.py
python seed_demo.py
uvicorn app.main:app --reload
```

Then open:

- http://127.0.0.1:8000 for the booking page
- http://127.0.0.1:8000/admin for the admin page
- http://127.0.0.1:8000/docs for the API docs (Swagger)

## Settings and admin password

`create_env.py` asks for an admin username and password and writes a `.env` file. The file has a random `SECRET_KEY` that signs the login cookie and a hash of the password. The password itself is never saved.

You can also copy `.env.example` to `.env` and fill it in by hand. The comments in that file explain each variable. The real `.env` is in `.gitignore`.

To use PostgreSQL, set `DATABASE_URL` to something like `postgresql://user:password@host:5432/dbname`. The tables are created on start.

If the admin login does not work, check that `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` are in `.env`. Without them the login answers with an error that says so.

## Demo data

```
python seed_demo.py
```

This adds 7 services, working hours and 40 made-up bookings for the next two weeks (5 of them cancelled). It does nothing if the database already has data. Use `python seed_demo.py --reset` to delete everything and start again.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a temporary database, so they never touch your real one. They cover double booking, overlapping bookings of different lengths, cancelling, the phone check and the admin login.

## Booking assistant (AI)

Above the booking form there is one text field. A client can write what they want in their own words, in English or Russian, for example "haircut tomorrow after 5" or "стрижка и борода в субботу утром". The assistant picks the service, the day and the time window and shows up to three free times. One click fills in the form.

- With `GEMINI_API_KEY` set, Gemini reads the request and returns the service, date and time window as JSON.
- Without a key, or if the AI call fails, a rule-based parser handles common phrases (today, tomorrow, weekdays, dates like 15.10, "after 5", "at 14:30", morning and evening).
- The AI only understands the request. Free times always come from the database, so it cannot suggest a time that is taken or outside working hours.

The endpoint is `POST /api/assistant` with `{"text": "..."}`. The code is in `app/assistant.py`.

## How double bookings are stopped

Services have different lengths, so a unique start time is not enough. A 60 minute haircut at 10:00 and a 30 minute beard trim at 10:30 start at different times but overlap.

Every booking saves one row in `booking_slots` for each 15 minutes it uses. The slot time is the primary key, so the database refuses a second booking on a time that is already used. The code catches that error and answers `409` with a clear message. There is also a check before the insert, but it only exists to give a friendly answer in the normal case. Two requests can pass it at the same moment, and the primary key is what stops the second one. Cancelling deletes the rows of that booking, which frees the time.

`test_many_requests_at_once_book_the_slot_once` sends 8 requests for the same time at once and expects one `201` and seven `409`.

## Deploy on Render

I have not deployed it yet. The repo has a `render.yaml` for a free Render web service.

1. Run `python create_env.py` locally and copy the `ADMIN_PASSWORD_HASH` line from the new `.env`.
2. On Render choose New, then Blueprint, and select this repo.
3. When Render asks for `ADMIN_PASSWORD_HASH`, paste the hash.
4. Open the Render URL. The first request after a pause is slow on the free plan.

On the free plan the disk is erased on every restart. With SQLite the demo data is added again each start, and new bookings are lost. For data that stays, create a PostgreSQL database on Render and set its URL as `DATABASE_URL`.

## Project layout

```
app/            FastAPI app: models, schemas, booking logic, routes
static/         the two pages (index.html, admin.html), CSS, JS, fonts
tests/          pytest tests
seed_demo.py    demo data
create_env.py   makes the .env file
scripts/        script that makes the screenshots in docs/img
```

Fonts are Young Serif and Hanken Grotesk (SIL Open Font License), served from `static/fonts`.

## What I learned

The hardest part was stopping double bookings when services have different lengths. A unique start time did not work, so I save one row per 15 minutes and let the database refuse duplicates. I also learned to test the race by sending many requests at once, because a normal test with two requests in a row never reaches the database error.
