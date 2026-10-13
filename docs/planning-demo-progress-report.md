# Tiến độ demo nhiều khu đất và tác động cộng dồn

Ngày 11/10/2026. **Demo backend/preview local synthetic đã nghiệm thu**;
xem [audit cuối](planning-demo-final-audit.md) và
[runbook](planning-demo-local-runbook.md). Regression 110 passed, browser 16
nhóm, native portfolio/uncertainty/unknown và PostgreSQL/Linux/chunked API
đạt. Nội dung bên dưới là lịch sử theo mốc. Counting chưa tiếp tục; không
commit/push/deploy, chưa hiệu chỉnh dữ liệu thực địa hay tích hợp map chính.

## Đã triển khai và kiểm tra

Cập nhật handoff/recovery 0.14: [chuỗi phân trang và uncertainty hiện tại](planning-series-and-recovery-audit.md).
HTTP uncertainty hai bài toán đạt, browser 14 nhóm; chunked API so đúng series
native/uncertainty trong 8 trường hợp. Focused native/jobs 19 passed, recovery
cuối 12 passed và packaged Linux đạt. Không đổi phương trình; full regression
101 là lượt trước các bổ sung handoff này. Còn audit tổ hợp/thứ tự/end-to-end.

Mốc 0.14: [single-site cùng context](planning-single-site-common-context.md).
Regression 101 passed; native hai orchestration độc lập cùng context/state
đạt; PostgreSQL/cache và packaged Linux/native/cancel/worker đạt. HTTP native
so vị trí, cộng dồn và một project đạt; browser 13 nhóm đạt trên Docker 8007.
Preview thêm mẫu một khu đất; còn uncertainty phiên bản mới và audit đầy đủ.

Mốc 0.13: [runtime benchmark/preflight](planning-runtime-benchmarks.md).
Regression 97 passed; PostgreSQL/PostGIS hiện tại native/cache/benchmark
đạt; HTTP native hai case và browser 12 nhóm đạt trên Docker API 8007.
Preflight chỉ dùng mẫu phù hợp worker/model/engine/physics, loại lượt cache
khỏi catalog cold. Còn single-site common context và audit toàn bộ kế hoạch;
không suy uncertainty phiên bản hiện tại từ lượt native này.

Mốc 0.12: [hydrographs/current uncertainty](planning-hydrographs-and-current-uncertainty.md).
Regression 90 test, native hai catchment full pipeline, CLI uncertainty
36 SUMO/12 SWMM và HTTP uncertainty cả hai bài toán đạt. API Docker 8007
đã cập nhật; series có timeline/peak time và không ghép các grid lệch nhau.
HTTP native 0.12 và UI 13 nhóm đạt; browser mở lại uncertainty run hiện tại,
giữ option C_only khi đổi case và đọc đúng ba seed/cảnh báo.

Mốc 0.11: [program normalization và invariant](planning-program-normalization.md).
Regression planning/integrated 81 passed; 8 trạng thái screening và phase
đã kiểm tra, native đổi tên cả ba parcel đã sửa/đạt. ZIP có bảng chuẩn hóa.
Packaged Linux native/cache/interrupt và HTTP hai case trên Docker API 8007
đạt, sau khi bổ sung dependency backend cho router giá đất đang có.
Browser 12 nhóm đạt trên API Docker 8007, gồm bảng normalized 9/11 row và
ảnh panel đã được xem. Không suy ra native uncertainty 0.11 từ lượt UI này.

Mốc 0.10: [layer theo thời gian](planning-spatial-timeseries.md), queue SUMO
theo lane/edge và geometry/sample SWMM nodes/links. Regression 21 passed,
focused native 1 passed, HTTP native hai case passed và UI 12 nhóm trên
instance cổng 8006/store riêng. Có chọn seed 2027 và sample SWMM ngoài phạm
vi bị từ chối. Chưa package/uncertainty full model 0.10.

Mốc hiện tại 0.9: [adapter nền tổng vùng và retention](planning-background-snapshot.md).
Regression 68 test trước retention, background focused 5 test, UI 12 nhóm
đạt; retention + jobs 11 test đạt. Adapter tách contribution cung cấp tường
minh, không tự suy mọi nguồn chồng lặp. Giữ artifact đã tham chiếu vô thời
hạn; CLI dọn orphan opt-in và không chạy khi còn job active. Các mốc 0.8/0.7
bên dưới là lịch sử, không mô tả mọi tính năng còn thiếu ở code hiện tại.

