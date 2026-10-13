# Nguồn và phạm vi dữ liệu của demo planning

Ngày 11/10/2026; model `planning-studies-0.8`. Đây là coverage của **mô hình
synthetic**, không phải chứng nhận độ phủ dữ liệu thực tại Thủ Đức.

## Đã bổ sung

`context.source_manifest` gồm 13 nhóm nguồn: parcel, baseline, development,
hệ số nhu cầu, dân số/di dời, mạng SUMO, traffic nền, trận mưa, graph thoát nước,
utility zones, trường/nhóm học sinh, mạng đi bộ và geometry mặt trời.

Mỗi entry có ID, version, payload SHA-256, source kind, phạm vi, note và
time basis. `observed_at=null`: hệ thống không tự tạo thời điểm quan trắc.
Source kind do người nhập khai báo cho baseline/capacity được giữ riêng;
không nâng cả study synthetic thành dữ liệu quan trắc đã kiểm chứng.

Manifest có ID/hash, nằm trong context hash và được đóng băng theo revision.
Thay công suất, mưa, nguồn hoặc thiết kế thay input/context tương ứng; một
run đã lưu không fetch lại dữ liệu khi đổi tab. Input/source hash giữ nguyên
khi đảo thứ tự collection hoặc serialize/reload cùng input.

## Phạm vi từng module

| Module | Phạm vi mô hình đã công bố | Giới hạn |
|---|---|---|
| Geometry | Union registered parcels, inventory baseline/development | Không suy ra inventory hàng xóm ngoài parcel |
| Traffic | Toàn corridor tổng hợp, private accesses và biên west/east | Không phải mạng TP.HCM/OD thực; nếu vượt AOI, preflight cảnh báo và công bố boundary riêng |
| School | Mọi location, connector và spine tổng hợp | Không có vỉa hè/tuyển sinh kiểm chứng; thiếu nhu cầu nền/capacity được ghi rõ |
| Drainage | Catchment bindings, graph tổng hợp và diện tích nền khai báo | Diện tích lưu vực nền chưa có polygon khảo sát, không có ngập 2D/tide boundary |
| Utilities | ID zone, background profiles và capacity dùng chung | Chưa có ranh vùng phục vụ, voltage/pressure/network-flow model |
| Shadow | Vùng nhận bóng cố định trong AOI | Geometry đã khai báo, không phải nhiệt độ/ánh sáng cửa sổ hoặc cảnh quan đầy đủ |

Mạng đường dùng **một factory** `network.specification()` cho cả manifest và
file node/edge/routes của netconvert. Test đối chiếu file edge XML thực với
specification; coverage giao thông chứa các edge đã công bố. Coverage đi bộ
được lập từ các vertex WGS84 thực để tránh cắt tuyến khi đổi hệ tọa độ.

Random stream dự án dùng hash hình học parcel và loại xe, tách khỏi tên
project. Native test đổi tên một project giữ nguyên các metric kiểm tra;
cohort parser dùng identity đầy đủ, không dùng prefix khiến ID chứa `__`
bị đếm vào hai nhóm. Không coi test một parcel là bằng chứng mọi trường hợp
rename/multi-site đã được nghiệm thu.

## Bàn giao map và artifact

Layer API có `source_manifest_id`, `module_coverage`, `units`.
Mỗi feature có `source_object_id`, engine, source IDs, đơn vị, coverage status,
cùng study/run/option/phase/context/time đã có. Missing edge sample được ghi
`no_reported_sample`, không biến thành lưu lượng/tốc độ 0.

Các dòng comparison screening/native có manifest/source IDs bên cạnh
method/time/unit/scope/limitations. ZIP có `source-manifest.json`; run độ nhạy
có manifest riêng trong `cases/{id}/`. `comparison.csv` cũng xuất các trường
nguồn/phương pháp/thời gian/giới hạn. Run cũ thiếu manifest có trạng thái
legacy rõ ràng; frontend không tự dựng nguồn hoặc coverage đã biết.

Trong preview `/simulation/planning`, mở **Nguồn dữ liệu và phạm vi từng tác
động** để xem bảng giới hạn. Đây là preview bàn giao backend; frontend của
nhóm tiếp tục dùng map chung và layer API.

## Bằng chứng local

- Regression planning/integrated: **63 passed**, 71,26 giây,
  `test-results/planning-source-regression.xml`.
- Bộ provenance mới nhất: **5 passed**, 13,74 giây,
  `test-results/planning-provenance.xml`; có thêm cohort namespace/CSV sau
  regression. Test chống alias khi consumer sửa metadata map cũng đạt riêng
  (`planning-source-map-isolation.xml`).
- Hai HTTP native case: **passed**, 48,52 giây,
  `test-results/planning-studies/http-native-report.json`, model 0.8.
- Native uncertainty 0.8: **36 SUMO/12 SWMM**, 61,47 giây; manifest riêng mỗi
  case; `uncertainty-native-report.json`. Kết luận nhạy theo giả định và seed,
  không có một vị trí thắng ổn định. Spread không phải confidence interval.
- Browser: **11 nhóm passed**, `ui-report.json`, có nguồn/coverage và đọc lại
  uncertainty run lịch sử. Native uncertainty mới ở trên là lượt CLI riêng.
- Docker image 0.8 đã build; packaged image chạy solver thật, cache 5/5,
  cancel/timeout và worker entrypoint đạt (`packaged-image-native-report.json`).
  Image được kiểm tra trước patch defensive copy metadata; patch đó có test
  isolation riêng, không thay input hay metric mô phỏng.

Các report nằm trong `test-results/planning-studies/` trừ JUnit ghi ở trên;
runtime/evidence bị gitignore. Không suy ra toàn bộ repo hoặc tính đúng tại
địa phương từ các lượt test này. Lệnh tái hiện nằm trong
[handoff](planning-simulation-api-handoff.md).

## Còn phải hoàn thiện

Model 0.9 đã bổ sung [adapter explicit snapshot và retention](planning-background-snapshot.md);
nguồn snapshot thứ 14 chỉ xuất hiện khi input có snapshot. Không tự suy
contribution thiếu hoặc nhận mọi nguồn chồng lặp. Còn timeseries queue/layer đầy đủ, invariant/corner
cases và audit end-to-end cuối cùng. Không cần quay lại counting để hoàn thiện
chức năng synthetic hiện tại; xem [audit](planning-completion-audit.md).
