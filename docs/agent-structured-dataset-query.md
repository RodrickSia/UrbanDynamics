# Truy vấn dataset bằng AI agent

## Phạm vi

Bản preview riêng trên server 156: cổng 51875, qua tunnel local 8192. Branch `feat/development-simulation-context`. Không cần mở Development plan. Không triển khai thay đổi này lên web chính cổng 51873.

Ba tool truy vấn dưới đây nằm trong tổng cộng **34 tool hiện tại**. Xem thêm
[bản nâng cấp PostGIS, Goong routes và phạm vi](agent-query-routing-upgrade.md).

| Tool | Chức năng |
|---|---|
| `dataset_describe` | Đọc các trường, kiểu, ví dụ và metadata thực sự quan sát được của một dataset trong vùng đã chọn |
| `dataset_query` | Lọc thuộc tính/không gian, nối nguồn, sắp xếp và tổng hợp |
| `dataset_query_refine` | Thêm điều kiện vào một trong 5 truy vấn gần nhất của cùng session và cùng khu vực |

Model chuyển ngôn ngữ tự nhiên thành JSON; backend kiểm tra cấu trúc và chạy adapter nguồn hiện có. Không có SQL, HTTP hoặc shell tùy ý do model cung cấp.

## Người dùng có thể hỏi gì?

- “Trong vùng bản đồ đang xem, tìm các đoạn đường có giá đất ở tham chiếu 20–40 triệu đồng/m², sắp xếp tăng dần.”
- “Tìm parcel 80–150 m² trong khu vực này, cách một đường có giá đất tham chiếu trong khoảng ấy dưới 300 m.”
- “Tiếp tục lọc các kết quả đó theo loại sử dụng đất này…”
- “Đếm số bản ghi khớp, tính giá trung bình và nhóm theo tên đường.”
- “Chỉ lấy các thửa giao với lớp dữ liệu ngập đã ghi nhận.”
- “Tìm parcel gần bệnh viện và công viên bằng hai phép nối POI riêng.”

Phải xác định địa lý trước: nêu tên địa danh/đường, chọn parcel hoặc nói rõ dùng vùng bản đồ đang xem. Tìm địa danh hiện dùng Nominatim/OSM; nếu provider không truy cập được, người dùng chọn phạm vi trên bản đồ. Tên quận được geocode thành bbox có nhãn, chưa phải ranh giới hành chính pháp lý chính xác.

## Dataset hỗ trợ

Mọi layer được đăng ký trong `repository.LAYER_INFO`, cộng năm adapter `population`, `traffic`, `sumo_network`, `sumo_simulation`, `poi`. Bao gồm parcel, giá đất, ngập lịch sử/rủi ro/vệ tinh, công trình giả lập và các snapshot bổ sung đã cài. Dataset chưa được cài sẽ báo thiếu, không tự tạo dữ liệu thay thế.

Schema được khám phá từ bản ghi trong vùng; không suy diễn một trường nếu nguồn rỗng. Sử dụng đơn vị nguồn. Không tự ép chuỗi `20,000` thành số hay biến ngân sách mua đất thành giá thị trường.

Population trả tổng mô hình hóa của vùng theo năm, không phải từng ô dân số hay mật độ từng parcel; không cho nối tổng vùng lên từng thửa. SUMO chỉ đọc run/cache có sẵn, truy vấn không tự chạy solver. POI bản đồ có phạm vi tile đã tải, OSM bổ sung cũng có phạm vi riêng; không coi là danh sách đầy đủ toàn thành phố.

## Bộ lọc và phép kết hợp

