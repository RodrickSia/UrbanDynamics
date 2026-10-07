# Ghép bảng giá đất với đoạn đường

## Phạm vi và mức bảo đảm

Phạm vi dữ liệu nguồn là TP.HCM mở rộng: TP.HCM, Bình Dương và Bà Rịa–Vũng Tàu trước sáp nhập, gồm Côn Đảo. Bảng giá có 9.502 dòng; số dòng có giá không đồng nghĩa với số đoạn đã hiển thị trên bản đồ.

Matcher `ward-unique-path-v1` sử dụng polygon phường/xã hiện tại của OpenStreetMap, tên đường và hai đường giới hạn trong bảng giá. Đây là ghép không gian phục vụ phân tích; không xác nhận ranh địa chính hoặc độ chính xác pháp lý của từng đoạn. Giá trích PDF và hình học ghép tự động được đánh dấu chưa kiểm tra thủ công.

## Luồng xử lý

1. `extract.py`: lấy bảng giá đầy đủ hoặc JSON nguồn được chỉ định; giữ đơn vị gốc, mã dòng, vùng, phường, trang PDF.
2. `road_sources.py`: lấy đường OSM trong ranh giới thành phố với ô 20 km; truy vấn quá tải được chia nhỏ tối đa hai cấp. Lấy các relation phường/xã cấp 6, dựng polygon kín và kiểm tra phạm vi. Cache từng relation và từng ô đường để tiếp tục sau gián đoạn.
3. `road_matcher.py`: ghép đúng tên phường duy nhất, đúng tên đường/alias rõ ràng; cắt đường trong phường. Dòng có hai đầu mút chỉ được ghép khi hai đường giới hạn thực sự giao đường cần định giá và có một đường đi duy nhất. Phân biệt layer cầu/hầm tại giao cắt. Dòng “trọn đường” chỉ dùng đường trong phường, không nối các phần rời nhau tùy ý. Cắt phần hiển thị theo ranh thành phố đã duyệt và đánh dấu phần bị cắt; lỗi overlay OSM chuyển thành dòng chờ. Polygon phường, buffer và đường đã cắt được tái sử dụng trong cùng lượt chạy.
4. `pipeline.py`: ghép kết quả tự động với hình học đã duyệt thủ công. Hình học thủ công được ưu tiên; các proxy cũ chỉ trùng tên không được đưa qua kiểm tra toàn thành phố.
5. `transform.py`: đổi nghìn đồng/m² thành đồng/m²; gắn trạng thái duyệt, phương pháp ghép, relation phường, way đường và trang PDF.
6. `load.py`: nạp PostGIS và snapshot; các dòng chưa ghép có lý do trong `review/land_price_pending.json`.

Không dùng fuzzy matching, tự đoán tọa độ hoặc tự nối khoảng đứt. Tên phường trùng giữa vùng, đường thiếu, đầu mút mơ hồ, đường có nhiều lối đi và dòng nguồn trùng định danh đều chờ kiểm tra. Hai làn song song chỉ được chấp nhận với tag một chiều, loại đường phù hợp và khoảng cách giới hạn. Độ đầy đủ và tag OSM vẫn là giới hạn của phương pháp.

## Chạy

Từ thư mục repo, cài `etl/requirements.txt`, đặt `PYTHONPATH=etl` và `DATA_DIR=etl/data`.

```powershell
python scripts/prepare-hcmc-boundary.py --cached
python scripts/prepare-land-price-segments.py --cached
python -m src.main run land_price --full-city --segments etl/data/review/land_price_reviewed.geojson
```

`--cached` tái sử dụng dữ liệu đã tải. Lệnh pipeline toàn thành phố mặc định vẫn dựng lại kết quả ghép từ cache. Bỏ cache hoặc bật `refresh_source` trong scheduler để cập nhật nguồn. Nếu tải nguồn lỗi, job dừng trước bước publish; snapshot trước đó được giữ.

Workflow thủ công `.github/workflows/land-price-matching-data.yaml` chạy trên GitHub-hosted runner để tải nguồn và tạo artifact; không có thông tin đăng nhập hoặc quyền truy cập database production. Artifact có roads, polygon phường, đoạn tự ghép, dòng chờ và snapshot giá đất. Cache và artifact phần đã tải được lưu khi lỗi nguồn; nhập `resume_run_id` để tiếp tục từ artifact của lượt trước.