Mốc mới nhất: [manifest nguồn và coverage](planning-source-manifest.md), model
0.8; regression 63 test, provenance focused 5 test, HTTP native cả hai case và
11 nhóm browser đạt. Native độ nhạy mới chạy 36 SUMO/12 SWMM, có manifest
theo case và cảnh báo ranking nhạy với giả định/seed. Docker image 0.8 đã
build/chạy native. Phạm vi và patch metadata cuối được ghi trong báo cáo nguồn.

Mốc mới: [ledger hiện trạng và di dời](planning-baseline-ledger.md), model 0.7.
Regression planning/integrated **59 passed**, 59,73 giây
(`test-results/planning-ledger-regression.xml`); browser **10 nhóm passed**.
Có mẫu rehousing, bảng tải trước/trừ/thêm/sau và CSV trong ZIP. Một test bổ
sung về default 36/36.0 nhận diện building giữ nguyên cũng đạt sau regression.
Ở mốc 0.7 background phải loại registered parcels; model 0.9 đã thêm adapter
explicit snapshot. Báo cáo lịch sử bên dưới ghi phạm vi lượt trước.

| Hạng mục | Bằng chứng/phạm vi |
|---|---|
| Study, context chung, equal-program, tổ hợp/giai đoạn | Test validation, khử trùng parcel, hash bất biến khi đổi thứ tự danh sách, phase reuse đúng trạng thái |
| Tải điện/nước/nước thải vùng chung | Cộng từng giờ rồi lấy max; capacity dùng một lần; unknown không kết luận đủ năng lực |
| SUMO chung nhiều project | Solver thật; background stream giữ nguyên; không route nền xuyên private access; bảo toàn xe đối chiếu trip XML với summary |
| SWMM chung lưu vực | Background subcatchment một lần, các branch cùng J0; continuity; interaction khác tổng các delta đơn; node/link timeseries |
| Chỗ học và tiếp cận | Max-flow/min-cost theo đường đi bộ synthetic; nhóm nhu cầu/capacity dùng một lần; không trộn giường bệnh thành chỗ học |
| Bóng đổ | Hợp nhất polygon, vùng nhận bóng cố định, loại geometry biên có diện tích 0; không gọi là nhiệt độ |
| So sánh/Pareto | Tiêu chí do input chọn; thiếu metric chặn ranking; trọng số công khai; case/seed/weight stability trong run độ nhạy |
| Độ nhạy và seed | Case giữ nguyên building plan; native thật 36 SUMO/12 SWMM, ba seed ghép cặp; tách dao động solver khỏi giả định input |
| Lưu run/API/worker/artifact | HTTP native cho cả hai bài toán, worker tiến trình riêng, idempotency, mở lại input/run, ZIP có solver input/output |
| Preview độc lập | 9 nhóm browser đạt: screening thật, layer theo option, native reload/phases, roads/nodes/shadow, ZIP, mobile, hủy/chạy tiếp native job bằng input đã lưu, đọc case/seed/stability run lịch sử và input đổi ẩn kết quả cũ/JSON lỗi |

Regression mốc physical parcel 0.6: **53 passed**, gồm planning và integrated single-site,
39,01 giây, một warning dependency TestClient. Bằng chứng:
`test-results/planning-demo-regression.xml`, model `planning-studies-0.6`.
Test bổ sung độ nhạy/capacity/artifacts trước đó:
4/4 đạt, `planning-uncertainty-focused.xml`. Đây là phạm vi bộ test đó, không phải
toàn bộ repo/ETL hoặc kiểm thử Linux/độ chính xác địa phương.

HTTP report: `test-results/planning-studies/http-native-report.json`.
Browser report/ảnh: `test-results/planning-studies/ui-report.json`,
`planning-desktop.png`, `planning-mobile.png`. Các file evidence/runtime bị
gitignore; chạy lại theo [handoff](planning-simulation-api-handoff.md).

## Case để thử

Mở `http://127.0.0.1:8005/simulation/planning` khi API/worker đã chạy:

1. Chọn **Cộng dồn A + trường B + C**, bấm **Nạp mẫu**.
2. Chọn **SUMO + SWMM**, bấm **Kiểm tra đầu vào**, rồi **Chạy và lưu**.
3. Xem `A_only`, `AB`, `ABC` và `phase_1/2/3`; lần lượt bật lớp trường, đường,
   nút SWMM và bóng đổ. Có thể mở lại bằng job ID và tải ZIP.

