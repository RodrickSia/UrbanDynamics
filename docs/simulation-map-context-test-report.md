# Kiểm thử tích hợp building hiện trạng từ map

Ngày 11/10/2026, Windows, Python trong `.venv`, model `integrated-building-1.3`.
Không commit/push hoặc deploy. Không sửa frontend trong hạng mục này.

## Kết quả

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ backend tại vòng kiểm tra trước bước hoàn thiện dedup | 136 đạt, 4 bỏ qua, 38,88 s |
| Map context + background, vòng cuối sau hoàn thiện dedup, giữ số tầng nguồn và nhãn baseline/design | 40/40 đạt, 12,38 s |
| HTTP trên API local + snapshot đã tải + map fixture | Đạt, 48,32 s |
| Predict → lưu/mở lại → recommendations → ZIP | Đạt; 3 gợi ý, ZIP 5.256.053 bytes; kiểm tra nội dung archive |
| Native SUMO/SWMM | Chạy engine thật; cân bằng số xe và kiểm tra balance SWMM đạt |
| Context công trình lân cận | Giữ nguyên giữa baseline, development và 3 gợi ý |

4 test bỏ qua cần PostGIS thật/chế độ integration được bật. Không chạy Docker/Linux ở vòng này. Pytest báo một cảnh báo deprecation của Starlette/httpx, không phải lỗi test.

## Các hành vi đã kiểm tra

- Nhận Polygon/MultiPolygon, giữ holes; cắt footprint qua ranh khu đất.
- Ghép fragment cùng ID, không tính lại footprint trùng; ưu tiên map trước OSM.
- Loại height fallback 12 m khi được đánh dấu; phân biệt height nguồn, height suy từ tầng và default 3 m.
- Giữ số tầng nguồn khi một bản duplicate khác bổ sung height; reject height/tầng nguồn mâu thuẫn.
- Coverage bbox không phủ site, thiếu timezone, geometry sai, quá 200 features, URL ngoài schema, synthetic + map_context trả 422.
- Baseline do người dùng cung cấp được ưu tiên, không bắt nó qua giới hạn 20 parts của baseline tự dựng.
- Preflight không chạy native solver. Hash phản ánh thay đổi chiều cao công trình lân cận.
- Công trình lân cận thực sự làm đổi shade trong site; occupancy hiện trạng chưa có vẫn ghi unknown/0.
- API lưu/mở lại và recommendations giữ context; maps baseline có provenance, maps development có nhãn design.

## Case HTTP với snapshot

- Input map: [sample](samples/simulation-map-context.json), **building fixture giả lập, chưa tải Goong thật**.
- Snapshot ID: `64334deff008126baf2d91c8c57197d9822a76eaf667a6a66edf7414b1e112a8`, gồm API nhóm, OSM và WorldCover đã tải ở bước trước.
- Run: `e3a30205-7db0-49b4-9741-54447cf77960`.
- Recommendations run: `a6cce684-9b11-4ebc-9cdf-832fa42d44b0`.
- 1 building baseline trong site, 10 phần footprint công trình lân cận (map fixture + OSM).
- Shade trung bình ngoài trời: baseline 17,16%; development 22,39% trên 10 mốc giờ. Đây là kết quả mô hình hình học của case, không phải quan trắc hoặc nhiệt độ.
- Mạng SUMO dùng snapshot OSM; OD/luồng nền chưa hiệu chỉnh từ counts thực tế.

## Chạy lại

```powershell
$env:PYTHONPATH = 'backend;etl'
.\.venv\Scripts\python.exe -m pytest backend/tests/test_simulation_map_context.py backend/tests/test_simulation_background.py -q --junitxml=test-results/simulation-map-context-focused.xml
```

Khi API chạy tại port 8003 và đã có snapshot tương ứng:

```powershell
.\.venv\Scripts\python.exe scripts/test-simulation-map-context-local.py --snapshot-id 64334deff008126baf2d91c8c57197d9822a76eaf667a6a66edf7414b1e112a8
```

Bỏ `--snapshot-id` để chạy sample với cơ chế `auto`; nếu có snapshot local phù hợp, backend vẫn có thể chọn nó.

Evidence local (gitignored):

- `test-results/simulation-map-context-backend.xml`
- `test-results/simulation-map-context-focused.xml`
- `test-results/simulation-map-context-local-report.json`
- `test-results/map-context-demo.json`, `map-context-recommendations.json`, `map-context-demo.zip`

API đang mở tại `http://127.0.0.1:8003/api/v1/docs`. Hợp đồng cho frontend: [simulation-map-context-handoff.md](simulation-map-context-handoff.md).

## Phần còn lại

Frontend cần gửi raw source building DTO khi người dùng chạy simulation. Backend không tự tải Goong; bài kiểm tra này không chứng minh tile thật có đủ footprint/height. Công trình chưa có trong nguồn, occupancy, địa hình, mạng cống và capacities vẫn thiếu hoặc giả định có nhãn. Chưa có kiểm chứng độ chính xác tác động bằng dữ liệu quan trắc địa phương.
