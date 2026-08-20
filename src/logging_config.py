"""Logging setup with sensitive data redaction."""

import logging
import re
import sys
from typing import Optional


class SensitiveFilter(logging.Filter):
    """Filter that masks webhook URLs and passwords if they inadvertently appear in logs."""

    WEBHOOK_PATTERN = re.compile(r'https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+')

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.WEBHOOK_PATTERN.sub(
                'https://discord.com/api/webhooks/***/[REDACTED]', record.msg
            )
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self.WEBHOOK_PATTERN.sub('https://discord.com/api/webhooks/***/[REDACTED]', v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.WEBHOOK_PATTERN.sub('https://discord.com/api/webhooks/***/[REDACTED]', a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure structured console logging with custom format and filters."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on re-init
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SensitiveFilter())

    root_logger.addHandler(console_handler)

    # Silence noisy external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    return logging.getLogger("crous_monitor")
