# Bàn giao branch simulation

Branch `feat/khoi-building-impact-simulation` dựa trên `origin/main` ngày 13/10/2026.

## Phạm vi

- Backend planning studies, job/worker, so sánh vị trí và tác động cộng dồn/phân kỳ.
- SUMO/SWMM, ledger hiện trạng, demand, normalization, sensitivity, provenance và map layers.
- Adapter snapshot parcel/WorldPop/OSM/WorldCover của hệ thống; API cho frontend chính.
- Counting pretrained/tracking, recount và visual review; catalog tham chiếu counting, flow default có nhãn synthetic.
- Demo API preview, gồm bảng thông số SUMO tuyệt đối và bảng so sánh có gate khi thiếu dữ liệu.
- Test backend/counting, scripts, mẫu và tài liệu liên quan. Worker profile trong `compose.khoi.yaml` phục vụ cấu hình PostGIS của nhóm; compose riêng bên dưới dùng SQLite cho demo độc lập.

Không đóng gói các thay đổi ETL giá đất/frontend đang làm trong workspace nguồn. Không đưa `.env`, credentials, `.venv`, model weights, video, snapshot runtime, database, kết quả solver hay thư mục `output/` lên Git.

## Chạy demo từ checkout mới

```powershell
git switch feat/khoi-building-impact-simulation
New-Item -ItemType Directory -Force .runtime/planning-system/snapshots
docker compose -f compose.simulation-demo.yaml up --build -d
```

Mở `http://127.0.0.1:8007/simulation/planning`. Nếu cổng 8007 đang được instance cũ dùng, đặt `$env:SIMULATION_DEMO_PORT = '8012'` trước khi chạy compose và mở cổng 8012.

Checkout mới chạy được các preset synthetic. Khối parcel thật chỉ xuất hiện khi có snapshot được cài trong `.runtime/planning-system/snapshots`. Không có default counting được cài thì không tự coi 19 lượt là dữ liệu sẵn có của checkout.

Volume compose này mới và khác `planning-program-runtime` trên máy tác giả. Các link Job UUID trong báo cáo lịch sử chỉ mở được trên instance đã giữ database đó; chúng không phải dữ liệu được clone qua Git.

## Dữ liệu parcel và counting

- Xem [hướng dẫn snapshot hệ thống](planning-system-demo-connection.md) và [API handoff](planning-simulation-api-handoff.md).
- Cài snapshot vào thư mục đã mount readonly; giữ nguyên byte và filename SHA để API kiểm tra integrity. Cần snapshot có đủ dữ liệu/phạm vi để chạy OSM network; không tự fallback thành mạng thật khác.
- Xem [pipeline counting](../scripts/traffic-counting/README.md). Video/model và cấu hình camera phải chuẩn bị riêng; counting core có thể test mà không tải Torch/model.
- Cài reference từ output review có `review-summary.json` và `config.json`:

```powershell
python scripts/traffic-counting/install_flow_default.py --review <folder-review> --destination .runtime/planning-system/snapshots/counting
```

Clip22 đã review ở máy tác giả có 19 lượt/16,67 giây: mức chuyển giả định 4.104 xe/giờ tổng các loại, SUMO hai lớp dùng 3.888. Không coi đây là quan trắc của mọi đường hoặc OD đã hiệu chỉnh. [Chi tiết](traffic-city-demo-default.md).

## Kiểm thử

Workflow `khoi-checks.yaml` kiểm thử API/ETL với PostGIS và thêm bước counting/ID repair. Các script UI kiểm thử local cần Playwright và Microsoft Edge; chạy trong thư mục đã có `.runtime/ui-check/node_modules/playwright-core` theo hướng dẫn demo, không phải dependency runtime của backend.

Các báo cáo có số test và Job UUID trước đây là bằng chứng của các phiên kiểm thử đó; không tự diễn giải thành CI của branch này đã xanh. Kiểm thử đóng gói branch được báo riêng khi push.

Kiểm thử đóng gói ngày 13/10/2026: **192/192 passed** trong checkout riêng dựa trên `origin/main`, 194,58 giây. Tập test gồm planning, integrated simulation, background/map context/parameters và counting/ID repair. Chạy bằng Python virtualenv đã có trên máy, với cwd/PYTHONPATH trỏ vào checkout mới; không phải kiểm thử cài dependency vào môi trường trắng. Compose demo được kiểm tra bằng `docker compose config --quiet`; chưa chạy stack compose mới trong lần đóng gói này để tránh trùng instance local đang dùng.

## Giới hạn

Đây là công cụ what-if. Occupancy/capacity còn unknown; quy hoạch chưa phải xác nhận pháp lý; SWMM chưa tạo flood depth 2D; bóng đổ chưa phải nhiệt độ. Bảng SUMO hiển thị số liệu mô hình tuyệt đối, còn bảng so sánh giữ unknown khi thiếu căn cứ. Không dùng delay xe hoàn thành đơn lẻ để xếp hạng khi còn backlog.
