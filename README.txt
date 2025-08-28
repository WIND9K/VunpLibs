Cài đặt
Cài local (khuyên dùng khi phát triển)
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e .

Cài từ GitHub (sau khi bạn public)
pip install "git+https://github.com/<your-org-or-user>/OnusLibs.git@v1.0.0"


Thay v1.0.0 bằng tag/commit bạn phát hành.

Cấu hình token ví (Keyring, per-project)

Mỗi dự án dùng profile riêng để tách biệt token.

# Windows
python -m onuslibs.cli --profile MyProject
# Sẽ prompt:
# WALLET_BASE: https://wallet.vndc.io
# ACCESS_CLIENT_TOKEN: ****** (nhập ẩn)


Token được lưu trong OS Keyring theo service OnusLibs:MyProject.

Xoay vòng / xoá token (trong code)
from onuslibs.token_manager import rotate_access_token, clear_wallet_credentials
rotate_access_token("MyProject", "NEW_TOKEN_VALUE")
clear_wallet_credentials("MyProject")

Cấu hình DB (.env)

.env chỉ dành cho CSDL. Không đưa token ví vào đây.

Tạo file .env (ở thư mục gốc dự án sử dụng OnusLibs, hoặc đặt biến đường dẫn — xem bên dưới):

# DB only
MYSQL_HOST=localhost
MYSQL_DB=onus
MYSQL_USER=user
MYSQL_PASS=pass


Vị trí nạp .env:

Ưu tiên đường dẫn chỉ định: ONUSLIBS_ENV_PATH=/path/to/.env

Nếu không có, lib sẽ tự tìm .env gần CWD

Cuối cùng fallback .env ở thư mục cha của CWD

Cách dùng trong code
from onuslibs.db_config import DB_CONFIG
from onuslibs.token_manager import get_wallet_credentials

# Lấy token ví theo profile (đã nhập qua CLI)
creds = get_wallet_credentials(profile="MyProject")
base, token = creds["base"], creds["token"]   # ❗đừng log token

# DB từ .env
db_host = DB_CONFIG["host"]
db_name = DB_CONFIG["database"]

# ví dụ khởi tạo client ví (tuỳ dự án)
# client = WalletClient(base_url=base, token=token)


(Tuỳ chọn) đặt profile mặc định bằng biến môi trường:

# Windows
$env:ONUSLIBS_PROFILE="MyProject"
# macOS/Linux
export ONUSLIBS_PROFILE="MyProject"

Bảo mật – kiểm tra nhanh

Token ví không nằm trong repo / .env / log.

Mỗi dự án 1 profile riêng → tách biệt tuyệt đối.

.gitignore phải chặn: .env, secret.key, encrypted_data.json, .venv/, __pycache__/.

Troubleshooting (ngắn gọn)

ModuleNotFoundError: onuslibs
→ Chưa cài: pip install -e . (đúng venv).

DB_CONFIG trả None
→ Sai vị trí .env. Đặt ONUSLIBS_ENV_PATH hoặc để .env ở gốc dự án (hoặc thư mục cha của CWD).

Keyring lỗi backend (Windows hiếm gặp)
→ Mở PowerShell “Run as Administrator” hoặc cài pip install keyrings.alt và cấu hình backend thay thế.

API bề mặt (tối thiểu)

onuslibs.cli

python -m onuslibs.cli --profile <name> [--base ... --token ...]

onuslibs.token_manager

get_wallet_credentials(profile, allow_env_fallback=True, allow_parent_env_fallback=True) → {"base","token"}

set_wallet_credentials(profile, base, token)

rotate_access_token(profile, new_token)

clear_wallet_credentials(profile)

onuslibs.db_config

DB_CONFIG = {"host","user","password","database"} (nạp từ .env)