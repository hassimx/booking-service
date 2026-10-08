# Takes the three README screenshots. Start the app with demo data first, then run:
#   ADMIN_PASSWORD=your-password python scripts/make_screenshots.py
# Needs: pip install playwright (uses the Edge or Chrome that is already installed)
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("ADMIN_PASSWORD")
OUT = Path(__file__).resolve().parent.parent / "docs" / "img"
WIDTH = 1000


def open_browser(playwright):
    for channel in ("msedge", "chrome"):
        try:
            return playwright.chromium.launch(channel=channel)
        except Exception:
            continue
    sys.exit("No Edge or Chrome found. Run: python -m playwright install chromium")


def page_bottom(page, selector):
    return page.evaluate(f"document.querySelector('{selector}').getBoundingClientRect().bottom + scrollY")


def busiest_day(page, today):
    best, best_count = today, -1
    for offset in range(14):
        day = today + timedelta(days=offset)
        rows = page.request.get(f"{BASE}/api/admin/bookings?date={day}&status=active").json()
        if len(rows) > best_count:
            best, best_count = day, len(rows)
    return best


# a day that is busy but still has some free times for the service
def busy_day_with_free_times(page, today, service_id):
    best, best_count = None, 99
    for offset in range(1, 14):
        day = today + timedelta(days=offset)
        times = page.request.get(f"{BASE}/api/slots?service_id={service_id}&date={day}").json()["times"]
        if 8 <= len(times) < best_count:
            best, best_count = day, len(times)
    return best


def log_in(page):
    page.goto(f"{BASE}/admin")
    page.fill("#username", USERNAME)
    page.fill("#password", PASSWORD)
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#dashboard:not([hidden])")
    page.wait_for_selector("#bookings-list tbody tr")


def main():
    if not PASSWORD:
        sys.exit("Set ADMIN_PASSWORD to the password of the running app.")
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = open_browser(playwright)
        # bypass_csp lets playwright run its own checks on pages that block inline scripts
        page = browser.new_context(viewport={"width": WIDTH, "height": 900}, bypass_csp=True).new_page()

        # admin list
        log_in(page)
        today = date.fromisoformat(page.evaluate("document.querySelector('#day-input').value"))
        day = busiest_day(page, today)
        page.fill("#day-input", str(day))
        page.dispatch_event("#day-input", "change")
        page.wait_for_function("document.querySelector('#day-summary').innerText.length > 0")
        page.evaluate("document.fonts.ready")
        page.evaluate("document.activeElement && document.activeElement.blur()")
        height = page_bottom(page, "#bookings-list") + 24
        page.screenshot(path=OUT / "admin.png", full_page=True, clip={"x": 0, "y": 0, "width": WIDTH, "height": height})

        # client booking page
        services = page.request.get(f"{BASE}/api/services").json()
        skin_fade = next(s for s in services if s["name"] == "Skin fade")
        booking_day = busy_day_with_free_times(page, today, skin_fade["id"])
        page.goto(BASE)
        page.locator("label.choice", has_text="Skin fade").click()
        page.locator(f'input[name="date"][value="{booking_day}"]').locator("..").click()
        page.wait_for_selector("label.chip")
        page.locator("label.chip").nth(4).click()
        page.fill("#name", "Alex Demo")
        page.fill("#phone", "+7 700 000 00 99")
        page.evaluate("document.fonts.ready")
        page.evaluate("document.activeElement && document.activeElement.blur()")
        height = page_bottom(page, "#book") + 24
        page.screenshot(path=OUT / "booking.png", full_page=True, clip={"x": 0, "y": 0, "width": WIDTH, "height": height})

        # swagger
        page.goto(f"{BASE}/docs")
        page.wait_for_selector(".opblock")
        page.click('.opblock-post:has(.opblock-summary-path[data-path="/api/bookings"]) .opblock-summary-control')
        page.wait_for_selector(".opblock-post.is-open .responses-table")
        height = page.evaluate("document.querySelector('.models').getBoundingClientRect().top + scrollY")
        page.screenshot(path=OUT / "swagger.png", full_page=True, clip={"x": 0, "y": 0, "width": WIDTH, "height": height})

        browser.close()
    print("Saved screenshots to", OUT)


if __name__ == "__main__":
    main()
