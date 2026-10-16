# Kết quả kiểm thử: PostGIS, Goong routes, scope

Ngày 16/10/2026. Branch `feat/development-simulation-context`.
Preview server 156 cổng 51875, tunnel **http://127.0.0.1:8192/**.

## Tổng hợp

| Nhóm | Kết quả |
|---|---|
| Backend regression + SQL trên PostGIS tạm riêng | **82/82 đạt**, không có test skip trong lần Linux này |
| Frontend TypeScript/Vite build | Đạt |
| Adapter dataset thật | **11/11 HTTP 200**; nguồn warehouse native dùng engine PostGIS |
| Manual API: SQL, refine, Search-selected scope, Matrix, Directions, weighted travel comparison, export | Đạt |
| Model thật EN → VI → EN | **3/3 đạt**, kiểm tra nội dung bộ lọc/kết quả/ID/tuyến đi/ngôn ngữ |
| Browser | **9 kiểm tra đạt**, có ảnh desktop/mobile và Markdown export |

Database test có 2.600 bản ghi giả lập hợp lý, nằm trong container tạm **riêng**;
không nhập chúng vào kho dữ liệu nhóm. Script tạo network/container riêng, không
public port và dọn tài nguyên sau chạy. Transaction ứng dụng vẫn read-only.
Có một cảnh báo deprecation TestClient/httpx; không có test thất bại trong lần
cuối. Các test model/API dùng dữ liệu nguồn thật, khác bộ dữ liệu SQL tạm.

## 1. Chứng minh không mất bản ghi sau 2.000 dòng

Trên PostGIS test: lọc trường n từ 2.500 đến 2.600, trả đúng **101** bản ghi
khớp, average **2.550**, hiển thị 3 dòng `[2600,2599,2598]`. Các bản ghi này
nằm ngoài 2.000 dòng đầu. Required spatial join, đơn vị triệu VND/m²,
NULL/NOT, group/average và truy vấn sai không làm đổi session đều được kiểm tra.

Trên dữ liệu thật quanh Gò Vấp:

- Viewport khoảng 4 km², có **30.072 parcel** trong phạm vi nguồn.
- Diện tích 80–200 m², cách một đường có giá tham chiếu đất ở 20–40 triệu
  VND/m² không quá 300 m: **177 bản ghi khớp**, hiển thị 3 thửa nhỏ nhất.
- Tạo truy vấn mới bỏ điều kiện giá/khoảng cách: **7.451 bản ghi khớp**,
  hiển thị đúng 2 thửa nhỏ nhất.
- Đây là số đếm bản ghi đã nhập, không xác nhận đủ mọi thửa ngoài thực địa,
  đất đang bán, đất trống hoặc giá áp dụng pháp lý cho từng thửa.

Một truy vấn kết hợp tại vùng đông thửa ban đầu chạm timeout **20 giây**.
Sau khi lọc/materialize tập nguồn join một lần và dùng envelope rẻ trước kiểm
tra geography chính xác, cùng case hoàn tất khoảng **1,8 giây** trong lần đo.
Đây là phép đo một case, không phải SLA cho mọi truy vấn. Giới hạn SQL 20 giây
vẫn được giữ; không lấy mẫu để thay số đếm khi timeout.

## 2. Luồng model đã kiểm tra

Prompt đầy đủ trong `scripts/check-agent-upgrade.py` và JSON evidence:

1. Tiếng Anh: tìm parcel 80–200 m², gần đường giá tham chiếu 20–40 triệu
   VND/m² trong 300 m, hiển thị tối đa 3, đếm trước limit.
2. Tiếng Việt: giữ khu vực, tạo truy vấn **mới**, bỏ điều kiện giá và khoảng
   cách đường giá, hiển thị đúng 2 thửa 80–200 m² nhỏ nhất.
