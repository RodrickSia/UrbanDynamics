# Bàn giao deploy simulation lên máy 156

Máy 156 **chưa có GitHub self-hosted runner và `.env`**, theo xác nhận của người dùng ngày 07/10/2026. Chưa triển khai remote. Workflow được bàn giao để nhóm cấu hình và chạy sau.

## Chuẩn bị trên máy 156 (Linux)

1. Cài Docker Engine + Compose plugin; đủ dung lượng cho image SUMO và volume PostgreSQL/artifacts.
2. Trong repo GitHub → **Settings → Actions → Runners → New self-hosted runner**, chọn Linux và làm theo lệnh GitHub cấp. Token đăng ký chỉ dùng trên máy 156, không ghi vào repo.
3. Chạy runner bằng service, thêm nhãn **urban-156** và cho tài khoản runner quyền dùng Docker. Nhãn ngăn workflow chọn nhầm một runner Linux khác.
4. Chọn thư mục bền vững, ví dụ `/srv/urbandynamics`. Tạo `.env` ở đó, quyền hạn chế, không đưa lên Git. Điền `POSTGRES_PASSWORD` đủ mạnh và các biến thật cần dùng. Dùng URL-safe password hoặc cấu hình URL đã escape đúng nếu tự đặt `DATABASE_URL`.
5. Đưa dữ liệu cache có nguồn vào `/srv/urbandynamics/data`. Không có data cache vẫn chạy synthetic pilot, nhưng layers thực sẽ báo unavailable. PostgreSQL schema scenario được tạo lúc lưu run; warehouse layer migrations chạy lúc volume DB được tạo lần đầu.
6. Repo → **Actions → Deploy integrated simulation to 156 → Run workflow**; chọn branch/commit đã được review. Nhập deploy directory và cổng localhost. Workflow test native solvers/API trong CI trước khi job deploy bắt đầu; không cần chạy service “trên GitHub” để service mới hoạt động.

Workflow giữ `.env`, `data/` và volumes trên máy. `git archive` tạo source từ commit được chọn ở `.releases/<timestamp>-<SHA>`; mỗi release dùng symlink tới `.env`/data bền vững. Sau smoke đạt, symlink `current` trỏ tới release mới. Lệnh Compose dùng project cố định `urbandynamics-156`.

API bind **localhost**, mặc định 8001. Để frontend truy cập từ ngoài, cấu hình reverse proxy trên máy 156 trỏ API tới `127.0.0.1:8001` với cùng origin, TLS và timeout tối thiểu 240 giây cho simulation. Chưa có authentication/rate limit ngoài giới hạn 2 simulation requests đồng thời trong app; nhóm nên giữ mạng nội bộ trước khi public.

## Kiểm tra sau deploy

- `docker compose -p urbandynamics-156 -f compose.khoi.yaml ps` — warehouse/backend running.
- `/health` — process; `/ready` — layers nền (503 nếu chưa publish layer, không đồng nghĩa solver hỏng).
- `/simulation/integrated` — UI mới; `/api/v1/scenarios/integrated/presets` — mẫu.
- Workflow smoke chạy predict thực với SUMO/SWMM + lưu/mở PostGIS. Nếu không đạt, job báo failed. Không tuyên bố có rollback tự động; kiểm tra logs và dùng release trước để rebuild nếu cần.

## Backup và rollback

Backup **cả** named volume `khoi_database` của project deploy (run PostgreSQL/GeoJSON documents), `khoi_simulation_runtime` (input/output native), và `data/`. Lưu lượng artifact tăng mỗi lần predict/rerun; cần retention/backup trước khi sử dụng thường xuyên.

Rollback: `cd` tới release trước trong `.releases`, chạy `docker compose -p urbandynamics-156 -f compose.khoi.yaml up -d --build --wait warehouse backend` với cùng cổng, kiểm tra smoke rồi cập nhật symlink `current`. Không chạy `down -v`. Rollback code không đảo ngược dữ liệu đã append.
