__all__ = ["fetch", "to_csv", "to_db", "__version__"]
__version__ = "2.0.0"

try:
    from .quick import fetch, to_csv, to_db
except Exception as e:
    _IMPORT_ERROR = e
    def _missing(*args, **kwargs):
        raise RuntimeError(
            f"OnusLibs v2: không import được quick ({{_IMPORT_ERROR.__class__.__name__}}: {{_IMPORT_ERROR}}). "
            "Hãy cài deps: httpx, tenacity, keyring, pydantic, pydantic-settings, structlog."
        ) from _IMPORT_ERROR
    fetch = to_csv = to_db = _missing
