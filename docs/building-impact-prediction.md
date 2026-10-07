# Dự tính tác động → đánh giá → tạo gợi ý cải thiện

Phiên bản: `building-impact-2.0.0`, ngày 05/10/2026. Thay thế luồng nhập sẵn ba phương án.

## Luồng hiện tại

1. Vẽ khu đất và công trình dự định xây, nhập hiện trạng + thiết kế. Chưa nhập phương án cải thiện.
2. Nhập mưa, hệ số bề mặt, số tầng/người; hệ số nhu cầu giao thông/nước/điện và nguồn dữ liệu.
3. Nhập mục tiêu môi trường và công suất còn lại trước khi xây.
4. Bấm **Dự tính tác động và đánh giá**: xem thay đổi từng feature và mục tiêu đạt/chưa đạt.
5. Nhập ngân sách, giới hạn thay đổi và chi phí; bấm **Tìm và kiểm tra gợi ý cải thiện**.
6. Hệ thống sinh ứng viên, tính lại, loại ứng viên vượt ngân sách hoặc làm xấu chỉ số đã mô hình hóa; hiển thị tối đa ba gợi ý.
7. Chọn gợi ý để so sánh, mở lại qua link, xuất JSON hoặc in PDF.

Trang demo `/simulation` chạy cùng FastAPI. Frontend chính vẫn là scaffold. Ví dụ là **hình học, thiết kế, hệ số, công suất, mục tiêu và chi phí giả định**, chưa khảo sát hoặc xác nhận quyền xây dựng. Công năng có trường học, nhà ở, văn phòng, bệnh viện và loại khác; chọn hệ số đúng công năng.

## Các feature dự tính

| Feature | Công thức / dữ liệu |
|---|---|
| Bề mặt, đất xanh, mái + sân cứng | Geometry và diện tích thiết kế; chưa tự nhận diện ảnh vệ tinh |
| Dòng chảy sơ bộ | `rain_mm / 1000 × Σ(area_m2 × coefficient)` |
| Giữ nước / nước còn lại | `retained = min(gross_runoff, available_storage)`; `remaining = gross − retained` |
| Diện tích sàn ước tính | `roof_m2 × floors` |
| Chuyến xe giờ cao điểm | `users × person_trips_per_user_hour × private_vehicle_share / average_vehicle_occupancy` |
| Nước | `users × liters_per_user_day / 1000 × (1 − saving_fraction)` |
| Nước thải | `water_demand × wastewater_fraction` |
| Điện cao điểm | `users × peak_kw_per_user × (1 − saving_fraction)` |

Hệ số giao thông phải xác định khung giờ, lượt đi/về và loại phương tiện. Dùng chung hệ số trước/sau chỉ phù hợp nếu cơ sở nhu cầu tương thích; cần khảo sát thêm khi đổi công năng. Công suất do planner cung cấp, chưa được hệ thống đo hoặc suy ra từ OSM.

Diện tích tính trên ellipsoid WGS84, trừ lỗ polygon. Bốn bề mặt không chồng lấn phải khớp khu đất với sai số `max(0.1 m², 0.01%)`. Footprint phải trong khu đất và khớp mái. Giới hạn: 1–1.000.000 m², 500 đỉnh, 20 vòng, mỗi trục ≤0,1 độ.

## Đánh giá

- So sánh từng chỉ số: ít dòng chảy, nhiều đất xanh, ít bề mặt không thấm và ít áp lực nhu cầu được xem là cải thiện trong phạm vi này.
- Tổng hợp `better`, `worse`, `mixed`, `unchanged`; không kết luận công trình có nên được xây chỉ từ nhu cầu tăng. Lợi ích phục vụ mới và tính pháp lý chưa được mô hình hóa.
- Mục tiêu: mức tăng dòng chảy cho phép, đất xanh tối thiểu và mái+sân cứng tối đa. Đây là mục tiêu planner chọn, chưa phải tiêu chuẩn pháp lý.
- Công suất: so sánh **nhu cầu tăng thêm** `max(0, sau − trước)` với **phần còn trống trước khi xây**, tránh tính trùng nhu cầu hiện trạng.
- API có thể bỏ `demand` khi chưa có dữ liệu; không tự gán hệ số giả định hoặc kết luận quá tải. Giao diện yêu cầu nguồn và số liệu khi bật nhóm nhu cầu.

## Gợi ý tự động

Giữ nguyên **footprint, diện tích mái, số tầng và số người**. Tìm cách:

