# Agent: PostGIS, Goong routes và phạm vi phân tích

Ngày triển khai: 16/10/2026. Branch `feat/development-simulation-context`.
Preview riêng: **http://127.0.0.1:8192/** → server 156 cổng 51875.
Web chính 51873 không được thay thế. Chưa commit/push các thay đổi.

## 1. Lọc và kết hợp dataset tại PostGIS

`dataset_query` và `dataset_query_refine` sử dụng compiler SQL tham số hóa khi
warehouse có cấu hình. Model chỉ cung cấp biểu thức JSON đã kiểm tra, không có
quyền chạy SQL hoặc HTTP tùy ý.

Các adapter warehouse native gồm các layer vector được đăng ký (parcel, công
trình giả lập, giá đất, ngập, mưa, ranh giới…) và `sumo_network`, `traffic`:

- Lọc địa lý/thuộc tính, phép nối, sắp xếp, đếm và tổng hợp chạy **trước LIMIT**.
- Không còn lấy 2.000 dòng đầu của bảng warehouse rồi mới lọc.
- Giữ `required:true` cho phép nối bắt buộc; thửa không có nguồn phù hợp bị loại.
- Join lọc nguồn trước, lấy đối tượng gần nhất thỏa điều kiện; khoảng cách này
  là địa lý hình học, không phải quãng đường đi xe.
- Số đếm bao phủ bản ghi **đã nhập trong hình học truy vấn**, không chứng minh
  bao phủ đầy đủ thực địa. Thuộc tính giá đường không trở thành giá của thửa.
- Kết quả có `query_engine=postgis`, `matched_count`, `count_scope`, số dòng đã
  hiển thị, nguồn và bản tóm tắt điều kiện. Trường cũ
  `matched_in_bounded_fetch` được giữ để tương thích, cùng giá trị số đếm.
- Bản ghi thiếu/không phải số không được chuyển thành 0. NOT trên điều kiện
  chưa biết vẫn là chưa biết. Nhóm/average công bố số giá trị đã biết.

Population là tổng mô hình hóa của vùng; POI tile là snapshot hữu hạn; SUMO run
đã lưu là adapter dữ liệu kết quả. Chúng vẫn giữ phạm vi và giới hạn riêng khi
được đưa vào SQL như dữ liệu giá trị. Không tuyên bố các adapter đó trở thành
một kho dữ liệu toàn thành phố đầy đủ. Không cho nối tổng dân số vùng vào từng
thửa để giả làm dân số từng thửa.

Giới hạn tài nguyên: tối đa 3 joins, 100 dòng hiển thị, 100 nhóm tổng hợp hiển
thị, vùng và buffer không quá 650 km², timeout mỗi câu SQL 20 giây. Timeout báo
lỗi rõ; không tự thay bằng mẫu rồi trả số đếm không đầy đủ. SQL ở transaction
read-only/repeatable-read, không sửa dữ liệu warehouse hay tạo index.

Để giảm xử lý lặp, compiler lưu tập base đã giới hạn địa lý và tập nguồn join
đã lọc trong CTE của từng truy vấn. Envelope rẻ giúp lọc cặp hình học trước;
`ST_DWithin` geography vẫn kiểm tra chính xác khoảng cách yêu cầu.

### Đơn vị nhập rõ ràng

Backend hỗ trợ giá trị có đơn vị, ví dụ:

```json
{"field":"residential_vnd_m2","op":"between","value":{"min":20,"max":40,"unit":"million_vnd_per_m2"}}
```

Được đổi thành `[20000000,40000000]` VND/m² đúng một lần. Các đơn vị được hỗ
trợ: `vnd_per_m2`, `million_vnd_per_m2`; diện tích `m2`/`ha`; khoảng cách
`m`/`km`; thời gian `s`/`min`, chỉ cho trường tương thích. Không đoán dấu phẩy
trong chuỗi nguồn hoặc tự suy diễn đơn vị người dùng chưa nêu.

## 2. Tiếp cận tiện ích bằng tuyến đường Goong

Hai tool mới đưa tổng số tool đăng ký cho model lên **34**:

| Tool | Nhiệm vụ |
|---|---|
| `accessibility_compare` | So sánh 1–6 parcel thật tới supermarket/park/hospital bằng Goong Distance Matrix V2 |
| `route_show` | Vẽ tuyến Goong Directions V2 từ một kết quả accessibility đã lưu trong cùng session |

`amenity_site_search` có `travel_mode` tùy chọn: null giữ sàng lọc đường thẳng;
nêu mode sẽ đánh giá tuyến đi trên shortlist. Số khớp tuyến đi chỉ tính các
ứng viên đã đánh giá, không đại diện mọi parcel trong vùng.

`candidate_compare` hỗ trợ thêm sáu tiêu chí: `hospital_travel_seconds`,
`park_travel_seconds`, `supermarket_travel_seconds`, `hospital_route_m`,
`park_route_m`, `supermarket_route_m`. Phải chọn mode để dùng các tiêu chí này.
Các metric chưa biết vẫn bị loại khỏi điểm chung, không được cộng lợi thế.

