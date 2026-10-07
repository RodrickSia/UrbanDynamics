# Báo cáo test local — đánh giá tác động công trình

## Cập nhật luồng dự tính → đánh giá → tạo gợi ý, ngày 05/10

Phiên bản hiện tại: `building-impact-2.0.0`. Giao diện chỉ nhận hiện trạng + công trình dự định xây; thiết kế cải thiện được hệ thống tạo sau khi đánh giá. Xem [hướng dẫn hiện tại](building-impact-prediction.md).

| Kiểm tra hiện tại | Kết quả |
|---|---|
| Windows, Python 3.13, toàn bộ backend/ETL với PostGIS thật | **77/77 đạt**, không skip |
| Linux Docker, Python 3.12, toàn bộ backend/ETL với PostGIS thật | **77/77 đạt**, không skip |
| Build backend, ETL, frontend scaffold | Thành công |
| API dự tính và tạo gợi ý | HTTP 201, kết quả lưu trong PostGIS |
| Edge headless | **10 nhóm kiểm tra đạt**, gồm sinh gợi ý sau dự tính, mở lại, xuất JSON, vẽ geometry, mobile và mất CDN |

15 test mới kiểm tra: luồng hai đầu vào, từ chối nhập sẵn `mitigated`, công thức nhu cầu giao thông/nước/nước thải/điện, công suất so với phần tăng thêm, bảo toàn footprint/số tầng/số người, giữ đúng diện tích/ngân sách, không tạo cải thiện miễn phí, không tự chuyển phương tiện thiếu căn cứ, yêu cầu chi phí vận hành rõ ràng, thiếu dữ liệu không gán hệ số, validation và lineage bản ghi.

Ví dụ **giả định**, 600 người sử dụng:

| Chỉ số | Công trình dự định xây | Gợi ý 1 do hệ thống tạo |
|---|---:|---:|
| Nước còn lại sau giữ nước | 544,32 m³ | 295,54 m³ |
| Chuyến xe giờ cao điểm | 80 chuyến/giờ | 60 chuyến/giờ |
| Nhu cầu nước | 48 m³/ngày | 30 m³/ngày |
| Nước thải | 38,4 m³/ngày | 24 m³/ngày |
| Điện cao điểm | 60 kW | 45 kW |

Gợi ý 1: chuyển khoảng 2.419,19 m² sân cứng sang đất xanh, 1.814,39 m² sang sân thấm; thêm 100 m³ giữ nước; chỉ tiêu xe cá nhân 60%, tiết kiệm nước 37,5%, giảm điện cao điểm 25%. Chi phí theo đơn giá giả định khoảng **829,08 triệu VND**, trong ngân sách giả định 1 tỷ. Giữ nguyên công trình, số tầng và 600 người.

Trạng thái **`partial_improvement`**: các mục tiêu khác đạt trong mô hình, dòng chảy vẫn cao hơn hiện trạng 214,10 m³. Không ép báo đạt bằng cách tự tăng ngân sách hoặc thu nhỏ công trình. Test riêng xác nhận hệ thống có thể đạt các mục tiêu trong một trường hợp nới giới hạn giữ nước/ngân sách; đây vẫn là giả định phần mềm.

Giao thông là dự tính nhu cầu chuyến xe; chưa xác nhận ùn tắc hoặc thời gian chờ. Công suất hạ tầng, hiệu quả tiết kiệm và chi phí là đầu vào giả định, chưa đối chiếu thực tế. Các file `test-results/` hiện phản ánh lần kiểm tra mới nhất. Chưa commit/push hoặc deploy máy 156.

---

## Ghi nhận phiên bản 1 trước khi sửa luồng

Ngày kiểm tra: **05/10/2026**. Phiên bản mô hình: `building-screening-1.0.0`.

## Kết quả

| Kiểm tra | Kết quả |
|---|---|
| Windows, Python 3.13, toàn bộ backend/ETL với PostGIS thật | **62/62 đạt**, không skip |
| Linux Docker, Python 3.12, toàn bộ backend/ETL với PostGIS thật | **62/62 đạt**, không skip |
| Build backend, ETL, frontend scaffold | Thành công |
| API cũ: health, ready, layers, history, risk, land price, price rows, satellite, rain scenario | HTTP 200 |
| Trang `/simulation` | HTTP 200 |
| Tạo bài đánh giá ba phương án | HTTP 201 |
| Đọc lại kết quả đã lưu trên PostGIS | HTTP 200, nội dung trùng nguyên kết quả tạo |
| Edge headless: 9 nhóm kiểm tra giao diện | Đạt |
| JavaScript syntax (`node --check`) | Đạt |

