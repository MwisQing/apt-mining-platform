import logging
import logging.handlers
import os
import sys
import traceback


_log_dir = None


def _get_log_dir():
    global _log_dir
    if _log_dir is None:
        _log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "logs",
        )
        os.makedirs(_log_dir, exist_ok=True)
    return _log_dir


DETAILED_FMT = "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s"
CONCISE_FMT = "%(asctime)s | %(levelname)-7s | %(message)s"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
BACKUP_COUNT = 3


def setup_logging():
    """Configure dual-log: detailed (full context) and concise (summary only)."""
    log_dir = _get_log_dir()

    # --- Detailed log handler (rotating) ---
    detailed_path = os.path.join(log_dir, "detailed.log")
    detailed_h = logging.handlers.RotatingFileHandler(
        detailed_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    detailed_h.setLevel(logging.DEBUG)
    detailed_h.setFormatter(logging.Formatter(DETAILED_FMT))

    # --- Concise log handler (rotating) ---
    concise_path = os.path.join(log_dir, "concise.log")
    concise_h = logging.handlers.RotatingFileHandler(
        concise_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    concise_h.setLevel(logging.INFO)
    concise_h.setFormatter(logging.Formatter(CONCISE_FMT))

    # --- Root logger ---
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(detailed_h)
    root.addHandler(concise_h)

    # Also keep console output for development
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(CONCISE_FMT))
    root.addHandler(console)

    # Capture unhandled exceptions
    def _excepthook(etype, value, tb):
        if issubclass(etype, KeyboardInterrupt):
            sys.__excepthook__(etype, value, tb)
            return
        root.critical(
            "Unhandled exception:\n%s",
            "".join(traceback.format_exception(etype, value, tb)),
        )

    sys.excepthook = _excepthook

    # Capture warnings
    logging.captureWarnings(True)

    root.info("Logging initialized (detailed=%s, concise=%s)", detailed_path, concise_path)
    return root
