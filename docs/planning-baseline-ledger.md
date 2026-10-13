# Ledger hiện trạng, thay thế và di dời

Model `planning-studies-0.7`, ngày 11/10/2026. Dữ liệu demo synthetic.

## Thử trên demo local

Mở `http://127.0.0.1:8005/simulation/planning`, chọn **Di dời 100 cư dân A
sang C**, **Nạp mẫu**, **Screening**, **Chạy và lưu**, sau đó chọn **Toàn danh
mục** (`ABC`). Dùng SUMO + SWMM để xem traffic/drainage trên cùng input.

- Nền ngoài parcel: 1.200 cư dân, tính một lần.
- A hiện hữu: 40 căn/100 cư dân; phương án A giải phóng nhà ở hiện hữu.
- C sau xây: 150 căn/300 cư dân, **đã bao gồm** 100 người từ A và 200 người
  từ ngoài vùng. B là trường 600 chỗ, người sử dụng trường không tính là cư dân.
- Vùng trước: 1.300 người; sau: 1.500 người; tăng ròng **200**.
- 100 di dời nội vùng không cộng thêm lần nữa vào residents/trips/utilities.

Chọn `A_only`: chưa đưa C vào vận hành, transfer A→C chưa active; ledger
cảnh báo **chưa rõ nơi đến của 100 cư dân**. Không tự đoán vị trí tiếp nhận.
Các phase là trạng thái vận hành giả định, không mô phỏng thời gian chuyển
nhà/thi công. Mẫu JSON: [planning-rehousing.json](samples/planning-rehousing.json).

## Hợp đồng đầu vào

`development` là **trạng thái hoàn chỉnh sau phát triển** trên parcel. Nếu giữ
công trình hiện hữu, đưa công trình đó vào development một lần, cùng các
công trình mới. Geometry/surfaces vẫn phải cân bằng. Không gửi chỉ tòa nhà
mới rồi kỳ vọng backend tự giữ mọi building baseline.

`resident_transfers` là metadata nguồn gốc/đích đến của người đã nằm trong
baseline và final building counts:

```json
{
  "id": "A_to_C",
  "from_project_id": "A",
  "to_project_id": "C",
  "residents": 100,
  "when_active_project_ids": ["A", "C"],
  "source": "Synthetic rehousing declaration; included in final C residents",
  "source_kind": "synthetic"
}
```

`null` ở origin/destination nghĩa là ngoài **study area**, không có nghĩa là
không biết. Hai đầu cùng null bị từ chối. Activation phải bao gồm các đầu
registered; transfer chỉ có hiệu lực khi mọi project trong điều kiện active.
ID/source và conditions nằm trong canonical input/hash.

Preflight/schema từ chối project không có, activation thiết kế cùng parcel
loại trừ nhau, origin occupancy unknown, tổng chuyển đi vượt số người có thể
chuyển hoặc tổng chuyển đến vượt số người trong thiết kế cuối. Các cư dân
giữ lại ở building không thay đổi không được sử dụng thêm làm nguồn/đích
cho transfer. Kiểm tra cả các conditional transfer có thể cùng kích hoạt.

Chưa suy ra di dời đến một nhóm background cụ thể, chuyển đổi OD nội bộ,
lịch chuyển nhà hoặc nguồn gốc từng household từ các total này. Khai báo
transfer không tự tạo project-to-project trips: SUMO vẫn external-OD-only.

## Hợp đồng kết quả

Mỗi `state.baseline_ledger` có:

- `parcels[]`: physical ID, project ID, zone, source/hash baseline, occupancy,
  building được giữ/loại hoặc cải tạo, load ledger và điện từng giờ.
- Mỗi load: `baseline`, `accounting_removed`, `replacement_added`, `final`,
  `delta`, `certainty`. Công thức: baseline − removed + added = final.
- `regional_loads`: nền vùng cộng parcel một lần cho điện/nước/nước thải.
- `population`: baseline/final/net delta, internal relocation, external
  inflow/outflow và `unexplained_net_change`.
- `active_resident_transfers`, `unresolved_existing_residents`, limitations.

Accounting removal là phép thay tải baseline bằng tải final, **không phải**
bằng chứng toàn bộ nhà bị phá. Building hoàn toàn không đổi được nhận diện
theo geometry/chương trình; tên và 36/36.0 không tạo khác biệt. Cải tạo có
thay thông số nằm trong nhóm remodeled; không suy ra khối lượng phá dỡ.

Không có snapshot, background đầu vào là phần **ngoài registered parcels**.
Model 0.9 có [adapter snapshot tổng vùng](planning-background-snapshot.md)
cho nguồn đã chứa parcel và cung cấp contribution rõ ràng. Backend tách một
lần rồi dùng nền sạch chung; không tự suy mọi nguồn chồng lặp hoặc gán tổng
vùng thành nền đã sạch.

Unknown occupancy được ghi `certainty=unknown`; số placeholder không chứng
minh thay đổi thực tế. `unexplained_net_change` không tự gọi là cư dân mới.

ZIP của run mới có `baseline-ledger.csv` theo case/option/phase/parcel/metric,
đơn vị, nguồn và certainty; result JSON chứa đầy đủ hourly ledger. Run cũ
không có ledger vẫn đọc được, UI ghi cần revision mới thay vì dựng số 0.

## Bằng chứng và phần còn lại

Regression planning/integrated vừa chạy: 59 passed, 59,73 giây,
`test-results/planning-ledger-regression.xml`. Có kiểm tra giữ building,
unknown occupancy, validation chuyển đi/đến, canonical hash, CSV qua API,
SUMO/SWMM thật trên case di dời và conservation. Browser 10 nhóm đạt, có
case rehousing và cảnh báo A_only; ảnh `planning-rehousing.png` đã được xem.
Smoke HTTP sau khi nạp lại API/worker bản cuối cũng đạt: model 0.7, before
1.300/after 1.500, net 200, internal relocation 100 và 150 dòng CSV có source/
unit. Report: `test-results/planning-studies/http-ledger-report.json`.

Đây là hoàn thiện ledger theo input được khai báo. Adapter background có
nguồn chồng lặp, coverage/manifest, retention và các invariant còn thiếu
tiếp tục nằm trong [audit](planning-completion-audit.md). Chưa nghiệm thu
toàn bộ kế hoạch; không tiếp tục object counting trong giai đoạn này.
