# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

@dataclass
class RuntimeLimits:
    page_size: int = 10000
    day_workers: int = 3
    req_per_sec: float = 3.0
    http2: bool = True
    timeout_s: float = 30.0

@dataclass
class AlgorithmConfig:
    force_segmented_paging: bool = True      # bật giải thuật segmented-by-total (v2)
    segment_safety_ratio: float = 0.95       # “đầy” ~ 95% page_size
    segment_min_seconds: float = 1.0         # cắt nhỏ tối thiểu 1s

@dataclass
class OutputConfig:
    csv_path: str = "files/commission_sample.csv"
    overwrite: bool = True

@dataclass
class AppConfig:
    # ---- API ----
    endpoint: str = "/api/vndc_commission/accounts/vndc_commission_acc/history"
    start: datetime = datetime(2025, 10, 11, 0, 0, 0, tzinfo=timezone.utc)
    end:   datetime = datetime(2025, 10, 11, 23, 59, 59, tzinfo=timezone.utc)
    filters_qs: str = "chargedBack=false&transferFilters=vndc_commission_acc.commission_buysell"
    fields: List[str] = field(default_factory=lambda: [
        "date", "transactionNumber", "relatedAccount.user.id",
        "relatedAccount.user.display", "amount"
    ])

    # ---- runtime & thuật toán ----
    limits: RuntimeLimits = field(default_factory=RuntimeLimits)
    algo:   AlgorithmConfig = field(default_factory=AlgorithmConfig)
    output: OutputConfig   = field(default_factory=OutputConfig)

def get_config() -> AppConfig:
    """Chuẩn cấu hình mặc định cho ứng dụng ngoài."""
    return AppConfig()
