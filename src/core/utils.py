import datetime

import pytz

from config import settings


def get_current_time() -> datetime.datetime:
    return datetime.datetime.now(pytz.timezone(settings.TIMEZONE))