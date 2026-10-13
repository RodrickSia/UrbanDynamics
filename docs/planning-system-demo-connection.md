# Simulation nối parcel và dữ liệu nền — chỉ demo kiểm thử

> Phần dưới là báo cáo lịch sử model 0.15. Demo mới 0.18 đã nối mạng OSM, WorldCover 2021, prior vehicle-mix từ counting, đường đi bộ OSM và 23 footprint hàng xóm. Xem [tiến độ và link mới](planning-remaining-groups-implementation.md). Occupancy/công suất/tuyển sinh chưa xác minh; counting chưa có crossing labels đầy đủ.

Cập nhật: 12/10/2026. Model: `planning-studies-0.15`.

## Phạm vi triển khai

Demo local tại <http://127.0.0.1:8007/simulation/planning> lấy snapshot qua API backend của nhóm trên server **156**, bằng SSH và đọc trong container `urbandynamics-backend-1`. Không ghi dữ liệu vào server, không thay frontend chính, không deploy production và không push GitHub trong lần này.

Luồng: chọn parcel thật → khai báo building plan → lấy nền từ snapshot → preflight → tạo job screening hoặc SUMO/SWMM → lưu kết quả, nguồn đầu vào và xuất GeoJSON/ZIP. Snapshot có SHA-256; worker kiểm tra nội dung và geometry parcel trước khi tính. Không gọi nguồn ngoài trong quá trình chạy simulation.

## Dữ liệu đã nối

Snapshot `199d0e6997ec9fd5ebaca06b02285d780a531788523d497093135137a46afa28`, thu thập lúc `2026-10-12T03:01:15.827986+00:00` — thời điểm thu thập không phải ngày quan trắc của từng nguồn.

| Dữ liệu | Snapshot hiện tại | Được dùng như thế nào |
|---|---|---|
| Parcel hệ thống | 2.730 feature; 200 parcel phù hợp demo | Ranh và diện tích thật của khu đất; giữ nguyên toàn bộ geometry. Chỉ chuẩn hóa MultiPolygon một phần thành Polygon tương đương |
| WorldPop | Khoảng 20.226 người trong bbox | Ước tính dân số vùng; có thể bao gồm cư dân trên parcel được chọn, chưa khử trùng chính xác |
| OSM | 570 element | Lấy footprint giao parcel để chuẩn bị hiện trạng; lấy vị trí trường. Đường OSM được lưu trong context nhưng **chưa đưa vào graph SUMO** |
| Lịch sử ngập | 1 feature | Lớp bối cảnh trong frozen context; không phải tham số hiệu chỉnh SWMM |
| Rủi ro ngập | 3 feature | Lớp bối cảnh; không suy ra độ sâu ngập của công trình từ lớp này |
| Giá đất | 0 feature trả về trong snapshot | Chưa có dữ liệu giá đất dùng được cho khu demo này |
| WorldCover | Không fetch trong lần này | Bề mặt chưa có khảo sát được ghi là giả định |

**Không coi footprint OSM bằng 0 là đất trống.** Occupancy hiện trạng được đặt `unknown`. Dân số WorldPop là prior tổng vùng, không phải số cư dân parcel hoặc census. So sánh liên quan hiện trạng thiếu dữ liệu trả `insufficient_data`, không tự thay thành mức tăng đã xác minh.

## Phần còn giả lập hoặc chưa biết

| Thành phần | Trạng thái |
|---|---|
| Hình khối công trình đề xuất | Plan giả định ban đầu theo số căn/cư dân/tầng; người dùng chỉnh đầy đủ trong JSON. Không phải thiết kế tối ưu tự đề xuất |
| Diện tích xanh/lát chưa có bản đồ | Giả định demo, bổ sung quanh footprint |
| Mạng SUMO, đèn và tuyến xe | Corridor/access được tạo bằng thuật toán; chưa khớp mạng đường OSM thực |
| Lưu lượng xe nền | Chưa quan trắc; giá trị số 0 trong đầu vào là placeholder, không chứng minh đường không có xe |
| Graph SWMM, cống, cửa xả, đất | Mô hình tổng hợp; chưa có khảo sát cống, triều và DEM cho ngập 2D |
| Công suất và tải nền điện/nước/nước thải | Chưa xác minh; capacity giữ `null`, source `unknown` |
| Sức chứa và nhu cầu trường học nền | Vị trí có thể lấy OSM; capacity/enrollment chưa biết |
| Tuyến đi bộ, inventory công trình hàng xóm | Chưa khảo sát đầy đủ; graph đi bộ tổng hợp |

Kết quả native là kết quả mô phỏng thật bằng SUMO/SWMM **trên mô hình giả định**, không phải dự báo đã hiệu chỉnh cho giao thông/ngập tại địa điểm.

