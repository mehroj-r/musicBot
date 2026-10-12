import logging
import sys


def setup_logging(level: str) -> None:
    # Docker collects stdout, so there are no log files to rotate
    logging.basicConfig(
        level=level.upper(),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    # Keep third-party chatter out of the logs
    for noisy in ("aiosqlite", "alembic", "PIL", "telethon"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
