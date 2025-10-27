import structlog

REDACT_KEYS = {"ACCESS_CLIENT_TOKEN", "Authorization", "token", "DB_PASSWORD"}

def _redact(_, __, event_dict):
    for k in list(event_dict.keys()):
        if k in REDACT_KEYS:
            event_dict[k] = "***"
    return event_dict

def setup_logging(level: int = 20):
    structlog.configure(
        processors=[_redact, structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )
    return structlog.get_logger()
