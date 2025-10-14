# Changelog

## [1.1.0] - 2025-10-14
### Added
- Module `onuslibs/api.py` (call_api/get/post/put/delete + paginate_get).
- `onuslibs/core/logger.py` (setup_logging).
- Tests kết nối API/DB, test token_manager (mock keyring).
- Docstring cho các class/hàm chính.

### Changed
- Bổ sung logging cho mã hoá/giải mã trong `security/secure_manager.py`.

### Fixed
- Nhỏ: chuẩn hoá params khi gọi `/api/users` (statuses, usersToInclude).