- Thuộc tính: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between`, `in`, `contains`, `is_known`, `is_unknown`.
- Kết hợp: `all` (AND), `any` (OR), `not`.
- Phạm vi: giao vùng `intersects`, nằm hoàn toàn trong vùng `within`, mở rộng vùng bằng `buffer_m`.
- Nối tối đa 3 nguồn: gần `near`, giao nhau `intersects`, hoặc đối tượng nguồn bao phủ toàn bộ hình học cơ sở `within`.
- Mỗi phép nối mặc định `required: true`: tự loại bản ghi không có đối tượng nguồn phù hợp, dù model quên viết thêm điều kiện `observed_match=true`. Chỉ dùng `required:false` khi chủ động muốn bổ sung dữ liệu nếu có; không coi bản ghi thiếu liên kết là đã đạt yêu cầu.
- Thuộc tính của đối tượng nguồn gần nhất thỏa điều kiện được đặt dưới `alias.<field>`, kèm `alias.distance_m`, `alias.observed_match`, `alias.match_count`.
- Sắp xếp tối đa 3 trường, dữ liệu thiếu luôn ở cuối.
- Tổng hợp: `count`, `sum`, `avg`, `min`, `max`; nhóm tối đa 2 trường. Hiển thị số giá trị số đã biết và số thiếu/không phải số.
- Aggregate và số khớp tính trên toàn bộ mẫu khớp trước `limit`; không cần tăng số dòng hiển thị để đếm.

Giá trị thiếu dùng logic ba trạng thái: đúng/sai/chưa biết. `NOT (giá > X)` không làm bản ghi thiếu giá trở thành đạt yêu cầu. Điều kiện số trên chuỗi trả chưa biết. Có thể dùng `is_unknown` khi chủ động tìm dữ liệu thiếu.

## Ví dụ JSON

Phải gọi describe cho `parcels` và `land_price` trước để kiểm tra trường trong nguồn đang chạy.

```json
{
  "layer": "parcels",
  "joins": [{
    "layer": "land_price",
    "alias": "price",
    "relation": "near",
    "radius_m": 300,
    "where": {"field": "residential_vnd_m2", "op": "between", "value": [20000000, 40000000]}
  }],
  "where": {"all": [
    {"field": "area_m2", "op": "between", "value": [80, 150]},
    {"field": "price.observed_match", "op": "eq", "value": true}
  ]},
  "select": ["area_m2", "price.distance_m", "price.residential_vnd_m2"],
  "order_by": [{"field": "area_m2", "direction": "asc"}],
  "aggregates": [{"op": "count"}],
  "limit": 20
}
```

Ý nghĩa: thửa có một đoạn đường đáp ứng khoảng giá trong bán kính 300 m. Không khẳng định thửa có mặt tiền đường đó, được áp dụng bảng giá đó, có giá bán đó hoặc đang được bán. Các trường nguồn, ngày, đơn vị và cờ kiểm duyệt giá được giữ cả khi model chỉ yêu cầu ít cột.

Điều kiện `where` trong join lọc nguồn trước khi chọn đối tượng gần nhất. Bởi vậy đây là “gần một đường có giá trong khoảng”, khác với “đường gần nhất bất kể giá có giá trong khoảng”.

## Luồng web và hỏi tiếp

- Bảng **Filtered dataset results** hiển thị dữ liệu, số khớp trong fetch, số chưa biết, nguồn và điều kiện truy vấn.
- Tối đa 100 đối tượng trả về được tô trên bản đồ; hỗ trợ điểm, đường, polygon.
- Lưu 5 truy vấn gần nhất trong session; không phải 5 cuộc hội thoại riêng.
- Refine thêm `where` bằng AND, đọc lại toàn bộ nguồn giới hạn, không chỉ lọc 20 dòng vừa hiển thị.
- Nếu đổi địa lý, phải tạo truy vấn mới. Để bỏ/thay điều kiện cũ cũng dùng truy vấn mới.
- Download evidence report đưa bộ lọc, nguồn, dòng kết quả và aggregate vào Markdown.

## Giới hạn cần nói rõ

- Nguồn warehouse native lọc/nối/đếm/sắp xếp tại PostGIS trước LIMIT, không còn cap lấy mẫu 2.000 dòng. POI tile, tổng dân số vùng và adapter SUMO run giữ coverage/giới hạn riêng; adapter hữu hạn vẫn có cờ khi chạm 2.000 dòng.
- Vùng và buffer tối đa 650 km²; bán kính tối đa 5 km. Không hỗ trợ một truy vấn chi tiết toàn TP.HCM mở rộng.
- Tối đa 100 đối tượng và 100 nhóm aggregate hiển thị. SQL read-only có timeout 20 giây; phải thu nhỏ truy vấn nếu vượt budget. Nhánh không có warehouse vẫn dùng adapter mẫu với tối đa 300.000 phép kiểm tra cặp hình học.
- Khoảng cách là khoảng cách ngắn nhất giữa hình học trên phép chiếu mét, không phải hành trình đi đường.
- Không có bản ghi ngập không chứng minh an toàn. Không có footprint không chứng minh đất trống. POI không chứng minh công suất còn dư.
- Trường `area_m2` được tính từ hình học, không phải diện tích sàn.
- Ngày chỉ được lọc với nguồn công bố hỗ trợ thời gian; nguồn khác sẽ báo lỗi thay vì âm thầm bỏ bộ lọc.
- Đã bổ sung [Goong Places V2](goong-preview.md) và [Distance Matrix/Directions V2](agent-query-routing-upgrade.md). Không tự tạo dữ liệu capacity hay thay kết quả SUMO bằng thời gian provider.

## Kiểm thử

[Kết quả thực chạy ngày 16/10/2026](agent-structured-query-test-report.md):
63 test backend, 3 lượt model thật, 7 kiểm tra browser và 11 adapter dữ liệu đạt.

- `backend/tests/test_agent_dataset_query.py`: logic AND/OR/null, khoảng số, nhiều phép nối, nguồn giá, refine toàn bộ fetch, nhóm/sắp xếp, giới hạn và truy vấn sai không làm đổi session.
- `scripts/check-agent-structured-query.py`: API nguồn thật, giá, parcel–giá, refine, report và ba lượt model thật EN→VI. Evidence lưu trong `test-results/general-agent/structured-query-result.json`.
- Kiểm tra browser xác nhận bảng lọc, hình học, lỗi JavaScript và ảnh chụp. Kết quả thực chạy được ghi ở báo cáo kiểm thử.
