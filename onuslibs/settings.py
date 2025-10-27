from pydantic_settings import BaseSettings, SettingsConfigDict

class LibSettings(BaseSettings):
    # Chỉ dùng khóa mới v2 (quên hết tên cũ)
    WALLET_BASE: str = "https://wallet.vndc.io"
    ACCESS_CLIENT_TOKEN: str | None = None
    PAGE_SIZE: int = 20_000
    EPSILON_SECONDS: int = 1

    model_config = SettingsConfigDict(
        env_prefix="ONUSLIBS_",
        env_file=".env",
        extra="ignore",
    )