3. Tiếng Anh: so sánh đi ô tô tới bệnh viện/công viên trong bán kính khám phá
   POI 3 km; vẽ tuyến tới bệnh viện cho **thửa đầu tiên từ truy vấn trước**.

Kết quả route của case có source **Goong Directions V2**, đúng parcel **1482720**,
dài khoảng **1.582 m**, thời lượng provider khoảng **363 giây**. Đây là ước tính
provider giữa điểm đại diện, không phải giao thông quan sát hay SUMO after.
Một số cơ sở trong OSM không có tên; hiển thị **Unnamed mapped hospital/park**,
giữ POI ID/nguồn, không tự đặt tên cơ sở.

Model từng gọi query trước khi chọn scope; guard chặn, model chọn viewport rồi
thực hiện lại. Lỗi này không tạo kết quả hay thay bằng vùng cũ. Trace giữ JSON
truy vấn để kiểm tra. Việc kiểm tra ngữ nghĩa chấp nhận filter AND tương đương,
bao gồm điều kiện đơn vị `VND/m2`, thay vì phụ thuộc một cách viết JSON duy nhất.

## 3. Scope và Goong

- Chọn kết quả Search places thật, gửi lại selected_place vào workspace,
  `source=search_place` dùng đúng tọa độ nguồn, buffer 1.000 m có nhãn.
- Viewport được phân biệt với polygon hành chính, bbox provider, buffer đường
  và buffer điểm. Có scope kind, diện tích, radius và nguồn trên UI.
- Phạm vi phân tích >2.000 đỉnh được kiểm thử độc lập với footprint công trình.
- Autocomplete/Detail chuyển sang V2; giữ địa chỉ mới/cũ từ provider.
- Matrix/Directions car được dùng thật. `bike` và `truck` được API chấp nhận;
  `foot`, `walking`, `motorcycle` trả lỗi 400 nên không cấp cho tool. Không tự
  đổi nghĩa mode bike thành xe đạp/xe máy khi chưa xác minh.

## 4. Browser

Các kiểm tra: caption số đếm tại database; nút route gọi API thật; LineString
route; nguồn route; scope kind; export giữ cả Matrix/Directions; panel mobile;
Search-selected place thực sự đi vào workspace gửi cho agent; không page error.
Kiểm tra selected-place binding cuối dùng response chat mock để tránh thêm một
lượt model: chỉ xác minh frontend gửi đúng tọa độ, không dùng mock làm bằng
chứng route/model. Các route và kết quả số liệu khác là API thật.

Ảnh được xem lại. Fill layer chỉ áp dụng polygon; tuyến Directions là **line
xanh**, không bị đóng thành polygon hoặc tô vùng giả. Label parcel chỉ áp dụng
hình học parcel. Cơ sở không có tên không hiển thị thành tên địa điểm bịa.

## Evidence local

Trong `test-results/query-upgrade/`:

- `postgis-tests.json`: stdout/status bộ 82 test.
- `live-cases.json`: dữ liệu API và ba prompt/response model, truy vấn thực,
  source metadata, lịch sử lỗi trước sửa.
- `browser-result.json`: các kiểm tra browser.
- `routes-desktop.png`, `routes-mobile.png`: ảnh đã kiểm tra.
- `report.md`: file tải từ web, có nguồn query và route.

Ma trận adapter: `test-results/general-agent/structured-query-matrix.json`.
File artifact nằm ngoài phần commit mặc định; tài liệu và scripts có thể review.

## Giới hạn còn lại

POI là dữ liệu bản đồ hữu hạn, chưa xác minh cổng/công suất. Routing chỉ đánh giá
shortlist, không tối ưu mọi POI/parcel trong thành phố. Giá tham chiếu đường không
thay thế giá thị trường/chi phí thu hồi. Chưa có mode đi bộ được xác minh, live
traffic hiệu chỉnh, pháp lý đất hay capacity hạ tầng đầy đủ. Phần nâng cấp này
không biến các giả định simulation hiện có thành dữ liệu đo thực tế.
