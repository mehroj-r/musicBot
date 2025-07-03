import logging.config
import os

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detailed": {
            "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        },
        "simple": {
            "format": "%(levelname)s: %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "detailed",
            "level": "DEBUG",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "logs/app.log",
            "formatter": "detailed",
            "level": "INFO",
        },
        "error_file": {
            "class": "logging.FileHandler",
            "filename": "logs/errors.log",
            "formatter": "detailed",
            "level": "ERROR",
        },
    },
    "root": {
        "handlers": ["console", "file", "error_file"],
        "level": "DEBUG",
    },
}

# Make sure the logs directory exists
if not os.path.exists(os.getcwd()+"/logs"):
    os.makedirs("logs")

# Configure the logging system
logging.config.dictConfig(LOGGING_CONFIG)

# Suppress pymongo logging to avoid cluttering the logs
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("pymongo.server").setLevel(logging.WARNING)
logging.getLogger("pymongo.monitoring").setLevel(logging.WARNING)
logging.getLogger("pymongo.pool").setLevel(logging.WARNING)
logging.getLogger("pymongo.mongo_client").setLevel(logging.WARNING)

# Create a logger for the application
logger = logging.getLogger(__name__)