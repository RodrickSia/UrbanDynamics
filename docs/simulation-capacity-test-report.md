# Kết quả kiểm thử nền/capacity và độ nhạy — 13/10/2026

## Kết quả

- **27/27 test backend đạt**: nguồn thật giữ unknown; opt-in nền giả lập; capacity độc lập với plan; occupancy có hash và trừ một lần; capacity có thể vượt ngưỡng; độ nhạy giữ nguyên plan; hash context ổn định khi lưu/đọc nhiều trường.
- **HTTP/worker đạt**: ba parcel nguồn hệ thống 1959486, 1958467, 1958799 chạy Screening với reference + 6 ca độ nhạy; job lưu thành công. Native một parcel, hành lang giả lập, OD nền khai báo 200 xe/h và ba seed chạy thành công reference + 6 ca, có kết quả SUMO/SWMM.
- **4 nhóm UI đạt**, không có lỗi JavaScript: mở lại kết quả có nhãn nguồn; đổi capacity −20% hiển thị vượt ngưỡng; native có ba seed và bảng SUMO; chọn parcel → nhập plan → chọn gói nền → nạp study.
- `git diff --check` và kiểm tra cú pháp JavaScript đạt.

Một lỗi hash do thứ tự trường học đã được phát hiện qua worker, sửa bằng thứ tự canonical và thêm regression test. Case thất bại cũ được giữ để audit; case kiểm chứng là revision mới.

## Tái chạy

```powershell
node scripts/test-demo-capacity-local.cjs
node scripts/test-capacity-demo-http.cjs
node scripts/test-capacity-demo-ui.cjs
```

Các helper local mặc định dùng Python và Playwright ở checkout `UrbanDynamics` cùng cấp; cấu hình `SIMULATION_TEST_PYTHON` và `PLANNING_PLAYWRIGHT_MODULE` nếu đặt khác. HTTP/UI cần demo 8007 đang bật, snapshot đóng băng và ba parcel nêu trên đã cài. Không chạy helper cập nhật container trong khi có job đang chạy.

Chứng cứ local ở `test-results/demo-capacity/`: JUnit `regression.xml`, `pytest.log`, đầu vào và kết quả hai job, `http-execution.json`, `ui-report.json`, ảnh `screening-reference.png`, `capacity-minus20.png`, `native-three-seeds.png`. Artifact runtime không được commit.

## Phạm vi đã kiểm chứng

Kiểm chứng tính nhất quán, lưu job, solvers và luồng demo. Native smoke test dùng lưu lượng và mạng nhỏ để kiểm tra pipeline; không chứng minh độ chính xác của OD/capacity toàn thành phố, không hiệu chỉnh với quan trắc. Bộ độ nhạy thay từng nhóm, chưa kiểm tra mọi tổ hợp bất lợi. Chưa chạy workflow mới trên GitHub Actions hoặc deploy server.
