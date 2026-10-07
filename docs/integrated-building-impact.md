# Simulation tác động tổng hợp — bản triển khai

Demo đầu tiên: **chung cư tại Thủ Đức**. AI giải thích được hoãn theo yêu cầu ngày 07/10/2026. Tham chiếu phạm vi: [kế hoạch](integrated-building-impact-plan.md).

## Chạy và sử dụng

Sau khi cài `requirements-dev.txt`, chạy từ root repo:

```powershell
$env:PYTHONPATH = 'backend;etl'
$env:SCENARIO_DATA_DIR = '.runtime/integrated-native-runs'
$env:SIMULATION_WORK_DIR = '.runtime/integrated-native-solvers'
& .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Mở **http://127.0.0.1:8002/simulation/integrated**. Với stack local riêng `compose.khoi.yaml`, dùng cổng **8001**. Stack dùng chung `compose.yaml` giữ PostGIS 17, frontend React và chỉ mở port frontend: truy cập `/simulation/integrated` qua cùng host/port frontend. Nginx chuyển API/trang demo đến backend với timeout 300 giây. Demo công thức cũ vẫn truy cập tại `/simulation`, có liên kết sang trang mới.

1. Chọn mẫu chung cư, sửa số căn/cư dân, hình học và thiết kế. Mẫu có 200 căn, 600 cư dân, 12 nhân viên, 80 lượt khách/ngày, 12 tầng cao 36 m. Đây là thiết kế tổng hợp, không phải công trình đã khảo sát.
2. Vẽ footprint/khu đất hoặc nhập GeoJSON trong phần nâng cao. Mái được tính từ footprint; dùng **Tính sân cứng còn lại** để cân bằng diện tích. Phần nâng cao hỗ trợ nhiều khối/công năng, diện tích sàn thực, lịch 24 giờ, cây, hiện trạng có nguồn, thiết bị, tái dùng nước và cửa xả bể.
3. Chọn kịch bản sức ép low/base/high, ngày bóng đổ và seed. Không cần nhập tay hệ số runoff, trip rate hay năng lực mạng. Các hệ số demo được hệ thống chọn và công khai nguồn tổng hợp.
4. Chạy trước/sau. Xem lợi ích phục vụ và sức ép riêng, bảng 22 chỉ số, điện/nước theo giờ, bản đồ vector và số xe/nước tràn thực từ solver.
5. Chọn phần được sửa, ngân sách tùy chọn, giới hạn chuyển bề mặt/thêm bể. Hệ thống chạy lại ứng viên rồi báo mục tiêu đạt/chưa đạt, chi phí và đánh đổi.
6. Tải snapshot JSON hoặc ZIP input/output solver; mở lại qua `?run=<UUID>`. Đổi thiết kế sẽ ẩn kết quả cũ.

Các công trình trường học, văn phòng, bệnh viện có preset. `residents` là dân cư thường trú; `daily_users` là học sinh/người dùng/bệnh nhân không thường trú; `staff` và `daily_visitors` tách riêng. Số người phục vụ không được cộng thành dân số thường trú.

## Các module thực sự chạy

| Nhóm | Phương pháp | Đầu ra / giới hạn |
|---|---|---|
| Xây dựng/bề mặt | WGS84 geodesic + Shapely overlay | Mật độ/FAR, diện tích sàn, xanh/không thấm, union tán cây; sàn thiếu bản vẽ được ghi là footprint × tầng |
| Điện/nước/nước thải | Thư viện tổng hợp theo công năng, lịch 24 giờ | kWh/ngày ≠ kW peak; nước tưới tách khỏi sanitary; ledger tái dùng và năng lượng xử lý giả định |
| Runoff screening | C × diện tích × mưa, dung tích bể trống | Screening độc lập; không thay thế thủy lực SWMM và không nhận là độ sâu ngập |
| Giao thông | **SUMO 1.27.1 thực**; mạng tín hiệu 4 nút, xe con/xe máy, dừng tại cổng, sublane | Peak-hour + 10 phút clearance; delay/queue, số hoàn thành/chưa hoàn thành/chưa xuất phát. Mean delay chỉ tính chuyến hoàn thành |
| Thoát nước | **EPA SWMM thực qua swmm-toolkit 0.17.0**; Horton, dynamic wave, bể/orifice/cống/outfall | Runoff 5 phút, depth/tràn nút/thời gian, continuity error. Mạng/cao độ/đất đều tổng hợp; chưa có triều và ngập bề mặt 2D |
| Bóng đổ | Vị trí mặt trời gần đúng UTC+7 + sweep polygon theo chiều cao | 08–17h, bản đồ 09/12/15h; địa hình phẳng, cây như khối đục, ngoài khu đất chỉ xét vùng 300 m; không dự báo nhiệt độ/Tmrt |
| Dân cư/dịch vụ | Nhóm người chung + công suất tổng hợp, khoảng cách dọc mạng kịch bản | Lợi ích nhà ở/phục vụ; nhu cầu dịch vụ chưa đáp ứng; tiếp cận đi bộ tổng hợp. Chưa gắn travel time SUMO vào routing dịch vụ |
| Đường | Mạng nền tổng hợp được đóng băng | Chiều dài cộng/trừ theo thiết kế chỉ là screening; SUMO chưa tái dựng topology từ các thay đổi đường này |
| Giá đất/ngập/quy hoạch | Nạp snapshot GeoJSON đang có trong `DATA_DIR/layers` trong 1 km | Hash/metadata/count/coverage; giá đường gần không có nghĩa là giá áp dụng cho khu đất; không tạo giá/quy hoạch pháp lý giả |

Parking được lưu như thông tin thiết kế, chưa có mô hình tìm chỗ đỗ/parking spillover. Thêm làn cổng thay đổi approach; mô hình dừng vẫn phục vụ tại lane 0. Không giả định hiệu quả của các trường chưa được engine sử dụng.

## Dữ liệu và tính tái hiện

- Nếu thiếu baseline: khu đất trống tổng hợp 15% sân cứng, 15% thấm, 70% xanh. Có thể cung cấp `baseline.design` + `baseline.source`; hệ thống không coi dữ liệu người dùng cung cấp là đã xác minh.
- Mạng đường/OD/hành vi xe, mạng cống/cao độ/đất, dân số ngoài khu đất/công suất dịch vụ, năng lực điện/nước và chi phí/mục tiêu đều có nhãn **synthetic**.
- Dữ liệu flood history/risk/satellite/land price được đọc từ PostGIS khi cấu hình warehouse, hoặc cache local; lưu feature/metadata/hash trong context. Hash PostGIS áp dụng cho phần context truy vấn trả về; hash file áp dụng cho bytes cache. Kết quả không tự tải WorldPop/DEM hay xác nhận hiện trạng thực từ OSM. Thiếu lớp thì báo unavailable; lỗi kết nối DB trả 503.
- Mưa mặc định là **trận thiết kế tổng hợp** 42/60/78 mm trong 1 giờ, tiếp theo 2 giờ không mưa. Forecast cache được ghi nguồn/thời điểm, không tự lấy forecast hết hạn làm thời tiết hiện tại.
- Low/base/high cùng thay mưa và tải chuyến ×0,7/1/1,3. Đây là stress cases; không phải xác suất hay confidence interval. Kiểm thử seed xác nhận cùng seed tái hiện route và delay, seed khác thay phân bố; chưa phải nghiên cứu ensemble hiệu chỉnh.
- Trước/sau/gợi ý dùng chung baseline, điều kiện, library, seed và context hash. ZIP có `.inp`, network/route XML, report, output binary và manifest SHA256. Không chỉ lưu điểm đánh giá.
- Run khác phiên bản model vẫn mở được; API yêu cầu dự tính mới trước khi sinh gợi ý, để tránh tính lại snapshot cũ bằng engine đã thay đổi. Điện dự phòng được kiểm tra bằng mức tăng lớn nhất tại cùng giờ trước/sau, không trừ hai đỉnh ngày ở hai thời điểm khác nhau.
- JSON/PostGIS là append-only; mỗi lần predict/recommend có UUID riêng, gợi ý lưu `parent_id`. PostGIS được dùng khi có `DATABASE_URL` (local riêng) hoặc `WAREHOUSE_*` với mật khẩu (stack chung), JSON atomic khi chưa cấu hình database. DB lỗi trả 503, không tự đổi sang kho khác.
- Artifact native ở `SIMULATION_WORK_DIR`: local `.runtime/...`; Docker named volume `/runtime/solvers`. Kho này độc lập với dữ liệu ETL chỉ đọc. Cần backup và chính sách retention theo dung lượng khi deploy; xóa artifact không xóa snapshot nhưng ZIP trả 410.

## Đánh giá và gợi ý

Không cộng mọi nhu cầu tăng thành một điểm “xấu”. Housing/service benefits, áp lực hạ tầng và biến động hình khối được trình bày riêng. Mục tiêu xanh/impervious/runoff/overflow và utility spare capacity là **mục tiêu giả định của dự án, không phải quy định pháp luật**.

Mục tiêu thủy lực dùng SWMM node overflow; mục tiêu traffic yêu cầu không còn xe chưa xuất phát/hoàn thành. Không kết luận đạt chỉ vì screening giảm runoff. Continuity error trên 5% hoặc count xe không cân bằng sẽ làm kết quả không đủ điều kiện xếp hạng “targets_met”. Tràn nút được tích phân theo mẫu report 5 phút, có sai số lấy mẫu và được ghi rõ.

Ba template ứng viên:

- Landscape/drainage: chuyển sân cứng thành xanh/thấm, thêm bể với cửa xả thiết kế.
- Operations/utilities: thiết bị nước/điện tiết kiệm theo hiệu quả tổng hợp, giãn lịch chung, chuyển lịch sạc EV.
- Combined: kết hợp hai nhóm.

Mọi ứng viên giữ nguyên danh sách building, footprint, tầng, chiều cao, sàn, cư dân và công suất; chạy lại GIS/demand/shadow/SUMO/SWMM. Lịch được giãn nhưng tổng nhu cầu/chuyến ngày bảo toàn. Tưới/EV/treatment có thể tạo đánh đổi; bể xả hạn chế cũng có thể làm tràn nặng hơn. Pareto chỉ so trong tập ứng viên này, không tuyên bố tối ưu toàn bộ không gian thiết kế. Có thể trả **partial/no_feasible_candidate**.

Giá/hiệu quả giải pháp là synthetic, cần hồ sơ thiết kế/báo giá để áp dụng. Không nhập ngân sách thì chỉ báo chi phí. Không tự giảm cư dân/số căn để làm phương án đẹp hơn.

## API và tổ chức code

| Endpoint | Chức năng |
|---|---|
| `GET /api/v1/scenarios/integrated/presets` | Mẫu công năng, thư viện, cảnh báo baseline |
| `POST /api/v1/scenarios/integrated/predict` | `site`, `development`, tùy chọn baseline/conditions; tính và lưu |
| `GET /api/v1/scenarios/integrated/{UUID}` | Mở snapshot |
| `POST /api/v1/scenarios/integrated/{UUID}/recommendations` | Ràng buộc/ngân sách; chạy lại và lưu con |
| `GET /api/v1/scenarios/integrated/{UUID}/artifacts` | ZIP scenario + input/output native |

Code Khôi:

- `backend/app/services/simulation/integrated/models.py`: schema/giới hạn/kiểm tra lịch, bể.
- `library.py`, `context.py`: presets/hệ số, snapshot dữ liệu nền, nguồn/seed/hash.
- `geometry.py`, `demand.py`: GIS/bóng đổ, demand chung/ledger.
- `solvers.py`, `swmm_worker.py`: SUMO subprocess và SWMM trong process riêng để tránh global state C.
- `engine.py`: orchestration, assessment, constraints/actions/rerun/Pareto.
- `backend/app/routers/integrated_scenarios.py`: API, lưu run, worker admission tối đa 2 requests đồng thời.
- `backend/app/static/integrated.*`: UI độc lập, map vector không cần CDN/tile.
- `backend/tests/test_integrated_simulation.py`: unit/metamorphic và solver thực.
- `scripts/test-integrated-local.py`, `scripts/test-integrated-ui.cjs`: regression Windows/Linux/API/PostGIS/browser.

Native subprocess timeout 60 giây/lần; pilot ≤100.000 m², ≤8.000 xe/giờ. API đồng bộ, nên frontend/proxy cần timeout đủ dài cho rerun nhiều ứng viên. Chưa có persistent job queue/authentication; dùng local hoặc mạng nội bộ trước khi mở dịch vụ công khai.

## Phần còn lại

**Có điều kiện:** SOLWEIG thermal comfort, flood 2D/coupling, EPANET water pressure, EnergyPlus thermal energy, sanitary hydraulics, network layout/parking và routing theo SUMO. API ghi rõ unavailable, không sinh số nhiệt độ/áp lực/độ sâu giả.

**Hoãn theo người dùng:** AI giải thích. Không cần endpoint/model AI ở stage này.

**Deploy 156:** người dùng xác nhận chưa có self-hosted runner và `.env`; xem [hướng dẫn deploy](integrated-deployment.md). Kết quả kiểm thử và số liệu minh họa nằm trong [báo cáo](integrated-simulation-test-report.md). Test phần mềm với dữ liệu tổng hợp không phải kiểm định độ chính xác mô hình tại Thủ Đức.
