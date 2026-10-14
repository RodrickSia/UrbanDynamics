# Kiểm thử trước nộp: catalog QCVN và gộp parcel

Ngày: 14/10/2026. Model `planning-studies-0.19`.

## Backend và dữ liệu

- **209/209 test** đạt trong bộ simulation/counting, gồm 11 test mới cho nâng cấp lần này; thời gian Windows 317,16 giây. Có một cảnh báo deprecation của thư viện TestClient; không có test thất bại.
- Test nhóm liền kề tạo một project với số căn/cư dân/sàn nhập một lần; roof qua ranh được cắt theo union một lần; source review vẫn giữ cả hai thửa.
- Nhóm rời, chạm điểm dẫn đến MultiPolygon, chồng nguồn, ID thiếu/nhóm trùng và building vượt ranh bị từ chối; persisted group geometry được kiểm tra lại với snapshot.
- Test nội suy bảng chung cư tại điểm bảng/giữa bảng và biên; occupancy thiếu giữ minimum requirements unknown; capacity/demand vận hành không đổi khi chỉ bật catalog; hash context ổn định sau lưu/đọc lại.

## Case end-to-end có nguồn geometry

- Snapshot: `0e62caa68cf5d4a1c9941cd82d59b8d4a09a453170dd09726c322d252bea2fda`.
- Hai thửa thật: **1937203 + 1937204**, có chung cạnh và đủ điều kiện geometry demo; không suy từ đó rằng được phép xây chung cư.
- Một plan chung: **20 căn, 60 cư dân, 4 tầng, 1.600 m² sàn**. Gói occupancy/capacity **synthetic_capacity_v1**, catalog **qcvn_urban_2021**.
- Job Screening `0b3fb6c8-6125-4f15-b587-fb49502c0755`: succeeded.
- Job native `b70457f8-39f5-401e-8ba7-78ea5c35062c`: succeeded; network OSM, giờ 18, seed 2026/2027/2028; có SUMO và SWMM. OD nền 200 xe/h là override chuyển từ counting, không phải đo ở hai thửa này.
- Kết quả trước/sau giao thông có số trong cả ba seed; một state có một parcel-group/project, không nhân 20 căn hoặc 60 người với số thửa.

URL local mở lại:

- [Screening và QCVN](http://127.0.0.1:8007/simulation/planning?job=0b3fb6c8-6125-4f15-b587-fb49502c0755)
- [SUMO/SWMM ba seed](http://127.0.0.1:8007/simulation/planning?job=b70457f8-39f5-401e-8ba7-78ea5c35062c&view=sumo)

Job IDs thuộc runtime local, không tự có khi clone repo mới. Đầu vào và chứng cứ nằm tại `test-results/submission-features/` (không commit): `request.json`, `study.json`, `catalog.json`, preflight, kết quả job, JUnit `regression.xml`, `regression.log`, và manifest thực thi.

## Tái chạy

Kiểm thử giao diện **3/3 nhóm đạt**, không có lỗi JavaScript: panel QCVN và chuyển hiện trạng; native nhóm thửa có ba seed; chọn hai thửa → bật gộp → chuẩn bị một plan 20 căn/60 người. Ảnh kiểm chứng: `qcvn-requirements.png`, `grouped-native.png`; manifest `ui-report.json` trong cùng thư mục artifact. Đã xem ảnh panel QCVN để kiểm tra nội dung/bố cục.

```powershell
node scripts/test-simulation-regression-local.cjs
node scripts/test-submission-demo-http.cjs
node scripts/test-submission-demo-ui.cjs
```

Helper Windows dùng Python/Playwright từ checkout `UrbanDynamics` cùng cấp; có thể cấu hình `SIMULATION_TEST_PYTHON`, `PLANNING_PLAYWRIGHT_MODULE`, `PLANNING_DEMO_URL`. HTTP cần snapshot đã cài và demo/worker hoạt động. Script tự tìm cặp chung cạnh trong các parcel đủ phạm vi, không coi cặp đó là ứng viên đã được phê duyệt.

## Phạm vi chứng minh

Đã kiểm chứng logic, bảo toàn nguồn, lưu job và solver trong case cụ thể. Không kiểm chứng capacity thực, dự báo occupancy thực, quyền hợp thửa/xây dựng hoặc tổng GPMB. Catalog là đối chiếu tối thiểu, không chuyển hệ số vận hành/capacity còn giả lập thành pháp lý đã xác minh. Chưa nối React main hoặc triển khai server trong lần này.
