

---

# CLI — Tham số chi tiết & `-h/--help`

Các script CLI trong `examples/` đều dùng **argparse**, vì vậy luôn có trợ giúp:
```bash
python -m examples.fetch_commission_history -h
python -m examples.get_commission -h
```

## `examples.fetch_commission_history`
Kéo lịch sử hoa hồng theo ngày/khoảng ngày. Phần lớn flag là **cấu hình app** (build `params`) để gửi lên API, còn `fetch_json(...)` lo phân trang/lấy dữ liệu.

**Flags chính**

- `--date YYYY-MM-DD`  
  Lấy dữ liệu trong **1 ngày** (giờ 00:00:00 → 23:59:59).
- `--start-date YYYY-MM-DD` `--end-date YYYY-MM-DD`  
  Lấy dữ liệu trong **khoảng ngày** (bao gồm cả ngày cuối).
- `--preset {minimal,basic,full}` *(mặc định: `basic`)*  
  Bộ `fields` có sẵn:
  - `minimal`: `date,amount`
  - `basic`: `date,transactionNumber,relatedAccount.user.id,relatedAccount.user.display,amount,description`
  - `full`: đầy đủ hơn (tuỳ mã script).
- `--fields a,b,c` | `--fields-file path.txt`  
  Ghi đè/thêm `fields` (CSV hoặc mỗi dòng 1 field trong file).
- `--page-size N`  
  **Ghi đè** `pageSize` cho lần chạy này. Nếu không đặt, Facade sẽ dùng `ONUSLIBS_PAGE_SIZE` (ENV), nếu vẫn không có sẽ mặc định `10000`.
- `--order {dateAsc,dateDesc}`  
  Gửi lên API qua `orderBy`.
- `--filters <transferFilters>`  
  Gửi lên API `transferFilters`, ví dụ: `vndc_commission_acc.commission_buysell`.
- `--charged-back {true,false}`  
  Gửi lên API `chargedBack`.
- `--out-json file.json` / `--out-csv file.csv`  
  Xuất dữ liệu ra file (CSV dùng `tools/write_csv.py`, tự flatten dot-path).

**Flags liên quan phân trang/hiệu năng**

- `--parallel`  
  Bật **đọc song song** các trang (dựa module pagination song song nếu có).  
  *Khuyến nghị* chỉ dùng khi `orderBy` ổn định (date asc/desc) và endpoint an toàn.
- `--workers N`  
  Số luồng khi `--parallel` (mặc định lấy từ `ONUSLIBS_MAX_INFLIGHT`, clamp ≤ 16).
- `--page-size N`  
  (Nhắc lại) Kích thước trang — ảnh hưởng trực tiếp đến số trang và việc API có cho đi tiếp không.

**Flags quan sát/debug (chỉ dùng khi test)**

- `--debug-flow`  
  In log từng trang, trực quan hoá luồng gọi.
- `--delay-ms N`  
  Ngủ N mili-giây **trước mỗi request** để dễ quan sát dòng log.
- `--max-pages N`  
  Giới hạn số trang để demo/kiểm thử (không lấy hết).
- `--print-total`  
  In `total_items` sau khi gom (nếu script bật tuỳ chọn này).

**Ví dụ**
```bash
# 1 ngày, preset basic, tuần tự
python -m examples.fetch_commission_history --date 2025-10-11 --preset basic --page-size 2000

# Quan sát tuần tự: log + delay
python -m examples.fetch_commission_history --date 2025-10-11 --preset basic \
  --page-size 400 --debug-flow --delay-ms 300 --max-pages 5

# Đa luồng (nếu endpoint an toàn): giữ thứ tự yield theo page
python -m examples.fetch_commission_history --date 2025-10-11 --preset basic \
  --page-size 2000 --parallel --workers 4
```

> **Lưu ý:** Một số API có thể **giới hạn** số trang/record theo `pageSize`. Khi thấy tổng nhỏ hơn `X-Total-Count`:
> - Giảm `--page-size` (1k–5k thường ổn định), hoặc
> - Chia `datePeriod` theo khung giờ và chạy nhiều lượt (gom lại).

---

## `examples.get_commission`
Phiên bản gọn, lấy commission theo ngày/khoảng ngày với các flag tương tự, thường dùng để **xuất JSON nhanh**.

**Flags chính**
- `--date` **hoặc** `--start-date/--end-date`
- `--preset {minimal,basic,full}`
- `--fields a,b,c` | `--fields-file path.txt`
- `--page-size N` | `--order {dateAsc,dateDesc}`
- `--filters <transferFilters>` | `--charged-back {true,false}`
- `--out-json file.json`

**Ví dụ**
```bash
python -m examples.get_commission --date 2025-10-11 --preset full --page-size 2000 --out-json out.json
```

---

## Biến ENV (tóm tắt)
- `ONUSLIBS_BASE_URL` *(bắt buộc)*
- `ONUSLIBS_PAGE_SIZE`, `ONUSLIBS_REQ_PER_SEC`, `ONUSLIBS_MAX_INFLIGHT`, `ONUSLIBS_TIMEOUT_S`, `ONUSLIBS_HTTP2`, `ONUSLIBS_VERIFY_SSL`, `ONUSLIBS_PROXY`
- `ONUSLIBS_SECRETS_BACKEND=keyring`
- `ONUSLIBS_KEYRING_SERVICE=OnusLibs`
- `ONUSLIBS_KEYRING_ITEM=ACCESS_CLIENT_TOKEN`
- `ONUSLIBS_FALLBACK_ENV=true` *(dev/test; prod nên false)*

> Ở mức **thư viện**, `fetch_json(...)` hiểu các tham số chung (fields, paginate, page_size, order_by, unique_key, strict_fields, on_batch, parallel, workers...).  
> Ở mức **app**, các flag đặc thù endpoint (vd `transferFilters`, `chargedBack`, `datePeriod`) sẽ được map vào `params` gửi lên API.

---
