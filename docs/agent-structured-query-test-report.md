# Báo cáo kiểm thử truy vấn dataset của agent

Đây là báo cáo giai đoạn đầu. Bản hiện tại đã có
[PostGIS pushdown, Goong routing và phạm vi thống nhất](agent-query-routing-upgrade.md);
các giới hạn lấy mẫu warehouse trong báo cáo lịch sử dưới đây không còn áp dụng
cho adapter warehouse native hiện tại.

Ngày: 16/10/2026. Branch: `feat/development-simulation-context`.
Preview: server 156 cổng 51875, tunnel local **http://127.0.0.1:8192/**.

## Kết quả

| Hạng mục | Kết quả |
|---|---|
| Unit test mới trên Windows | **22/22 đạt** |
| Toàn bộ test general agent + Development agent + structured query trên Linux | **63/63 đạt** |
| Frontend TypeScript/Vite build | Đạt |
| API nguồn thật: giá, parcel–giá, refine và export report | Đạt |
| Model thật: truy vấn EN, refine VI, truy vấn mới bỏ giới hạn diện tích | **3/3 đạt** |
| Browser: bảng, cờ giá, hình học, lịch sử, export, panel mobile, không lỗi JavaScript | **7/7 đạt** |
| Ma trận structured query cho 10 dataset web và POI | **11/11 HTTP 200** |

Linux chạy trong container kiểm thử dùng image preview, mount source read-only,
không sửa container ứng dụng hoặc database. Có một cảnh báo deprecation của
FastAPI TestClient/httpx; không có test lỗi. Bộ test tổng hợp chưa chạy được trực
tiếp trên Windows vì module giao thông hiện có import `fcntl` chỉ có trên Unix;
22 test mới chạy được trên Windows, toàn bộ 63 test chạy trên Linux.

## Case thật đã kiểm tra

Trong viewport mẫu Thủ Đức, nguồn trả 48 parcel:

1. Parcel diện tích 40–1.000 m², gần đường có giá tham chiếu đất ở 20–40 triệu
   VND/m² trong 300 m: **0 khớp**.
2. Hỏi tiếp bằng tiếng Việt, diện tích 80–500 m², giữ điều kiện trước: **0 khớp**.
3. Tạo truy vấn mới bỏ giới hạn diện tích, giữ giá và khoảng cách: **4 khớp**,
   hiển thị 3 thửa diện tích nhỏ nhất.

| Parcel | Diện tích tính từ hình học | Khoảng cách tới đường giá phù hợp | Giá tham chiếu đường |
|---|---:|---:|---:|
| 1937204 | 2.569,71 m² | 227,9 m | 32.900.000 VND/m² |
| 1937203 | 37.604,77 m² | 153,4 m | 32.900.000 VND/m² |
| 1937205 | 64.763,81 m² | 9,7 m | 32.900.000 VND/m² |

Đường tham chiếu là Đường Số 1, hiệu lực ghi nhận 2026-01-01. Cả
`geometry_reviewed` và `source_values_reviewed` đều false. Đây là dữ liệu nguồn
chưa kiểm duyệt việc gán giá; không phải xác nhận giá thị trường, giá áp dụng
pháp lý, đất trống hoặc khả năng xây nhà. Các parcel trên có diện tích lớn;
không coi chúng là các lô nhà ở phù hợp chỉ vì đạt điều kiện nối giá.

Model tự phục hồi sau lỗi tên layer/trường không tồn tại bằng cách đọc catalog
và describe lại. Điều này không làm truy vấn lỗi được thực thi. Kết quả cuối đã
được script kiểm tra số khớp, required joins và số dòng hiển thị, không chỉ kiểm
tra HTTP thành công.

## Ma trận adapter

| Dataset | Bản ghi khớp phạm vi trong fetch |
|---|---:|
| population | 1 bản ghi tổng dân số của vùng |
| flood_risk | 0 |
| flood_history | 0 |
| flood_satellite | 0 |
| land_price | 38 |
| parcels | 48 |
| synthetic_buildings | 18 |
| traffic | 181 |
| sumo_network | 181 |
| sumo_simulation | 0 |
| poi | 0 |

Đây là kết quả trong viewport thử, không phải thống kê toàn thành phố.
HTTP 200 với 0 bản ghi xác nhận adapter đọc được nguồn/trạng thái; không xác
nhận có coverage tại vị trí đó. SUMO query không chạy solver mới; trạng thái
chưa có cache cho kỳ yêu cầu được giữ trong sources. POI của test API không có
snapshot tile từ browser và nguồn bổ sung không có bản ghi trong viewport đó.
18 công trình `synthetic_buildings` là dữ liệu giả lập có nhãn.

## Lỗi phát hiện và đã sửa

- Describe gặp trường `id`/`area_m2` có sẵn: giữ trường dẫn xuất chuẩn, không để
  thuộc tính nguồn ghi đè.
- Model quên điều kiện loại bản ghi không nối được giá: đổi join mặc định thành
  `required:true`, thêm test required/optional join. Số khớp và aggregates chỉ
  tính những dòng đạt mọi join bắt buộc.
- Refine phải giữ bộ lọc cũ, đọc lại cả fetch, kiểm tra đúng session và địa lý;
  model phải có yêu cầu tiếp tục rõ ràng.
- Khoảng cách bằng 0 cho dữ liệu điểm phải giữ được giao chính xác.
- Không giữ overlay structured query cũ khi chuyển sang một tìm kiếm candidate
  hoặc amenity mới thành công.

## Evidence và chạy lại

Trong `test-results/general-agent/` (artifact local, không commit dữ liệu test):

- `structured-query-result.json`: tool/source thật, ba prompt nguyên văn,
  phản hồi model và trace.
- `structured-query-matrix.json`: nguồn/trạng thái 11 adapter.
- `structured-browser-result.json`: 7 kiểm tra giao diện.
- `structured-query-desktop.png`, `structured-query-mobile.png`: ảnh đã xem.
- `structured-query-export.md`: báo cáo tải trực tiếp từ web.

Scripts:

- `scripts/check-agent-structured-query.py` (có gọi model và phát sinh chi phí).
- `scripts/check-agent-query-matrix.py` (chỉ API dữ liệu, không model).
- `scripts/check-agent-structured-browser.cjs` (khôi phục session đã kiểm thử).

## Giới hạn

Đây là kiểm thử kỹ thuật và logic trên vùng mẫu, không phải kiểm định chất lượng
mọi dữ liệu trong thành phố. Giới hạn 2.000 bản ghi/nguồn và 650 km² vẫn áp dụng;
filter chạy trên fetch giới hạn, chưa push-down thành truy vấn toàn warehouse.
Giới hạn được công bố trong kết quả. Chưa thêm Goong routing/geocoding vào agent,
chưa tạo dữ liệu capacity, và chưa deploy thay đổi lên web chính 51873.
