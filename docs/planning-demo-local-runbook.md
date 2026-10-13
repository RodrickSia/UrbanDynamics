# Chạy và review demo planning local

Ngày 11/10/2026. Dữ liệu synthetic; object counting và AI giải thích hoãn.
Frontend chính tích hợp theo [API handoff](planning-simulation-api-handoff.md).

**Cập nhật 12/10 — model 0.15:** demo 8007 đã có adapter parcel/snapshot từ
server 156, chỉ bật trong kiểm thử. Xem [hướng dẫn kết nối và giới hạn dữ liệu](planning-system-demo-connection.md).
Các case synthetic bên dưới vẫn được giữ để kiểm tra mô hình.

## 1. Instance đang chạy

Mở <http://127.0.0.1:8007/simulation/planning>.

API `planning-program-api` và worker `planning-program-worker` dùng image
`planning-demo-backend:local`, cùng volume `planning-program-runtime`.
Store SQLite nằm ở `/runtime/studies.sqlite`; solver ở `/runtime/solvers`.
PostgreSQL/PostGIS là tùy chọn đã kiểm tra bằng script riêng; instance demo
Docker 8007 này dùng SQLite. Docker chứa service, không thay thế PostgreSQL.

```powershell
docker inspect planning-program-api planning-program-worker --format '{{.Name}} {{.State.Status}}'
Invoke-RestMethod http://127.0.0.1:8007/health
```

## 2. Dựng instance mới trên máy khác

Từ root repo, cần Docker Engine hoạt động. Các lệnh dưới dùng tên container
và cổng của demo; chạy khi chưa có hai container cùng tên:

```powershell
docker build -f backend/Dockerfile -t planning-demo-backend:local .
docker run -d --name planning-program-api -p 127.0.0.1:8007:8000 --mount type=volume,source=planning-program-runtime,target=/runtime -e PLANNING_SQLITE_PATH=/runtime/studies.sqlite -e SIMULATION_WORK_DIR=/runtime/solvers -e PLANNING_BENCHMARK_MACHINE_ID=local-docker-worker planning-demo-backend:local
docker run -d --name planning-program-worker --mount type=volume,source=planning-program-runtime,target=/runtime -e PLANNING_SQLITE_PATH=/runtime/studies.sqlite -e SIMULATION_WORK_DIR=/runtime/solvers -e PLANNING_BENCHMARK_MACHINE_ID=local-docker-worker planning-demo-backend:local python -m app.services.simulation.planning.worker
```

Nếu cập nhật code: build image trước; xác nhận không còn job queued/running;
stop/remove đúng hai container, rồi chạy lại hai lệnh `docker run`. Giữ nguyên
volume để giữ studies, jobs, cache và artifact. Theo dõi bằng `docker logs`.

## 3. Case phần 1 và phần 2

1. Chọn **Một khu đất trên nền chung**, nạp mẫu; xem building plan/nguồn.
2. Chạy **Screening**, sau đó **SUMO + SWMM** để thấy road/node/link layers.
3. Chọn **So sánh vị trí A/B/C**: cùng 200 căn/600 cư dân/24.000 m² sàn.
4. Kiểm tra đầu vào, chạy screening; so bảng nhu cầu/chỗ học/bóng đổ.
5. Chạy native; chọn baseline/A/B/C, giờ, seed và khoảng SUMO/thời điểm SWMM.
6. Chạy **Độ nhạy + 3 seed**; xem từng case và cảnh báo độ ổn định.
7. Lưu job ID, mở lại; tải ZIP và xem nguồn/coverage. Muốn shortlist, chỉnh
   `options` trong JSON trước khi tạo study mới; không sửa kết quả đã lưu.

## 4. Case phần 3

Mẫu cộng dồn mặc định có các trạng thái chính. Để review đủ tám trạng thái
và hai thứ tự triển khai, mở nội dung một trong các file sau và dán vào
**Building plan, dữ liệu nền và giả định (JSON)**:

- `docs/samples/planning-portfolio-a-first.json`: A → AB → ABC.
- `docs/samples/planning-portfolio-b-first.json`: B → AB → ABC.