Nếu đã có roads toàn thành phố ở local/server, chọn `source_scope=wards` để chỉ tải polygon phường/xã. Tải artifact về, đặt `inputs/land_price_wards.geojson` và `raw/land_price/wards/` vào cùng `DATA_DIR` của road cache, rồi chạy lệnh chuẩn bị có `--cached`. Chế độ wards không publish lớp giá.

## Frontend

UI trước thay đổi này khóa lớp Land price. Đã nối lớp với TileJSON và vector tiles của API hiện có, thêm chú giải màu, giá ba loại đất, nguồn PDF, tình trạng duyệt và thống kê phần đã ghép/chờ. Chỉ tải tiles trong khung nhìn; kiểm tra metadata mỗi 5 phút và làm mới khi snapshot thay đổi.

Các lần cập nhật dữ liệu tiếp theo không cần sửa UI nếu giữ hợp đồng API/property hiện tại. Lớp thể hiện giá tham chiếu chính thức, không phải giá giao dịch; khu vực trống không có nghĩa giá bằng 0.

## Kiểm chứng local

- Frontend: 80/80 test đạt, build production và ESLint đạt.
- Trình duyệt Chromium/MapLibre thật: test vector tile, click giá, opacity, đổi nền và tắt lớp đạt; dùng dữ liệu fixture có kiểm soát.
- ETL/API: 38 test đạt, 1 test PostGIS integration bỏ qua vì Docker local chưa chạy. CI kiểm tra trên Linux và database PostGIS riêng.
- Smoke test nguồn thật: 1 polygon Phường Phú Thuận, 63.459 OSM ways, 9.502 dòng giá: 6 dòng ghép được sau kiểm tra cầu/hầm. Đây là kiểm tra một phường, chưa phải kết quả toàn thành phố.
- Lượt nguồn thật toàn thành phố: 159 polygon phường/xã hợp lệ; 63.459 ways OSM; 9.502 dòng giá ứng viên. Tạo snapshot 1.848 dòng đã ghép, 7.654 dòng chờ; 1.847 dòng ghép tự động và 1 đoạn đã duyệt thủ công.
- Cả 1.848 hình học hợp lệ, định danh duy nhất và nằm trong ranh phân tích. Có 1 đoạn cắt theo ranh thành phố, hiển thị nhãn partial tương ứng.
- API trên snapshot thật ở local trả HTTP 200: `/api/v1/land-prices` (1.848 features), `/api/v1/land-prices/rows` (9.502 records), TileJSON (metadata 1.848). Đây là file snapshot mode; việc phục vụ vector tiles trên production cần nạp PostGIS.

| Vùng trước sáp nhập | Dòng nguồn | Dòng có hình học | Dòng chờ |
| --- | ---: | ---: | ---: |
| TP.HCM | 5.480 | 1.343 | 4.137 |
| Bình Dương | 2.581 | 149 | 2.432 |
| Bà Rịa–Vũng Tàu | 1.441 | 356 | 1.085 |

Chỉ khoảng 19,4% dòng nguồn có hình học để hiển thị; phạm vi trải trên cả ba vùng chưa đồng nghĩa mọi đường đã có giá trên map. Nguyên nhân chính là thiếu tên đường OSM trong phường và mô tả đầu mút chưa có đường tương ứng. Các dòng trích PDF/hình học tự động chưa được duyệt thủ công, không dùng như hồ sơ định giá pháp lý.

Kết quả local dùng ở stack chính: `etl/data/layers/land_price.geojson`; dòng chờ: `etl/data/review/land_price_pending.json`; geometry tự ghép: `etl/data/review/land_price_auto_segments.geojson`. Mẫu thật của ba vùng: `docs/samples/land_price_spatial_three_regions.geojson`.

Nguồn hình học: [OSM API](https://wiki.openstreetmap.org/wiki/API_v0.6), [Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL); giấy phép ODbL. Nguồn/niên đại ranh giới và bảng giá được giữ trong metadata của từng snapshot.
