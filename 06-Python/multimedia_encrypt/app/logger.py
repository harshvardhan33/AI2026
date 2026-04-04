"""
Centralised logging for the Encrypted Vault application.

Format:
    2026-04-04 10:30:00.123 | INFO     | upload       | [d5c4c564] Received: photo.jpg
    2026-04-04 10:30:00.456 | INFO     | analysis     | [d5c4c564] Routed to image_crew
    2026-04-04 10:30:02.789 | ERROR    | image_crew   | [d5c4c564] YOLO failed: ...

Log file: logs/app.log  (also mirrored to stdout)
"""
from __future__ import annotations

import logging
from pathlib import Path

_configured = False


class _PipeFormatter(logging.Formatter):
    """Fixed-width pipe-delimited formatter for easy readability."""
    def format(self, record: logging.LogRecord) -> str:
        ts     = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        ms     = f"{record.msecs:03.0f}"
        level  = f"{record.levelname:<8}"
        name   = f"{record.name.split('.')[-1]:<12}"   # last segment only
        return f"{ts}.{ms} | {level} | {name} | {record.getMessage()}"


def setup_logging() -> None:
    """Configure the 'app' logger hierarchy. Safe to call multiple times."""
    global _configured
    if _configured:
        return
    _configured = True

    Path("logs").mkdir(exist_ok=True)
    formatter = _PipeFormatter()

    root = logging.getLogger("app")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    # ── File handler (full detail) ────────────────────────────────────────────
    fh = logging.FileHandler("logs/app.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # ── Console handler (INFO and above) ─────────────────────────────────────
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'app' namespace."""
    setup_logging()
    return logging.getLogger(f"app.{name}")
