# Kết quả nâng nền simulation — local 11/10/2026

Phạm vi: backend simulation dùng dữ liệu chung; frontend do người khác tích hợp.
Code ở workspace branch `feat/khoi-flood-land-price`; chưa commit/push, chưa merge main, chưa deploy.
Server 156 chỉ được đọc qua SSH và API đang chạy, không đổi dịch vụ/database.

## Kết quả kiểm thử

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Toàn bộ backend pytest trên Windows | **111 đạt, 4 bỏ qua**, 23,60 s | `test-results/simulation-background-backend.xml` |
| PostGIS integration local | **Chưa chạy** | 4 test yêu cầu PostGIS bị skip; Docker Desktop daemon không chạy |
| Linux/Docker của thay đổi này | **Chưa chạy** | Không suy kết quả Linux từ Windows |
| Đọc API server 156 | **Đạt** | Snapshot local, sources và hash từng response |
| Tải OSM và cửa sổ ESA WorldCover | **Đạt** | 922 OSM elements, 573 polygon phân loại trong cửa sổ |
| API preflight/predict, SUMO/SWMM native trên dữ liệu pilot | **Đạt** | `test-results/simulation-background-local-report.json`, `background-demo.json` |
| Lưu/mở lại JSON local | **Đạt** | `storage_roundtrip=true`; chưa kiểm tra PostGIS persistence local lượt này |
| Ba phương án cải thiện chạy lại | **Đạt**, cùng context/giờ/quy mô building | `background-recommendations.json`, `context_frozen=true` |
| ZIP solver artifacts | **Đạt**, 2.196.439 bytes | `test-results/background-demo.zip` |
| Thời gian smoke end-to-end | **45,60 s** | Gồm preflight, prediction, rerun 3 ứng viên, mở lại và ZIP; không gồm tải nguồn |

Pytest có một warning từ FastAPI/Starlette về dependency test client. Không có test thất bại ở lượt cuối.

Các test mới kiểm tra: hash snapshot, site ngoài coverage, dữ liệu dân số tương lai, bbox dân số sai,
snapshot được ghim không lấy dân số mới từ warehouse, baseline user override, footprint/surface cân bằng,
thiếu OSM không đồng nghĩa đất trống, registry không nhận trị số là verified, preflight không chạy solver,
chặn URL/path từ client, import native OSM, GeoJSON WGS84, giờ chung và recommendations giữ context.

## Snapshot và nguồn thực sự đã lấy

Snapshot có WorldCover:
`64334deff008126baf2d91c8c57197d9822a76eaf667a6a66edf7414b1e112a8`.
File: `data/simulation_snapshots/<snapshot_id>.json`, gitignored.

AOI bbox `[106.7508553006184, 10.810959502679781, 106.7701446993816, 10.830040491451985]`, bao quanh preset chung cư Thủ Đức.

- **5.318 thửa đất** trong response parcels khu vực; không phải số thửa nằm trong site.
- **35.247,63 người**, WorldPop **2026**, tổng raster pixels bbox. Không phải số đếm thực hay cư dân của chung cư.
- **5 đối tượng cơ sở giáo dục OSM** trong buffer dùng cho simulation; chưa xác minh capacity hay tính duy nhất thực địa.
- **3 feature flood history**, **3 flood risk**, **30 giá đất** trong bbox; dùng làm context, không tự hiệu chỉnh SWMM.
- OSM **922 elements** gồm đường, building tags, land-use, POI và signal nodes.
- ESA WorldCover **2021 v200**, độ phân giải 10 m; **573 polygon** trong cửa sổ. Polygon không tương đương số công trình hoặc thửa.

Lượt tải đầu tiên đã chọn 2030 vì đó là năm lớn nhất catalog. Đã sửa selector để chỉ chọn năm không vượt năm hiện tại, tải lại 2026; snapshot 2030 không dùng trong case cuối. Backend cũng bỏ dân số tương lai khỏi nền hiện tại.

## Case native: thêm chung cư

Run ID `b58046ec-2578-443d-9317-f5ae17bcbf2c`.
Mạng SUMO import: **585 nút, 1.240 cạnh có hướng**, 8 hướng nguồn và 8 hướng đích đại diện.
Đây là mạng sau filter xe cơ giới/bbox và có connector cổng giả định, không phải mạng đầy đủ của thành phố.

| Chỉ số | Baseline kịch bản | Sau xây chung cư |
|---|---:|---:|
| Giờ so sánh | 18h | 18h |
| Xe kế hoạch | 2.077 | 2.159 |
| Xe hoàn thành | 2.077 | 2.159 |
| Xe chưa hoàn thành / chưa xuất phát | 0 / 0 | 0 / 0 |
| Chậm trễ trung bình chuyến hoàn thành | 33,18 s | 33,38 s |
| Hàng chờ tối đa | 16,54 m | 17,63 m |

Các số là **output mô phỏng trên nền hỗn hợp**, không phải dự báo đã xác thực ngoài đường.
Luồng nền 2.077 xe/h được ước lượng từ dân số bbox × trip rate × profile × mode/occupancy × participation × stress factor.
Chưa có counts camera, OD survey hoặc lịch đèn khảo sát. Không dùng mức chênh ~0,20 s làm bằng chứng chính xác về tác động thực địa.

Baseline tại khu đất có **0 footprint OSM được mapping**. Không kết luận đất trống.
WorldCover ghi khoảng **11.423,93 m² built-up** làm paved proxy sau trừ footprint biết, khoảng **672,00 m²** chưa phân loại.
Chiều cao/công năng/occupancy hiện hữu chưa đủ. Baseline vì vậy chưa phải hồ sơ hiện trạng thực; frontend phải hiển thị cảnh báo.

Ba ứng viên chạy lại giữ building và context; case có ứng viên `targets_met` với **mục tiêu và năng lực giả định của dự án**.
SWMM continuity/count xe kiểm tra đạt không chứng minh mạng cống thật, nhiệt độ, áp lực nước hay quá tải lưới.

## Phần còn giả định

- OD, profile trips, modal shares/occupancy, tỷ lệ tham gia vùng, hành vi xe, pha đèn và connector cổng.
- Bề mặt chưa phân loại, built-up→paved proxy, tầng/height nếu thiếu tag và occupancy hiện hữu.
- Nhu cầu dịch vụ, capacity dịch vụ; combined schooling/health chỉ là screening, chưa đánh giá đủ theo loại/nhóm tuổi.
- Suất điện/nước/nước thải, lịch, hiệu quả tiết kiệm; cống/cao độ/đất/biên SWMM.
- Công suất dư điện/nước/nước thải, đơn giá và mục tiêu.

Registry đã chuẩn hóa nhãn và reference phương pháp; **chưa thay toàn bộ numeric defaults bằng hệ số địa phương được duyệt**.
Camera counting, scheduler snapshot citywide, job API persistent và frontend map integration chưa triển khai ở lượt này.

## Tái hiện

```powershell
$env:PYTHONPATH = 'backend;etl'
& .venv/Scripts/python.exe -m pytest backend/tests -q
& .venv/Scripts/python.exe scripts/test-simulation-background-local.py --snapshot-id 64334deff008126baf2d91c8c57197d9822a76eaf667a6a66edf7414b1e112a8
```

Tham khảo payload, môi trường, API và giới hạn trong [bàn giao backend](simulation-background-integration.md).
