# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from typing import List

@dataclass
class RuntimeLimits:
    page_size: int = 10000
    http2: bool = True
    timeout_s: float = 30.0

@dataclass
class OutputConfig:
    csv_path: str = "files/users_sample.csv"
    overwrite: bool = True

@dataclass
class UsersAppConfig:
    # ---- API ----
    endpoint: str = "/api/users"
    id_param: str = "usersToInclude"
    fields: List[str] = field(default_factory=lambda: ["id", "username", "name", "email"])

    # IDs để test (theo bạn cung cấp)
    ids: List[str] = field(default_factory=lambda: [
        "6277729705839478686",
        "6277729705841389470",
        "6277729705866067870",
        "6277729705874792350",
        "6277729705876799390",
        "6277729705899581342",
        "6277729705903484830",
        "6277729705904418718",
        "6277729705925767070",
    ])

    # ---- runtime/output ----
    limits: RuntimeLimits = field(default_factory=RuntimeLimits)
    output: OutputConfig = field(default_factory=OutputConfig)

def get_users_config() -> UsersAppConfig:
    """Chuẩn cấu hình mặc định cho ứng dụng ngoài (no-datePeriod)."""
    return UsersAppConfig()
