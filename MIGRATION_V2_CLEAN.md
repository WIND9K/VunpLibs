# Migration sang OnusLibs v2 (CLEAN REPLACE)

## Xoá hoàn toàn code cũ
1) Trong VS Code (đang ở nhánh v2): Xoá mọi file/thư mục cũ TRỪ `.git/`, `.github/`, `LICENSE`, `README` nếu muốn giữ.
2) Copy toàn bộ nội dung bộ **OnusLibs v2 (CLEAN)** này vào repo.
3) Commit: `feat(v2): clean replace with new framework stack` → Push.

## Đổi ENV/.env sang khoá mới
- BẮT BUỘC dùng: `ONUSLIBS_ACCESS_CLIENT_TOKEN`, `ONUSLIBS_WALLET_BASE`.
- Không còn hỗ trợ tên cũ: `ONUSLIBS_TOKEN`, `ONUSLIBS_BASE_URL`, ...

## Kiểm tra chạy
- Cài deps (xem README). 
- Chạy script mẫu `fetch(...)` theo README.