## Cách test trên giao diện

1. Mở demo local và tìm khối **parcel hệ thống**; bấm **Nạp parcel thật**.
2. Bấm một polygon hoặc chọn từ danh sách; có thể chọn tối đa 6 parcel.
3. Nhập số căn, cư dân và số tầng; bấm **Dùng parcel và nền này**.
4. Xem/chỉnh building plan trong JSON. Bấm kiểm tra đầu vào, sau đó chạy Screening hoặc SUMO + SWMM.
5. Xem nguồn, các giá trị `Chưa biết`, mở lại job và tải artifacts để đối chiếu.

Case đã kiểm tra: parcel **1919282**, diện tích khoảng **1.734,71 m²**, 20 căn, 60 cư dân, 8 tầng. Native HTTP test sử dụng giờ 18h và ba seed 2026/2027/2028. Đó là chương trình xây dựng giả định trên ranh thật.

## API dành cho frontend demo

Adapter tại `backend/app/routers/planning_system_demo.py`:

- `GET /api/v1/planning/demo/system/snapshots`
- `GET /api/v1/planning/demo/system/snapshots/{id}/parcels`
- `POST /api/v1/planning/demo/system/prepare`

Ví dụ body:

```json
{
  "snapshot_id": "199d0e6997ec9fd5ebaca06b02285d780a531788523d497093135137a46afa28",
  "parcel_ids": ["1919282"],
  "housing_units": 20,
  "residents": 60,
  "floors": 8
}
```

Response có `demo_only: true` và `study`, chuyển tiếp study vào API planning hiện có. Frontend có thể gửi `developments` dạng `{ "1919282": <Design đầy đủ> }` thay plan ban đầu. Kết quả giữ `system_snapshot_id`, `system_parcel_bindings`, `context.system_background` và manifest nguồn. Đây là adapter cho demo; chưa là endpoint triển khai production.

## Gate và lưu trữ

Chỉ bật khi **API và worker cùng có**:

```text
PLANNING_SYSTEM_DEMO_ENABLED=1
PLANNING_SYSTEM_SNAPSHOT_DIR=/system-snapshots
```

Mount thư mục `.runtime/planning-system/snapshots` vào `/system-snapshots` dạng read-only. Gate tắt: endpoint adapter trả 404; gửi study `demo_system` qua endpoint planning thường cũng bị từ chối. File snapshot bất biến phải được giữ để mở lại/retry revision. Study/job/result lưu trong volume SQLite `planning-program-runtime`; dữ liệu nguồn nằm ở thư mục snapshot local, không chứa credentials.

Tạo lại snapshot đọc từ server:

```powershell
.venv/Scripts/python.exe scripts/prepare-simulation-background.py `
  --ssh-host 192.168.20.156 --backend-container urbandynamics-backend-1 `
  --base-url http://127.0.0.1:8000 --radius-m 750 `
  --output-dir .runtime/planning-system/snapshots --without-landcover
```

## Bằng chứng kiểm thử

- Hồi quy planning/integrated: **114/114 đạt**, 164,26 giây (`test-results/planning-system-demo-regression.xml`).
- Sau điều chỉnh provenance: **15/15 đạt**, 29,38 giây (`test-results/planning-system-demo-final-focused.xml`).
- Native HTTP: script `scripts/test-planning-system-demo-local.py`; báo cáo `test-results/planning-system-demo/http-report.json`, kết quả JSON và ZIP cùng thư mục.
- Giao diện: script `scripts/test-planning-system-demo-ui.cjs`; báo cáo và ảnh desktop/mobile cùng thư mục. Báo cáo chỉ được ghi khi toàn bộ kiểm tra thành công.

Bản Docker cuối đã kiểm tra thành công native HTTP/ZIP/GeoJSON và **4/4 nhóm kiểm tra giao diện**, gồm chọn polygon, chuẩn bị plan/preflight, screening/mở lại native, desktop/mobile không lỗi JavaScript. Job native: `55e7bb71-5e5d-4704-a0fb-fd31a3bc821d`; run: `08609252-6e30-44e2-814c-9cd83002fbf3`. Image manifest: `77530f3b4ae2ca87d6750b6fd7f2b9e7245b8e108f625325ed178d0d90c68827`.

Các báo cáo model 0.14 trước đây là lịch sử; bằng chứng kết nối snapshot này dùng model 0.15. Bước tiếp theo để tăng tính sát thực là nhập mạng đường OSM vào SUMO, hiệu chỉnh luồng xe và bổ sung occupancy/công suất hạ tầng có nguồn; không suy ra chúng chỉ từ parcel.