Chạy native; chọn phase 1/2/3 và các option. Review:

- AB/ABC giống nhau ở hai thứ tự vì cùng tập dự án active.
- B-first bổ sung chỗ học sớm; A-first bổ sung nhà ở sớm.
- Phase 3 vượt capacity điện/nước/nước thải của fixture synthetic.
- Marginal là chênh lệch giữa hai phase; interaction nằm trong phần audit JSON.
- Nút/cống SWMM có series, không phải bản đồ độ sâu ngập 2D trên mặt đất.

Có thể mở job đã chạy bằng ID trong
`test-results/planning-portfolio/portfolio-report.json` của máy local.
Job IDs thuộc store của máy đó; máy khác chạy lại input mẫu để tạo ID riêng.

## 5. Tái hiện kiểm thử

Python local dùng `.venv/Scripts/python.exe`; browser script dùng
`.runtime/ui-check/node_modules/playwright-core` và Edge. Nếu chưa có module:

```powershell
npm install --prefix .runtime/ui-check playwright-core
$env:PYTHONPATH='backend;etl'
.venv/Scripts/python.exe scripts/prepare-planning-study.py --output .runtime/planning-generated-samples
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8007 --sqlite-path .runtime/unused-for-external-worker.sqlite --external-worker --run-mode native --output test-results/planning-single-site
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8007 --sqlite-path .runtime/unused-for-external-worker.sqlite --external-worker --study-mode single_site --run-mode native --hours 18 --output test-results/planning-single-site/single
.venv/Scripts/python.exe scripts/test-planning-studies-local.py --api http://127.0.0.1:8007 --sqlite-path .runtime/unused-for-external-worker.sqlite --external-worker --run-mode uncertainty --hours 7 18 --output test-results/planning-single-site
.venv/Scripts/python.exe scripts/test-planning-portfolio-local.py --api http://127.0.0.1:8007
.venv/Scripts/python.exe scripts/test-planning-missing-local.py --api http://127.0.0.1:8007
.venv/Scripts/python.exe scripts/test-planning-series-local.py --api http://127.0.0.1:8007 --evidence test-results/planning-single-site
.venv/Scripts/python.exe scripts/test-planning-postgres-local.py --output test-results/planning-single-site
```

`--external-worker` dùng worker Docker hiện có; sqlite-path trong lệnh không
được dùng để tạo worker khác. Observation timeout phải kiểm tra chính job ID
đã tạo trước khi thử lại. Script portfolio lưu job ID sớm và có `--resume`
để đọc/kiểm tra lại hai job đã ghi, không enqueue thêm.

Regression planning + integrated:

```powershell
$env:PYTHONPATH='backend;etl'
$planningTests = @(Get-ChildItem backend/tests/test_planning_*.py | ForEach-Object FullName)
.venv/Scripts/python.exe -m pytest @planningTests backend/tests/test_integrated_simulation.py -q --junitxml=test-results/planning-final-regression.xml
```

Browser trên API/worker thật và các reports đã tạo:

```powershell
$env:PLANNING_API_URL='http://127.0.0.1:8007'
$env:PLANNING_EVIDENCE_DIR='test-results/planning-single-site'
$env:PLANNING_PORTFOLIO_EVIDENCE_DIR='test-results/planning-portfolio'
$env:PLANNING_MISSING_EVIDENCE_DIR='test-results/planning-unknown-comparison'
node scripts/test-planning-ui.cjs
```

Linux image check (script bind read-only, không mount source backend):

```powershell
docker run --rm --name planning-final-linux-check --mount "type=bind,source=$PWD/scripts/planning-linux-native-check.py,target=/check.py,readonly" -e PYTHONPATH=/app:/app/etl -e PLANNING_SQLITE_PATH=/tmp/planning-final/studies.sqlite -e SIMULATION_WORK_DIR=/tmp/planning-final/solvers planning-demo-backend:local python /check.py
```

Reports/runtime được gitignore. Xem phạm vi bằng chứng và các giới hạn trong
[audit](planning-completion-audit.md); số test không chứng minh độ chính xác
thực địa. Không cần GitHub Actions hoặc server để chạy demo local này.
