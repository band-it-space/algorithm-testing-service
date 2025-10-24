import os
import logging
from logging.config import dictConfig


def setup_logging() -> None:
    """
    Configure application-wide logging with rotating file handlers.

    Environment variables:
    - LOG_DIR: directory for log files (default: /app/logs)
    - LOG_LEVEL: logging level string (default: INFO)
    - LOG_JSON: if 'true', use JSON-like formatter (default: false)
    """
    log_dir = os.getenv("LOG_DIR", "/app/logs")
    os.makedirs(log_dir, exist_ok=True)

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    json_enabled = os.getenv("LOG_JSON", "false").lower() == "true"

    # Basic plain or JSON-like format string
    if json_enabled:
        fmt = (
            '{"ts":"%(asctime)s","lvl":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}'
        )
    else:
        fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {"format": fmt},
            },
            "handlers": {
                "algo_file": {
                    "class": "logging.handlers.TimedRotatingFileHandler",
                    "filename": os.path.join(log_dir, "algorithm-worker.log"),
                    "when": "midnight",
                    "backupCount": 7,
                    "encoding": "utf-8",
                    "formatter": "default",
                    "level": level,
                },
                "result_file": {
                    "class": "logging.handlers.TimedRotatingFileHandler",
                    "filename": os.path.join(log_dir, "result-worker.log"),
                    "when": "midnight",
                    "backupCount": 7,
                    "encoding": "utf-8",
                    "formatter": "default",
                    "level": level,
                },
                "api_file": {
                    "class": "logging.handlers.TimedRotatingFileHandler",
                    "filename": os.path.join(log_dir, "api.log"),
                    "when": "midnight",
                    "backupCount": 7,
                    "encoding": "utf-8",
                    "formatter": "default",
                    "level": level,
                },
                "file_write_file": {
                    "class": "logging.handlers.TimedRotatingFileHandler",
                    "filename": os.path.join(log_dir, "file-write-worker.log"),
                    "when": "midnight",
                    "backupCount": 7,
                    "encoding": "utf-8",
                    "formatter": "default",
                    "level": level,
                },                 
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": level,
                },
            },
            "loggers": {
                "app.workers.algorithm_worker": {
                    "handlers": ["algo_file", "console"],
                    "level": level,
                    "propagate": False,
                },
                "app.workers.result_worker": {
                    "handlers": ["result_file", "console"],
                    "level": level,
                    "propagate": False,
                },
                "app.workers.file_write_worker": {
                    "handlers": ["file_write_file", "console"],
                    "level": level,
                    "propagate": False,
},
                "app.api": {
                    "handlers": ["api_file", "console"],
                    "level": level,
                    "propagate": False,
                },
            },
            "root": {"handlers": ["console"], "level": level},
        }
    )