### Cách tính và giới hạn

1. Lấy parcel và POI thật từ hệ thống/OSM đã có nguồn.
2. Dùng điểm đại diện nằm trong hình học, chưa phải cổng đã khảo sát.
3. Mỗi parcel chọn tối đa 2 cơ sở gần theo đường thẳng cho mỗi loại yêu cầu.
4. Gộp điểm đích, chia batch tối đa 6 origins × 12 destinations; không gọi API
   cho mọi thửa. Trường hợp tối đa 6 parcel × 3 loại × 2 cơ sở cho mỗi thửa
   tạo tối đa 216 cặp trong toàn lần đánh giá.
5. Matrix trả khoảng cách và thời gian của mode. So sánh thời gian chọn cơ sở
   nhanh nhất trong shortlist; yêu cầu khoảng cách chọn tuyến ngắn nhất.
6. Không có tuyến, lỗi quota hoặc thiếu POI → chưa biết; không thay bằng 0 hay
   đường thẳng có nhãn là tuyến đi.
7. Người dùng có thể bấm **Show route to hospital/park…**; line được vẽ từ
   polyline của provider. Source, mode và cảnh báo vẫn đi cùng kết quả/export.

Đây không phải tối ưu mọi cơ sở trong thành phố, xác minh cổng, đảm bảo thời
gian giao thông hiện tại hoặc dự báo sau xây dựng. SUMO vẫn có nhiệm vụ riêng.

### Mode được xác minh

API thật đã nhận `car`, `bike`, `truck`. Giữ nhãn mode `bike` của provider,
không tự khẳng định là xe đạp/xe máy nếu chưa làm rõ semantics. API thật trả
400 cho `walking`, `foot`, `motorcycle`; vì vậy chúng không được cấp cho tool,
dù tài liệu Goong có nhắc một số tên mode khác. Khi người dùng không nêu phương
tiện, agent hỏi lại hoặc đưa kết quả đường thẳng sơ bộ có nhãn.

## 3. Một ngữ cảnh vị trí cho web và agent

- Search places và `area_select source=goong_place` dùng chung Goong Places V2.
  Kết quả có địa chỉ hiện hành và địa chỉ cũ khi provider trả về.
- Địa điểm người dùng chọn trên web được truyền vào workspace đã kiểm tra.
  Prompt “Analyze the selected place” dùng `source=search_place`.
- Điểm Goong/địa điểm đã chọn tạo buffer **1.000 m có nhãn**, không phải quận.
- `source=street` vẫn dùng mạng đường OSM nguồn của nhóm, buffer đường 100 m.
- `source=viewport` dùng chính bbox tại thời điểm gửi prompt; việc kéo bản đồ
  sau đó không âm thầm đổi vùng đã lưu.
- `source=place` yêu cầu hình học Nominatim nếu có. Polygon chỉ được gắn nhãn
  administrative khi provider thực sự phân loại boundary/administrative;
  nếu chỉ có bbox phải ghi rõ bbox. Không thay toàn quận bằng buffer một điểm.
- `scope_summary` công bố loại phạm vi, diện tích, radius, nguồn, bbox; giao
  diện có **Analysis boundary**. Đây không phải xác nhận pháp lý của ranh giới.
- Phân tích hỗ trợ polygon phức tạp tối đa 30.000 tọa độ, tách khỏi giới hạn
  2.000 đỉnh của footprint công trình trong các luồng thiết kế.

## 4. Kiểm thử theo nhiệm vụ

[Báo cáo kết quả và các case thực chạy](agent-query-routing-test-report.md):
82 test backend, 3 lượt model thật, 9 kiểm tra browser và 11 adapter đạt.

- `scripts/test-agent-query-server.py`: tạo PostGIS tạm riêng, không public port,
  nạp hơn 2.000 dòng và chạy toàn bộ test agent/SQL/routes/scope. Container và
  network test được dọn sau chạy; không nạp dữ liệu test vào warehouse nhóm.
- `scripts/check-agent-upgrade.py`: dữ liệu thật, unit conversion, giữ điều kiện
  refine, phạm vi Search places, route metrics, polyline, report và ba lượt
  model EN → VI → EN. Kiểm tra cả nội dung kết quả chứ không chỉ tool succeeded.
- `scripts/check-agent-query-matrix.py`: các adapter dataset của web.
- Evidence ở `test-results/query-upgrade/` gồm JSON kết quả và ảnh browser.

Các prompt thử thực tế được lưu nguyên văn trong script/evidence. Trường hợp
model sai tên layer/field được backend từ chối và cho sửa; không thực thi tên
bảng/SQL do model tự sinh. Trace của query giữ biểu thức JSON để kiểm tra lỗi
ngữ nghĩa và hiệu năng. Model chỉ nhận bản tóm tắt đủ nguồn/số đếm thay vì cả
polygon lớn; UI và export vẫn giữ dữ liệu đầy đủ.