- Chuyển sân cứng sang đất xanh / sân thấm trong giới hạn và giữ tối thiểu phần sân cần thiết.
- Thêm giữ nước trong giới hạn.
- Giảm tỷ lệ xe cá nhân khi planner xác nhận khả năng chuyển phương tiện và khả năng tiếp nhận của phương tiện thay thế.
- Đặt chỉ tiêu tiết kiệm nước / giảm điện cao điểm trong hiệu quả giả định đã nhập.

Mỗi ứng viên được tính lại bằng cùng mô hình. Chi phí gồm bề mặt, giữ nước và vận hành, theo đơn giá người dùng nhập. Đơn giá vận hành tính theo mỗi **điểm phần trăm** thay đổi. API yêu cầu cung cấp rõ chi phí khi bật can thiệp, không tự lấy báo giá thị trường.

Xếp hạng: ít mục tiêu chưa đạt → ít thiếu hụt dòng chảy → chi phí thấp → đất xanh nhiều. Tìm kiếm hữu hạn theo bước 25% giới hạn bề mặt, các mức dung tích và mức vận hành cần để đạt công suất; chưa tối ưu toàn cục.

Gợi ý là thông số cần khảo sát, chưa phải bản vẽ bố trí cây/hồ, thiết bị hoặc bằng chứng hiệu quả thực tế. Không đủ ràng buộc thì báo `partial_improvement` và mục tiêu còn thiếu; không tìm được cải thiện thì báo `no_feasible_improvement`. Không tự tăng ngân sách hoặc giảm quy mô để ép kết quả tốt.

## API và lưu trữ

| API | Vai trò |
|---|---|
| `POST /api/v1/scenarios/site-area` | Đo GeoJSON Polygon |
| `POST /api/v1/scenarios/building/predict` | Nhận hai trạng thái, mục tiêu, giả định; tính/đánh giá/lưu |
| `POST /api/v1/scenarios/building/{uuid}/recommendations` | Nhận ràng buộc/chi phí; tạo gợi ý, tính lại/lưu |
| `GET /api/v1/scenarios/building/{uuid}` | Mở lại kết quả |

Luồng predict không nhận `mitigated`. API cũ `POST /scenarios/building` và `/scenarios/rain` được giữ, giao diện mới dùng `/building/predict`.

PostGIS: `building_scenario_runs`, site SRID 4326, JSONB, thời gian UTC, phiên bản và SHA256. Gợi ý có UUID mới, `parent_run_id`, constraints, phiên bản search và `recommendation_sha256`; bản ghi gốc giữ nguyên. Không có database thì JSON nguyên tử phục vụ local; database đã cấu hình nhưng lỗi trả 503, không fallback. Sai dữ liệu trả 422; không có bản ghi 404; gợi ý từ luồng cũ 409.

Tính đồng bộ vì module nhẹ. Chưa có worker/jobs hoặc AI Club/LLM integration: đề xuất hiện do tìm kiếm phương án và quy tắc tính toán. Đầu ra có số liệu/nguồn/giới hạn để AI diễn giải sau.

## Chạy local

```powershell
$env:POSTGRES_PASSWORD = ((Get-Content .runtime/khoi-local.env -Raw).Trim() -split '=', 2)[1]
& .venv/Scripts/python.exe scripts/test-khoi-local.py --linux-checks
npm install --prefix .runtime/ui-check --no-package-lock --no-save playwright-core
node scripts/test-building-ui.cjs
```

Mở `http://127.0.0.1:8001/simulation`, nạp ví dụ → kiểm tra/xác nhận → dự tính → tìm gợi ý. File password riêng trên máy đã setup, bị gitignore; người dùng mới tạo password riêng theo guide Khôi. Test UI cần Edge; có thể đổi `BUILDING_BROWSER_CHANNEL` và `BUILDING_API_URL`. Test tạo scenario giả định, chặn tile server; ảnh/report nằm trong `test-results/`.

## Giới hạn

Chưa dự báo độ sâu/vùng/thời gian ngập, ùn tắc/hàng chờ/thời gian đi lại, bóng đổ/nhiệt hoặc mô phỏng mạng hạ tầng. Hệ số và công suất chưa hiệu chỉnh với dữ liệu đo. Tiết kiệm nước không mô hình hóa tái sử dụng; giảm nước thải theo tỷ lệ là giả định. Cần lưu lượng/OD/tín hiệu giao thông, công suất đơn vị quản lý, địa hình/cống/mưa/triều và chiều cao/khí tượng trước khi nâng lên mô phỏng vật lý.
