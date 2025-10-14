# onuslibs/core/logger.py
import logging
import sys

_DEF_FMT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"

def setup_logging(level: int = logging.INFO) -> None:
    if logging.getLogger().handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_DEF_FMT))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
