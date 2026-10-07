# So sánh tác động công trình — phiên bản ưu tiên

> Tài liệu này mô tả luồng so sánh thủ công phiên bản 1. Giao diện hiện dùng [luồng dự tính → đánh giá → tạo gợi ý phiên bản 2](building-impact-prediction.md). API cũ được giữ để tương thích bản ghi đã lưu; người dùng không còn nhập sẵn phương án cải thiện.

## Phần đã triển khai

- Trang demo tiếng Việt tại `/simulation`, chạy cùng FastAPI. Trang frontend chính hiện vẫn là scaffold; module này có thể được tích hợp qua API sau.
- Vẽ khu đất và footprint tùy chọn cho thiết kế ban đầu / cải thiện. Có thể nhập GeoJSON nếu thư viện bản đồ không tải.
- Nhập đúng ba phương án: hiện trạng, thiết kế ban đầu, thiết kế cải thiện. Cùng một khu đất, trận mưa và bộ hệ số.
- Tính thay đổi diện tích xanh, mái + sân cứng, diện tích sàn ước tính và thể tích nước chảy tràn trước/sau giữ nước.
- Kiểm tra tổng diện tích, geometry, vị trí footprint và sự khớp giữa footprint với diện tích mái.
- Lưu từng lần chạy riêng, mở lại qua UUID; giữ đầu vào, SHA256, thời gian UTC, phiên bản mô hình, phương pháp và giới hạn.
- Xuất JSON; in / lưu PDF bằng trình duyệt.

Ví dụ nạp sẵn là **hình học, thiết kế và hệ số giả định**, chưa khảo sát hay xác nhận quyền xây dựng. Có thể chọn trường học, nhà ở, văn phòng, bệnh viện hoặc loại khác. Công năng/số người được lưu làm context; chưa dùng để suy ra lưu lượng xe hoặc nhu cầu hạ tầng.

## Chạy local

Dùng stack Khôi đã setup:

```powershell
$env:POSTGRES_PASSWORD = ((Get-Content .runtime/khoi-local.env -Raw).Trim() -split '=', 2)[1]
& .venv/Scripts/python.exe scripts/test-khoi-local.py
```

Mở `http://127.0.0.1:8001/simulation`, bấm **Nạp ví dụ giả định**, kiểm tra đầu vào, đánh dấu xác nhận rồi bấm **Tính và lưu so sánh**. Link kết quả có dạng `/simulation?run=<uuid>`. Khi sửa đầu vào, giao diện ẩn kết quả cũ cho đến khi tính lại.

Khi mở link kết quả, hệ thống nạp lại đầu vào để có thể sửa và tính thành lần chạy mới; bản ghi cũ được giữ nguyên.

Kiểm tra trình duyệt tùy chọn, cần Edge đã cài trên Windows:

```powershell
npm install --prefix .runtime/ui-check --no-package-lock --no-save playwright-core
node scripts/test-building-ui.cjs
```

Script tạo thêm các scenario giả định trong stack local, chặn tải tile bản đồ nền khi test để không phụ thuộc tile server; vẫn kiểm tra thao tác vẽ polygon bằng Leaflet. `BUILDING_API_URL` và `BUILDING_BROWSER_CHANNEL` cho phép đổi địa chỉ local hoặc trình duyệt đã cài. Report, ảnh và JSON xuất nằm trong `test-results/`, bị gitignore. Xem [báo cáo kiểm thử](building-simulation-test-report.md).

Tệp `.runtime/khoi-local.env` là tệp riêng trên máy, bị gitignore; không commit hoặc chia sẻ. Người dùng mới tạo `POSTGRES_PASSWORD` riêng theo hướng dẫn stack Khôi.

