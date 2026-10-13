# Mặc định lưu lượng đường từ counting

## Mức mặc định đã chọn

Nguồn: UIT-ADrone clip `50m_90d_morning_congkhuA_22_3_0`, pretrained detector và tracking; vạch đếm kéo dài đến `y=0.65`. Video 500 frame, 30 fps, dài 16,6667 giây. Đếm 19 lượt: 17 xe máy, 1 ô tô, 1 xe buýt. Chưa có nhãn độc lập để xác nhận độ chính xác.

| Loại | Lượt trong clip | Quy đổi xe/giờ |
|---|---:|---:|
| Xe máy | 17 | 3.672 |
| Ô tô | 1 | 216 |
| Xe buýt | 1 | 216 |
| Tổng, hai hướng cộng lại | 19 | **4.104** |

Công thức: `q = N × 3600 / thời lượng thực tế`. Không dùng thời lượng 60 giây trong config vì clip thực tế ngắn hơn.

Đây là **mức giả định demo giống nhau cho các đường chưa có dữ liệu**, không phải quan trắc các đường ở TP.HCM. Không chia theo làn, không coi là lưu lượng riêng của mỗi hướng; chưa có hiệu chỉnh theo cấp đường, giờ hay năng lực thông hành.

## Cách dùng trong hệ thống

- Service `counting_reference.flow_default(reference_id, road_id, observed_vehicles_hour)` trả mức mặc định cho một đường. Nếu có số liệu đường, dùng số liệu đó; giá trị 0 cũng hợp lệ và không bị thay bằng mặc định. Caller phải bảo đảm dữ liệu quan trắc đúng đường/thời điểm trước khi truyền vào.
- `GET /api/v1/planning/demo/system/traffic-default` trả chính sách mặc định, nguồn, đơn vị và hạn chế cho frontend của nhóm. Chỉ mở trong test demo.
- `POST /api/v1/planning/demo/system/prepare` tự chọn reference đã cài khi caller không truyền `counting_reference_id`. Nếu không truyền `traffic_peak_vehicles_hour`, dùng profile giả định cố định từ clip; truyền giá trị này sẽ thay mức mặc định bằng profile đỉnh/ngày hiện có.
- Counting reference mới được lưu theo SHA-256; `default-reference.txt` chọn reference mặc định. Không sửa hay ghi đè reference 15 lượt trước đây. Có thể dùng `PLANNING_DEFAULT_COUNTING_REFERENCE_ID` để cấu hình reference thay thế.
- Snapshot traffic có profile riêng vẫn được ưu tiên bởi resolver hiện có. Chỉ thêm mặc định vào đường không có dữ liệu qua service; **chưa ghi lưu lượng vào bảng đường của cả thành phố và chưa thay frontend của nhóm**.

## SUMO khác lưu lượng từng đoạn đường

Solver hiện hỗ trợ ô tô và xe máy: đầu vào demo tương ứng **3.888 xe/giờ**, gồm 216 ô tô và 3.672 xe máy. Xe buýt được giữ trong nguồn counting nhưng chưa đưa vào solver hai loại xe.

Trong study hiện tại, đây là **một proxy tổng nhu cầu OD của vùng mô phỏng**, phân phối qua các background route hiện có. Không bơm 3.888 xe vào từng internal edge: một xe đi qua nhiều edge, nhân theo số đoạn sẽ đếm lặp và tăng nhu cầu sai. Chưa bảo đảm SUMO tạo ra đúng 4.104 xe/giờ trên từng đường.

Profile 24 giờ cố định là giả định để demo chạy tại mọi giờ. Không đủ dữ liệu để suy ra profile ngày, cao điểm hoặc OD thật từ clip 16,67 giây. Để ước lượng riêng từng đường cần camera-to-road mapping, cửa sổ đo dài hơn và phân bổ OD theo mạng.

## Cài đặt và kiểm tra

```powershell
.\.venv\Scripts\python.exe scripts/traffic-counting/install_flow_default.py --review output/counting-visualization-clip22-extended-line --destination .runtime/planning-system/snapshots/counting
$env:PYTHONPATH = "$PWD/backend;$PWD/etl"
.\.venv\Scripts\python.exe -m pytest backend/tests/test_counting_flow_default.py backend/tests/test_planning_system_demo.py backend/tests/test_planning_uncertainty.py -q
```

Kiểm thử local: **19/19 đạt**, gồm quy đổi và bảo toàn tổng theo loại xe, loại xe solver hỗ trợ, override bằng số 0, chọn reference tự động, giữ override đỉnh và đóng API khi tắt demo.