26 test mới bao gồm phép tính có kết quả biết trước, cân bằng thể tích, phương án không đổi, mưa bằng 0, dung tích giữ nước quá lớn, polygon có lỗ/đảo chiều, footprint trong/ngoài khu đất, tổng diện tích sai, nguồn giả định trống, hệ số ngoài giới hạn, geometry không hợp lệ, NaN/Infinity, lưu/mở lại nhiều lần chạy, lỗi database và geometry PostGIS SRID 4326.

Lỗi NaN/Infinity trong phản hồi validation đã sửa: API trả 422 với tên trường và thông báo, không echo dữ liệu đầu vào gây lỗi serialize. Các API cũ được kiểm tra cùng bộ test.

Các kiểm tra giao diện:

1. Nạp ví dụ, xác nhận, tính và hiển thị ba phương án.
2. JSON tải xuống khớp kết quả API.
3. Link đã lưu mở lại đúng kết quả và đầu vào.
4. Sửa đầu vào ẩn kết quả cũ; tính lại có UUID và SHA256 mới.
5. Tỷ lệ bề mặt sai tổng 100% bị từ chối.
6. Vẽ khu đất và footprint bằng thao tác con trỏ; tính thành công.
7. Viewport 390×844 không tràn ngang toàn trang; lỗi bố cục đã sửa.
8. Chặn CDN Leaflet: ví dụ và tính toán vẫn chạy qua chế độ không có bản đồ.
9. Không có lỗi JavaScript chưa xử lý.

Tile OpenStreetMap được chặn trong test trình duyệt để tránh phụ thuộc mạng. Thao tác vẽ kiểm tra bằng Leaflet thực, nhưng test này không xác nhận chất lượng hoặc khả dụng của bản đồ nền. Bóng đổ, nhiệt, giao thông, nhu cầu hạ tầng và AI chưa triển khai nên chưa được nghiệm thu.

## Ví dụ tính toán

Đây là **dữ liệu giả định để kiểm tra phần mềm**, không phải công trình thật hoặc mô phỏng ngập đã hiệu chỉnh.

- Khu đất giả định tại Thủ Đức: **12.095,93 m²**.
- Mưa đồng đều của trận giả định: **60 mm**.
- Hệ số giả định dùng chung: mái 0,90; sân cứng 0,85; sân thấm 0,35; đất xanh 0,20.

| Phương án | Mái / sân cứng / sân thấm / đất xanh | Dung tích giữ nước trống | Nước còn lại sau giữ nước giả định |
|---|---|---:|---:|
| Hiện trạng | 0% / 10% / 20% / 70% | 0 m³ | **214,10 m³** |
| Thiết kế ban đầu | 30% / 50% / 10% / 10% | 0 m³ | **544,32 m³** |
| Thiết kế cải thiện | 30% / 20% / 20% / 30% | 80 m³ | **333,68 m³** |

Trong ví dụ này, cải thiện giảm khoảng **210,64 m³** so với thiết kế ban đầu; vẫn cao hơn hiện trạng. Kết quả cho thấy đánh đổi trong các giả định đã nhập, không kết luận mức ngập thực tế của khu vực.

## Bằng chứng và chạy lại

Các tệp local bị gitignore:

- `test-results/khoi-local.xml`, `khoi-linux.xml`: kết quả từng test.
- `test-results/khoi-local-report.json`: build, pipeline và smoke test API.
- `test-results/building-ui-report.json`: các nhóm test trình duyệt.
- `test-results/building-ui-desktop.png`, `building-ui-mobile.png`: ảnh giao diện.
- `test-results/building-ui-export.json`: JSON xuất từ giao diện.

Lệnh tái hiện:

```powershell
$env:POSTGRES_PASSWORD = ((Get-Content .runtime/khoi-local.env -Raw).Trim() -split '=', 2)[1]
& .venv/Scripts/python.exe scripts/test-khoi-local.py --linux-checks
npm install --prefix .runtime/ui-check --no-package-lock --no-save playwright-core
node scripts/test-building-ui.cjs
```

Docker Desktop đã được bật và stack local vẫn chạy tại `http://127.0.0.1:8001/simulation`. Lần kiểm tra này thực hiện trên máy local; các thay đổi mới chưa commit/push, chưa chạy GitHub Actions và chưa deploy máy 156.
