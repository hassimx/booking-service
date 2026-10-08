from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings

# bookings are stored in 15 minute cells, clients pick a start every 30 minutes
GRID_MINUTES = 15
START_STEP_MINUTES = 30


# all times in the database are the shop's local time, without a timezone
def local_now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone)).replace(tzinfo=None)