Ngày 13/10: đã bật Docker, rebuild image và thay API/worker demo 8007, giữ volume dữ liệu và readonly snapshot. Giao diện để trống đỉnh OD thay cho giá trị 800 cũ; API tự chọn reference mới. Kiểm tra UI xác nhận mặc định 3.888 xe/giờ và override bằng 0. Solver có cấu hình `PLANNING_SOLVER_TIMEOUT_SECONDS`; instance demo dùng 600 giây sau khi một child SUMO vượt giới hạn 120 rồi 300 giây (lượt thứ hai đạt thời điểm mô phỏng 3.928/4.200, còn 428 xe đang dừng). Giữ nguyên vật lý/nhu cầu, không hạ lưu lượng để làm test pass. Chưa commit/push.

Kiểm thử bổ sung sau thay đổi runner: **16/16 đạt** (counting default và planning jobs), lưu tại `test-results/planning-flow-default/regression.xml`. Đây là tập kiểm thử bổ sung, có overlap với 19 test trước; không cộng hai số thành tổng test độc lập.

Case native mới đã hoàn tất: job `7ae2d330-34b8-4389-94fc-7b77ab8219ca`, run `dc054c7a-5199-4d56-bae2-2fb0ea2595c4`, 3 parcel/5 options/3 phases, OSM + SUMO/SWMM. [Mở case](http://127.0.0.1:8007/simulation/planning?job=7ae2d330-34b8-4389-94fc-7b77ab8219ca&option=together_3). Cân bằng số xe và nước đạt; một số phương án còn xe tồn đọng nên không xếp hạng từ delay xe hoàn thành đơn lẻ. Xem [báo cáo đánh giá](simulation-competition-readiness-20261013.md).

### Bảng thông số SUMO trên web

Đã thêm **Thông số SUMO của lượt chạy** ngay trước bảng So với hiện trạng: lưu lượng nền theo lớp xe, số xe dự kiến/đã vào/hoàn thành/chưa hoàn thành/chưa vào, tồn đọng, tỷ lệ hoàn thành, delay, hàng chờ và bảo toàn số xe. Bảng thay đổi theo phương án, giờ và seed, dùng dữ liệu của run đã lưu; hiện trạng mô phỏng cũng được ghi là có giả định. Nguồn counting lấy từ context của chính run, không dùng pointer hiện tại để thay nguồn của run cũ.

Bảng so sánh cũ vẫn giữ insufficient_data khi không có occupancy đủ để suy ra tác động. Việc hiển thị số liệu tuyệt đối của solver không tự tạo ra so sánh đã xác minh. Screening hiển thị thông báo chưa chạy SUMO.

UI kiểm tra thành công: nền 3.888, phương án cả 3 dự kiến/hoàn thành 3.909, hàng chờ 41,61 m, backlog bằng 0; chuyển P1/P3/hiện trạng lần lượt có backlog 1.113/436/869; giữ số 0 và gate của bảng so sánh; không có lỗi JavaScript. Bằng chứng: `test-results/planning-flow-default/sumo-raw-table.png` và `saved-result-ui-report.json`.

Lần build image chứa bảng mới bị timeout tại Docker Hub auth. Đã cập nhật hai file static vào container API hiện tại, giữ worker/run/dữ liệu. Source repo đã có bảng mới; khi dựng lại container từ image cần build lại từ source để giữ thay đổi này. Không cần chạy lại solver để mở bảng cho run đã lưu.

## Visualize toàn bộ tập test hiện có

Trang tổng hợp: `output/counting-test-suite/index.html`.

| Clip | Lượt qua vạch | Vạch |
|---|---:|---|
| 16 | 17 | Ngang, nhánh phía nam |
| 22 | 19 | Dọc, kéo dài đến y=0.65 |
| 31 | 13 | Dọc, kéo dài đến y=0.65 |

3/3 clip đã tải trên 152, mỗi clip 500 frame. Không phải toàn bộ UIT-ADrone. Render offline từ tracks của pretrained model, sửa ID trùng theo phương pháp hiện có; clip31 được tính lại với vạch mới trên cùng tracks, không huấn luyện hay rerun detector. Không gộp các clip thành một lưu lượng trung bình của thành phố.

Kiểm tra bàn giao: SHA-256 của cả 3 video tải về trùng bản render trên server; cả 3 video H264 mở được trong Edge, 1920×1080, thời lượng 500/30 giây. Đã kiểm tra chỉnh tốc độ và chụp frame tại giây thứ 1 của từng clip; không có lỗi JavaScript. Kết quả lưu ở `output/counting-test-suite/browser-check.json`.