Leaflet 1.9.4 tải qua CDN có integrity hash; bản đồ nền dùng OpenStreetMap có attribution. Cần Internet cho bản đồ, nhưng nhập GeoJSON / nạp ví dụ và tính toán vẫn hoạt động nếu thư viện CDN không tải. [Nguồn Leaflet](https://leafletjs.com/download.html).

## Phương pháp và ý nghĩa

`model_version = building-screening-1.0.0`.

Diện tích được tính trên ellipsoid WGS84 bằng `pyproj.Geod`; polygon có lỗ được trừ đúng diện tích. [Tài liệu pyproj](https://pyproj4.github.io/pyproj/stable/api/geod.html).

Mỗi phương án có bốn loại bề mặt **không chồng lấn**:

| Trường | Ý nghĩa |
|---|---|
| `roof_m2` | Diện tích chiếu bằng mái / footprint công trình |
| `paved_m2` | Sân cứng không thấm |
| `permeable_m2` | Sân thấm; tách khỏi đất xanh |
| `green_m2` | Đất xanh ở mặt đất, không phải diện tích tán cây chồng lên mái/sân |
| `available_storage_m3` | Dung tích trống có thể tiếp nhận nước đầu trận mưa |
| `floors`, `users` | Số tầng, số người do người dùng nhập |
| `footprint` | Polygon WGS84 tùy chọn; nếu có phải nằm trong khu đất và khớp `roof_m2` |

Tổng bốn loại diện tích phải khớp diện tích khu đất với sai số tối đa `max(0.1 m², 0.01% diện tích)`. Không tự chuẩn hóa dữ liệu sai. Giới hạn khu đất: 1–1.000.000 m²; tối đa 500 đỉnh và 20 vòng polygon, phạm vi mỗi trục không quá 0,1 độ.

```text
Nước chảy tràn sơ bộ (m³) = mưa (mm) / 1000 × Σ(diện tích (m²) × hệ số)
Nước giữ lại giả định = min(nước chảy tràn, dung tích trống)
Nước còn lại = nước chảy tràn − nước giữ lại
Diện tích sàn ước tính = diện tích mái × số tầng
```

Hệ số từ 0 đến 1 là đầu vào bắt buộc; API không gán hệ số mặc định. Người dùng phải nêu `coefficient_basis` và `design_basis`. Hệ số trong ví dụ chỉ để thử phần mềm, không được trình bày là hệ số thực địa của Thủ Đức.

Phép trừ dung tích chưa kiểm tra đường dẫn nước, khả năng tiếp nhận theo thời gian hoặc xả nước. `unretained_runoff_m3` là thể tích ước tính còn lại sau phép giữ nước giả định; **không phải thể tích ngập**. Chưa tính thấm động, mạng cống, địa hình, triều hoặc trao đổi nước với khu lân cận.

Mức giảm phần trăm trả `null` khi giá trị mốc bằng 0. So sánh gồm hiện trạng→thiết kế, hiện trạng→cải thiện và thiết kế→cải thiện. Thiết kế cải thiện vẫn có thể làm chỉ số xấu hơn; hệ thống không ép kết quả theo tên phương án.

## API

| Endpoint | Kết quả |
|---|---|
| `POST /api/v1/scenarios/site-area` | Nhận GeoJSON Polygon, trả diện tích m² |
| `POST /api/v1/scenarios/building` | Tính và lưu trọn bộ ba phương án, HTTP 201 |
| `GET /api/v1/scenarios/building/{uuid}` | Mở lại nguyên kết quả đã lưu |

Swagger ở `/docs` chứa schema đầy đủ. `scripts/building_demo.py::sample_payload()` tạo payload ví dụ phù hợp diện tích đo được.

POST nhận `title`, `building_use`, `site`, `rainfall_mm`, `coefficients`, `coefficient_basis`, `design_basis`, `baseline`, `development`, `mitigated`. Trả `variants`, `comparisons`, GeoJSON `map`, `method`, `limitations`, `unavailable_modules`, `id`, `created_at`, `input_sha256` và `model_version`.

Đầu vào sai trả 422; UUID không tồn tại trả 404; lỗi lưu trữ trả 503 và không báo thành công. Khi có `DATABASE_URL`, lưu vào bảng PostGIS `building_scenario_runs`, geometry SRID 4326 và JSONB đầy đủ. DDL trong `backend/app/services/simulation/schema.sql` được áp dụng bằng transaction khi tạo lần chạy đầu tiên, giống cơ chế bootstrap lớp dữ liệu hiện có. Schema mới không cập nhật hoặc xóa các lớp ngập/giá đất.

Nếu không cấu hình database, lưu JSON bằng rename nguyên tử tại `SCENARIO_DATA_DIR` hoặc `DATA_DIR/scenarios`. File fallback phục vụ local/testing; không fallback khi database đã cấu hình nhưng bị lỗi. Stack Docker local lưu PostGIS trên volume `khoi_database` hiện hữu.

Module nhẹ này tính đồng bộ trong request. Chưa có worker/jobs; bổ sung hàng đợi bền vững khi tích hợp các engine vật lý chạy lâu. Chưa tích hợp chatbot AI; kết quả cấu trúc đã có nguồn giả định và giới hạn để adapter AI sử dụng sau.

## Các module tiếp theo

1. Bóng đổ với chiều cao thật và tiếp cận dịch vụ trên mạng đường có dữ liệu bao phủ.
2. Nhu cầu chuyến đi, điện/nước dựa trên các hệ số có nguồn và công suất hạ tầng thực tế.
3. SWMM và mô hình thủy động lực bề mặt cho một lưu vực nhỏ có địa hình, mạng cống, mưa/triều và sự kiện kiểm chứng.
4. SOLWEIG / SUMO sau khi chuẩn bị dữ liệu và hiệu chỉnh thích hợp.

API `/api/v1/scenarios/rain` được giữ nguyên chức năng cảnh báo theo mưa và lịch sử ngập. Module mới chưa xuất bản bản đồ độ sâu ngập và chưa xác định ảnh hưởng ngập đến hàng xóm.
