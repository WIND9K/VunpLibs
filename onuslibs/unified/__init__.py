# Unified facade package

from .api import fetch_json
from .segmented import fetch_json_segmented  # NEW

__all__ = ["fetch_json", "fetch_json_segmented"]
