# Kết quả kiểm tra preview Development simulation

Ngày: 15/10/2026. Branch riêng `feat/development-simulation-context`, gốc main `fe69437`.

## Bản đã triển khai

- Web trên máy hiện tại: **http://127.0.0.1:8192**, qua SSH tới server 156 cổng loopback 51875.
- API riêng: 8022. Compose project: `urbandynamics-development-preview`.
- Folder server: `/GuestShare_NAS/WorkingSpace/Personal/nguyenmv/MLAI/UrbanDynamics/development-preview`.
- Không thay branch main, không thay dịch vụ production và không push GitHub.

## Chức năng đã bổ sung

1. Mặc định giữ cảnh quan ngoài footprint. Dùng OSM/WorldCover từ snapshot khi phủ scope; phần chưa phân loại ghi nhãn 40/50/10 thay vì tự coi toàn bộ là paved.
2. Chuẩn bị mạng quanh vị trí chọn, cache bất biến, dùng cùng mạng/OD nền/seed trước và sau. Ưu tiên mạng OSM-derived trong kho nhóm, sau đó extract đã cài và Overpass. Nền counting hoặc profile synthetic có nguồn rõ.
3. Hiện Before / After / Change, bảng SUMO delay/queue/backlog, SWMM overflow/peak và nguồn dữ liệu. Không biến Unknown thành hiện trạng 0.
4. Nút **View last completed run** mở kết quả đã lưu cùng revision và scope, không tạo job. Đây là cách xem case native ngay trong web nhóm mà không phải chờ chạy lại.

## Case thật đã chạy

| Thuộc tính | Giá trị |
|---|---|
| Parcel | 1937203, Trường Thọ, Thủ Đức; hình học cadastral từ hệ thống |
| Plan | `67e729aa-f3f1-4ef2-9345-39987367c21e` |
| Job | `4eb7caf9-f7d9-4904-ac45-cb8793e09be4` |
| Result | `5e49c69d-7a41-4169-9a47-8f4b688dada4` |
| Đề xuất | Chung cư 4 tầng, footprint vẽ trong parcel; đây là phương án thử, không xác nhận đất trống |
| Mạng native | 858 cạnh SUMO; tái dựng cục bộ từ kho mạng OSM-derived |
| Vùng mạng | Study area và buffer 750 m |
| Lưu lượng nền | 3.888 xe/giờ từ chính sách chuyển reference counting; không phải đo tại parcel |
| Điều kiện | Giờ 07:00 và 18:00, seed 2026, mưa 60 mm |
| Đầu vào đất | ESA WorldCover 2021 v200 + nguồn OSM trong snapshot; khoảng 587,99 m² mặt đất chưa phân loại |
| Inventory hiện trạng | Unknown trong case API này; không cung cấp Goong tile context và không có inventory generated phù hợp |
| Chuẩn bị đầu vào qua API | Khoảng 1,29 giây, chưa bao gồm toàn bộ bước tạo network/solver của worker |
| Tạo job → hoàn thành | 1.044 giây, khoảng **17 phút 24 giây**, trên server đang có các workload khác |
| Solver con | 1 network + 4 SUMO + 2 SWMM thành công |
| Cân bằng số xe | Đạt |
| Cân bằng SWMM | Đạt |

### Một số số liệu mô hình

Hai giờ cho kết quả giống nhau do profile nền counting mặc định là hằng 24 giờ; đây không phải nhận định giờ cao điểm ngoài thực tế.

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Xe hoàn thành | 809 | 813 |
| Xe đã xuất phát nhưng chưa hoàn thành | 2.424 | 2.430 |
| Xe chưa xuất phát | 655 | 649 |
| Queue tối đa | 633,76 m | 633,75 m |
| SWMM overflow | 1.549,42 m³ | 1.552,01 m³ |
| SWMM peak runoff | 0,9227419 m³/s | 0,9227449 m³/s |

Các hàng traffic được ghi **Assumption-based comparison** vì baseline occupancy chưa biết. Có nhiều xe chưa hoàn thành nên chênh lệch completed-trip delay phải ghi **Not comparable**. Không diễn giải queue giảm 0,01 m thành một cải thiện thực tế. Overflow là kết quả mạng thoát nước tổng hợp, không phải vùng ngập 2D đã đo.

## Kiểm tra bảo vệ dữ liệu và vận hành

- Đã hỏi trực tiếp kết nối DB của preview: `SHOW transaction_read_only` trả **on**.
- `ZONING_STORAGE=sqlite`; đã xác nhận file plans SQLite và studies SQLite nằm trong `/runtime` của preview.
- Mạng Docker riêng; backend preview không dùng chung service DNS `backend` của production.
- Cache OSM kiểm tra SHA-256, ranh giới phải phủ study area; thất bại lấy dữ liệu không tự chuyển sang mạng đường giả.
- Đã gặp Overpass 406/429/500/504 trong quá trình thử. Header nhận diện ứng dụng đã được sửa; đường ưu tiên kho OSM-derived giúp case này không cần chờ dịch vụ công cộng.
- Một lần theo dõi qua tunnel bị ngắt khi thay frontend. Job server vẫn hoàn tất; đã lấy lại kết quả bằng `--collect`, không chạy thêm native job để bù.
- Native case khá nặng. Khi trình diễn nên mở kết quả đã lưu; Quick estimate dành cho phản hồi tương tác. Không cam kết native dưới một phút.

## Các lỗi tìm thấy và đã sửa trong quá trình kiểm tra

- Metadata float chưa canonicalize khiến API và worker tính context hash khác nhau: đã chuẩn hóa lại trước khi hash, regression qua cả screening/native.
- Một parcel được bọc MultiPolygon nhưng chỉ có một polygon bị từ chối: đã chuẩn hóa trường hợp một phần, vẫn từ chối geometry rời không được hỗ trợ.
- UI đọc SUMO/SWMM từ `comparison` thay vì `traffic_comparison`/`drainage_comparison`: đã sửa và kiểm tra qua API/browser thực.
- Dữ liệu giả định trong `scenario_values` có thể làm hiện trạng thiếu dữ liệu hiện thành 0: bảng tác động cơ bản giữ Unknown; bảng native dùng nhãn giả định rõ và chặn kết luận delay khi còn backlog.

## Bằng chứng

- **40/40 test backend đạt**, khoảng 76 giây.
- **6/6 test frontend đạt**; TypeScript đạt và frontend build triển khai thành công.
- **1/1 browser regression đạt** với fixture offline, gồm screening/native, reload, revision cũ và nhiều viewport.
- Kiểm tra browser trên server thật đạt: mở kết quả bằng **View last completed run** từ phiên trình duyệt mới, xem SUMO và nguồn, restore sau reload, mobile không tràn trang, không có page error.

- `test-results/development-context-backend.xml`: JUnit backend.
- `test-results/development-context-frontend.json`: Vitest frontend.
- `test-results/development-context/browser-regression.json` và `.log`: browser regression với fixture offline; lần đạt hoàn tất khoảng 49 giây.
- `test-results/development-context/live-native.json`: case API thật, frozen input, kết quả và solver children.
- `test-results/development-context/browser-result.json`: kiểm tra web server, nguồn, bảng kết quả, reload và mobile.
- `test-results/development-context/web-results.png`, `web-mobile.png`: ảnh kiểm tra trực quan.

Kiểm thử chức năng và cân bằng solver không chứng minh độ chính xác thực địa. Phần còn thiếu calibration OD, chu kỳ đèn, inventory/occupancy đầy đủ và công suất hạ tầng vẫn được ghi nhãn.