Fixture: A 600 cư dân, B trường 600 chỗ, C 450 cư dân, nền 1.200 cư dân.
Nhu cầu tuổi học minh họa 18%; nhóm nền 216 học sinh. Trường hiện hữu 230 chỗ,
40 chỗ reserved cho nhóm ngoài mô hình. A-only làm unmet tăng; thêm trường B
có thể giảm unmet. ABC có 405 học sinh trong các nhóm mô hình.

ABC tải điện khoảng 688,20 kW so capacity synthetic 500 kW, nước cấp 203,28
m³/ngày so 180, nước thải 149,01 m³/ngày so 130. Đây là case chủ động đặt gần
ngưỡng để kiểm tra capacity, không phải năng lực hạ tầng thật tại Thủ Đức.
Delay mọi xe có thể giảm do thêm chuyến ngắn: kiểm tra delay **xe nền** cùng
completion/backlog để diễn giải tác động lên người đang sử dụng mạng.

## Công việc tiếp theo và điều kiện xong

1. **Độ bền job đã có code và test:** retry dùng lại child hoàn chỉnh,
   timeout/cancel dừng cây tiến trình, recovery xác nhận worker local đã dừng,
   lease ngăn owner cũ ghi kết quả; cache kiểm tra context/engine/seed/checksum.
   Job partial không có full run để ranking. Bộ job 7/7 đạt trong lượt chạy
   riêng 16,58 giây và có trong regression 53 test. Browser retry đã đạt bằng
   API/worker thật; còn chính sách giữ artifact và vận hành recovery nâng cao.
2. **Lưu trữ và bàn giao:** đã kiểm tra PostgreSQL/PostGIS thật trong container
   riêng, cache 5/5 child ở lượt thứ hai; đã kiểm tra Linux/native/cancel/cache
   và worker entrypoint trong image backend với source mount. Bằng chứng:
   `postgres-report.json` và `linux-native-job-report.json` trong
   `test-results/planning-studies/`. Hai report này kiểm tra store/job trước
   thay đổi physical-parcel của model 0.6; không phải toàn bộ test Linux.
   Còn cần đủ source/unit/coverage của map, retention và bàn giao thống nhất.
3. **Audit toàn bộ kế hoạch:** ledger hiện hữu/thay thế/unknown/di dời và
   coverage nguồn; geometry/connector corner cases; kiểm tra regression và
   từng invariant trong mục 14–15 của kế hoạch. Các module chưa có phải được
   ghi rõ thay vì coi là 0 hoặc đổi phạm vi nghiệm thu.

### Lỗi đã sửa trong lượt audit physical parcel

Hai thiết kế loại trừ nhau trên cùng parcel nay dùng chung một cổng vật lý
SUMO và cùng ID branch SWMM. Stream xe dùng ID parcel nên đổi thiết kế không
làm đổi ngẫu nhiên giờ xuất phát ngoài ý muốn. Native test xác nhận hai thiết
kế giống nhau có cùng delay/queue/cohort/edge intervals và SWMM timeseries;
thêm thiết kế trùng không đổi kết quả so với study một parcel.

Các thiết kế cùng parcel cần cùng `gate_lanes` trong study mạng chung; đầu vào
xung đột bị từ chối, không tự thêm cổng/làn. Mô phỏng thay đổi cấu trúc mạng
là kịch bản mạng riêng chưa hỗ trợ. Run mới công bố phương pháp/thời gian/
giới hạn của metric và có `drainage_rows` trong marginal theo phase.

Do model đổi 0.5 → 0.6, tạo revision mới trước khi chạy input cũ. Run hoàn
chỉnh đã lưu vẫn đọc được; không dùng cache context 0.5 cho solver 0.6.

Chưa deploy server, chưa commit/push trong lượt triển khai này. Preview phục
vụ kiểm tra hợp đồng backend; frontend map của nhóm tiếp tục do thành viên
phụ trách tích hợp.

Đã có [demo độ nhạy và kiểm tra seed](planning-uncertainty-demo.md). Mẫu UI
có reference/low/high/lower_capacity; preflight báo số lượt solver. Bảng
Pareto theo trung bình case có thể giữ nguyên dù đổi theo seed, nên phải xem
cả cảnh báo ổn định tổng hợp.

Danh sách thiếu/đủ bằng chứng theo từng mục và invariant:
[audit nghiệm thu](planning-completion-audit.md). Hai HTTP native model 0.6
vừa chạy lại đạt, 40,93 giây; đây chưa phải hoàn thành mọi mục trong audit.
