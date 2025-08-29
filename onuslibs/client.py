import os
import sys
from getpass import getpass

class OnusAuth:
    def __init__(self, access_client_token: str | None = None):
        token = access_client_token or os.environ.get("ACCESS_CLIENT_TOKEN")
        if not token:
            # Nếu chạy trong terminal, cho phép nhập token
            if sys.stdin.isatty():
                print("[OnusLibs] ACCESS_CLIENT_TOKEN is missing.")
                token = getpass("Please enter ACCESS_CLIENT_TOKEN: ").strip()
                if not token:
                    raise RuntimeError("ACCESS_CLIENT_TOKEN is required but not provided.")
                # Có thể gán tạm vào env để lần sau session còn dùng
                os.environ["ACCESS_CLIENT_TOKEN"] = token
            else:
                # Non-interactive thì raise luôn
                raise RuntimeError(
                    "ACCESS_CLIENT_TOKEN is missing. "
                    "Set $env:ACCESS_CLIENT_TOKEN before running."
                )
        self.access_client_token = token

    def headers(self) -> dict[str, str]:
        return {"Access-Client-Token": self.access_client_token}
