# onuslibs/logs.py
import os, logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

def _level(name: str) -> int:
    name = (name or "INFO").upper()
    return getattr(logging, name, logging.INFO)

def get_logger(name: str = "onuslibs") -> logging.Logger:
    logger = logging.getLogger(name)
    if getattr(logger, "_configured", False):
        return logger

    enable = os.getenv("ONUSLIBS_LOG_ENABLE", "false").lower() == "true"
    level  = _level(os.getenv("ONUSLIBS_LOG_LEVEL", "INFO"))
    logger.setLevel(level)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handlers = []

    # Console
    if os.getenv("ONUSLIBS_LOG_CONSOLE", "true").lower() == "true":
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        handlers.append(sh)

    # File (bật khi ONUSLIBS_LOG_ENABLE=true)
    if enable:
        log_file = os.getenv("ONUSLIBS_LOG_FILE", "logs/onuslibs.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        rotate  = os.getenv("ONUSLIBS_LOG_ROTATE", "size").lower()   # size|time
        backups = int(os.getenv("ONUSLIBS_LOG_BACKUP_COUNT", "7"))
        if rotate == "time":
            fh = TimedRotatingFileHandler(log_file, when="midnight", backupCount=backups, encoding="utf-8")
        else:
            max_bytes = int(os.getenv("ONUSLIBS_LOG_MAX_BYTES", "10485760"))  # 10MB
            fh = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        fh.setFormatter(fmt)
        handlers.append(fh)

    for h in handlers:
        logger.addHandler(h)
    logger._configured = True
    return logger

def scrub_headers(h: dict | None) -> dict | None:
    if not h:
        return h
    out = dict(h)
    if "Access-Client-Token" in out:
        tok = out["Access-Client-Token"] or ""
        out["Access-Client-Token"] = (tok[:4] + "…" + tok[-4:]) if len(tok) > 8 else "****"
    return out
