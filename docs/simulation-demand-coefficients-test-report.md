# Kết quả kiểm tra hệ số nhu cầu và độ nhạy

Ngày: **11/10/2026**, Windows local, Python trong `.venv`. Model `integrated-building-1.4`, library `thu-duc-demo-library-1.3`.

## 1. Test tự động

```powershell
$env:PYTHONPATH='backend;etl'
.\.venv\Scripts\python.exe -m pytest backend/tests -q --junitxml=test-results/simulation-parameters-backend.xml
```

**157 đạt, 4 bỏ qua, 0 lỗi/thất bại; 39,816 giây.** Bốn test bỏ qua cần môi trường PostGIS phù hợp. Lần này không chạy lại CI GitHub, Docker hoặc Linux.

Test mới kiểm tra:

- Điện văn phòng chuyển 116,4 kWh/m²/năm sang ngày lịch, giữ năm 2015 và nhãn benchmark lịch sử; profile demo giữ 0,14.
- Không gán mức tối thiểu QCVN hoặc trips toàn thành phố thành hệ số nhu cầu tòa nhà đã đo.
- Catalog bao phủ hệ số theo công năng, mẫu số và trạng thái nguồn; trips nhân viên/điện reuse thực sự tác động công thức.
- Bảo toàn ledger nước/reuse/nước thải; OAT chỉ thay hệ số được chọn, giữ run cha.
- Kết luận tăng nhu cầu có thể ổn định trong khi kết luận vượt capacity đổi.
- Giới hạn mode share/số nguyên; từ chối hệ số sai, không tương thích công năng/mode hoặc request sai.
- Catalog/preflight/save/read qua API; native sensitivity chạy SUMO thật, cùng giờ, cân bằng số xe và ZIP không trùng file.
- Sửa lỗi SUMO synthetic ghi kết quả vào context sau hash. Chỉ phục hồi lỗi xác định này ở run cũ nếu khôi phục được hash gốc; context bị đổi hệ số vẫn bị từ chối.

## 2. Smoke test qua HTTP local

API được khởi động lại để nạp code mới tại **http://127.0.0.1:8003**. Swagger: **http://127.0.0.1:8003/api/v1/docs**. Không sửa frontend; giao diện demo cũ chưa có nút phân tích độ nhạy mới.

```powershell
.\.venv\Scripts\python.exe scripts/test-simulation-parameters-local.py --snapshot-id 64334deff008126baf2d91c8c57197d9822a76eaf667a6a66edf7414b1e112a8
```

**Đạt; 71,53 giây** cho toàn luồng: catalog reviewed/demo → preflight → predict → 6 case demand → 2 case traffic (4 lần SUMO) → đọc lại → xuất ZIP → xác nhận run gốc không thay đổi.

| Kết quả | Giá trị |
|---|---|
| Run dự đoán | `10eebde2-8aa9-42a5-83b7-bfcdd3ad0be1` |
| Run con demand | `aec83e58-6805-4854-9271-8c932a649d51` |
| Run con native traffic | `f771ee14-5159-454d-8e48-4f0b46ae25f2` |
| Mạng giao thông | Nhập OSM từ snapshot |
| Catalog | 57 hệ số; 1 mặc định có nguồn số trực tiếp áp dụng |
| ZIP native | 6.225.649 byte, kiểm tra CRC đạt, không trùng tên, có artifact từng case |

Nguồn nền là snapshot đã tải của team/OSM/WorldCover/WorldPop. Buildings gửi qua `map_context` vẫn là fixture có nhãn `TEST_FIXTURE_NOT_REAL_GOONG`. Occupancy hiện trạng không biết từ footprint/height, do đó không coi baseline trips bằng 0 là số đo thực địa. Background flows, OD/mode/đèn/hành vi và spare capacity chưa được hiệu chỉnh bằng khảo sát địa phương.

## 3. Một kết quả minh họa

Thiết kế: chung cư 12 tầng, 600 cư dân, 12 nhân viên, 80 khách/ngày và 12 trụ EV, theo sample hiện có. Các số dưới đây thuộc đúng run ở trên.

| Chỉ số nhu cầu | Trước xây | Sau xây | Biên độ chênh lệch trong các case OAT đã thử |
|---|---:|---:|---:|
| Nước cấp mới (m³/ngày) | 0,538 | 78,518 | +56,381 đến +99,581 |
| Nước thải (m³/ngày) | 0 | 58,944 | +41,261 đến +76,224 |
| Điện (kWh/ngày) | 718,498 | 2.890,659 | +1.621,313 đến +2.723,009 |
| Đỉnh profile điện (kW) | 68,897 | 328,967 | +207,249 đến +312,891 |

Ba hệ số được thử độc lập: nước cư dân, tỷ lệ hồi lưu và điện chung cư; mỗi hệ số ×0,7/×1,3. Return fraction ×1,3 bị giới hạn tại 1. Đây là biên độ giữa các **kịch bản đã thử**, không phải khoảng tin cậy hoặc mọi tổ hợp.

- Cả 8 chỉ số nhu cầu giữ hướng tăng trong 6 case.
- Nước và nước thải đổi kết luận đạt/không đạt ngưỡng capacity giả định giữa các case.
- Điện vẫn không đạt ngưỡng spare capacity ở mọi case. Capacity điện so tải bổ sung tại cùng giờ, không lấy đơn thuần chênh lệch hai peak.

Native traffic thử trips cư dân 1,4 và 2,6/ngày, cùng giờ 18h, topology, seed và background:

| Case | Xe planned/completed sau xây | Delay trước/sau (s/completed trip) | Hàng chờ trước/sau (m) |
|---|---:|---:|---:|
| Low, 1,4 trips/cư dân/ngày | 2.137 / 2.137 | 33,179 / 33,623 | 16,54 / 26,78 |
| High, 2,6 trips/cư dân/ngày | 2.180 / 2.180 | 33,179 / 33,607 | 16,54 / 18,13 |

Mọi xe planned hoàn thành; không còn xe chưa khởi hành/dở dang trong các case này. Delay/queue không tăng đơn điệu theo số xe trong hai lần chạy: routing, timing và tương tác của mô phỏng có thể làm cực đại hàng chờ đổi. Hai case cùng seed không đủ kết luận quan hệ nhân quả hay độ chính xác; cần counts/calibration và nhiều seed trước khi dùng cho quyết định thực địa.

## 4. File kết quả local

Script tạo các file không đưa vào Git trong `test-results/`:

- `simulation-parameters-backend.xml`: toàn bộ pytest backend.
- `simulation-parameters-local-report.json`: kiểm tra HTTP và số liệu tóm tắt.
- `parameters-demo.json`: run dự đoán mới.
- `parameters-demand-sensitivity.json`, `parameters-traffic-sensitivity.json`: run phân tích.
- `parameters-traffic-sensitivity.zip`: JSON và input/output engine phục vụ xem lại.

Các run được lưu ở `.runtime/background-smoke/runs`; artifact tại `.runtime/background-smoke/solvers`. Nhận lại qua GET `/api/v1/scenarios/integrated/{id}` khi API dùng cùng thư mục lưu.

## 5. Phạm vi kết luận

Đã kiểm tra code, API, bảo toàn dữ liệu và engine chạy được. **Chưa xác thực độ chính xác dự báo bằng quan sát thực tế.** Trong 57 hệ số đã chuẩn hóa, chỉ điện văn phòng áp dụng benchmark địa phương; nghiên cứu đó không hiệu chỉnh điện chung cư của case này. Những hệ số chưa đủ nguồn vẫn có nhãn giả định và không được nâng thành “dữ liệu thật”.

Không commit, push hay deploy trong đợt này. [Bàn giao API và nguồn hệ số](simulation-demand-coefficients.md).
