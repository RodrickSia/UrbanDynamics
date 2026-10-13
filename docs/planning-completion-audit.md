# Audit nghiệm thu demo planning

Ngày 11/10/2026; model `planning-studies-0.14`.
**Audit hiện tại:** [nghiệm thu đầy đủ demo local](planning-demo-final-audit.md),
đối chiếu mọi mục và 13 invariant; [runbook](planning-demo-local-runbook.md).
Nội dung bên dưới là lịch sử audit theo mốc, giữ các khoảng trống đã ghi lúc
đó để truy vết; không coi danh sách còn lại ở mốc cũ là trạng thái hiện tại.
Dữ liệu synthetic theo yêu cầu; counting vẫn hoãn. Không commit/push/deploy.

## Bằng chứng đã quan sát

- Mốc portfolio 0.14: `scripts/test-planning-portfolio-local.py` chạy đủ tám
  trạng thái native, ba seed/giờ 18h và hai thứ tự A→AB→ABC/B→AB→ABC; cùng
  trạng thái ở hai thứ tự có cùng vật lý, marginal/interaction được đối chiếu.
  Báo cáo cuối `test-results/planning-portfolio/portfolio-report.json` là lượt
  đọc lại cùng hai job để xác nhận phân tích capacity đã sửa, không phải chạy
  solver mới. ABC vượt capacity điện/nước/nước thải ở phase 3 cả hai thứ tự;
  các capacity đều synthetic. Regression đầy đủ 108 passed, browser 15 nhóm.
  Sau đó chỉnh comparison occupancy unknown sang null và giữ giả định riêng:
  30 focused passed, live API/worker passed tại
  `test-results/planning-unknown-comparison/http-report.json`. Không suy rằng
  full regression/browser đã chạy lại sau chỉnh null. Docker local 8007 đã
  dùng image mới; run cũ giữ nguyên. Còn chốt audit toàn bộ và gói bàn giao.

- Handoff/guard 0.14: [chunked series, recovery và độ nhạy](planning-series-and-recovery-audit.md).
  HTTP uncertainty hai bài toán đạt, child 72/108 SUMO và 12/18 SWMM; browser
  14 nhóm đạt. API chunked khớp tám native/case results, provenance/units và
  missing không thành 0; 19 focused passed, final recovery 12 passed và image
  Linux native/cancel/cache/worker đạt. Không đổi vật lý; full regression 101
  trước bổ sung handoff. Còn audit tổ hợp/thứ tự triển khai và hợp đồng đầy đủ.

- Mốc 0.14: [single-site cùng context](planning-single-site-common-context.md),
  refactor bộ tính trạng thái và native dùng chung; hai orchestration native
  độc lập cho cùng kết quả trên fixture cùng context. Regression 101 passed;
  PostgreSQL/cache, packaged Linux/native/cancel/worker, HTTP ba case và
  browser 13 nhóm đạt. Chưa có native uncertainty 0.14. API integrated legacy
  site-only không được coi bằng luồng mới; handoff dùng shared study cho cả
  phần 1/2/3. Còn audit đầy đủ/corner cases và các gate còn thiếu.

- Mốc 0.13: [benchmark/preflight](planning-runtime-benchmarks.md), regression
  97 passed; PostgreSQL/PostGIS với native và cache thật đạt; HTTP native cả
  hai case, browser 12 nhóm và focused timing UI đạt trên Docker local 8007.
  Số đo theo đúng profile; không dùng cached/mixed run để hạ cold ETA. Chưa
  kiểm tra native uncertainty 0.13 hoặc single-site equivalence cùng context.

- Mốc 0.12: [hydrograph và uncertainty](planning-hydrographs-and-current-uncertainty.md),
  regression 90 passed; native hai catchment full pipeline 1 passed; CLI
  uncertainty 36 SUMO/12 SWMM và HTTP uncertainty cả hai bài toán đã đạt.
  HTTP native hiện tại và UI 13 nhóm cũng đạt, gồm reload/case/seed uncertainty.
  Grid shifted/different step, duplicate IDs và invalid values bị từ chối.
  Còn single-site common context, benchmark/preflight và current PostgreSQL.

- Mốc 0.11: [normalization và invariant](planning-program-normalization.md),
  regression 81 passed, focused final 2 passed. Đủ 8 tập screening; rename
  ba parcel giữ native metrics trong tolerance 1e-6 sau sửa solver identity.
  Packaged Linux + HTTP native cả hai case đạt trên Docker image hiện tại;
  UI 12 nhóm đạt, panel normalized đã xem; còn native uncertainty/current
  PostgreSQL và audit end-to-end toàn phạm vi.

- Mốc 0.10: [layer theo thời gian](planning-spatial-timeseries.md), regression
  21 passed, focused native 1 passed; HTTP native cả hai case và UI 12 nhóm
  trên cổng 8006. Queue/lane mapping được đối chiếu XML, SWMM sample khớp
  solver output; chưa suy ra package hoặc uncertainty toàn model hiện tại.

- Mốc 0.9: [adapter snapshot và retention](planning-background-snapshot.md),
  regression 68 passed, background focused 5 passed, UI 12 nhóm passed,
  retention/jobs 11 passed. Adapter explicit contributions và orphan GC đã
  có, còn kiểm chứng hợp đồng nguồn nhóm, corner cases và package hiện tại.
  Các mục chi tiết dùng bằng chứng 0.8/0.7 bên dưới cần đọc cùng cập nhật này.

- Mốc source/coverage 0.8: regression 63 passed, provenance focused 5 passed,
  HTTP native cả hai case passed, 11 nhóm UI passed, native uncertainty
  36 SUMO/12 SWMM passed và Docker packaged native/cache/interrupt passed.
  Có focused metadata isolation sau các gate đó; xem phạm vi/thời gian/
  artifact trong [báo cáo nguồn](planning-source-manifest.md).

- Mốc ledger 0.7: regression 59 passed, 59,73 giây,
  `test-results/planning-ledger-regression.xml`; browser 10 nhóm passed,
  có case rehousing và cảnh báo nơi đến unknown. Có native transfer test và
  API ZIP CSV ledger test. Sau đó một focused test default height 36/36.0 đạt.
  Chi tiết: [ledger](planning-baseline-ledger.md). Các lượt bên dưới là lịch sử.

- Regression planning + integrated: 53 passed, 39,01 giây,
  `test-results/planning-demo-regression.xml`.
- HTTP native model 0.6: site-selection và cumulative đều passed, 40,93 giây;
  `test-results/planning-studies/http-native-report.json`. Có API thật, worker
  riêng, SUMO/SWMM, idempotency, immutable input/result và ZIP.
- Browser: 9 nhóm passed, `test-results/planning-studies/ui-report.json`.
  Retry job bị hủy chạy lại native bằng input đã lưu. Độ nhạy trên browser
  kiểm tra đọc lại run lịch sử; không phải lượt chạy native uncertainty mới
  của model 0.6. Đã xem ảnh desktop; script kiểm tra mobile không tràn ngang.
- PostgreSQL/PostGIS: script local có solver thật, 5 child tính mới và 5 cache
  hits ở job sau; Linux image/source mount kiểm tra native/cache/interrupt và
  worker entrypoint. Report ở cùng thư mục trên. Đây là lượt store/job trước
  chỉnh physical parcel 0.6, không phải chứng minh toàn bộ model mới trên Linux.

File bằng chứng/runtime bị gitignore. Dùng các script trong handoff để tái
hiện; số test không thay thế việc xét phạm vi từng yêu cầu.

## Đối chiếu các mục kế hoạch

| Mục | Bằng chứng hoặc hiện trạng | Còn phải làm/kiểm chứng |
|---|---|---|
| 1. Single-site | 0.14 shared single-site qua integrated engine/worker; độc lập native same context, topology và state; regression 101 tests | Kiểm chứng thêm corner cases; frontend dùng contract shared study, API legacy không tự chuyển dữ liệu nền |
| 2–3. Hai bài toán, giới hạn pilot | Hai fixture/API native; giới hạn schema/workload; benchmark 0.13 theo profile và PostgreSQL 0.14 | Audit giới hạn/phạm vi mạng và cấu hình worker; không ngoại suy ETA cho physics khác |
| 4–5. Luồng map, input/nền | Preview và API layer/option/phase; bộ input synthetic | Adapter dữ liệu map của nhóm và hợp đồng dữ liệu nền đầy đủ; không xây frontend map chính |
| 6. Frozen context | Canonical hash/revision/idempotency; manifest/coverage; adapter explicit snapshot 0.9 | Kiểm chứng hợp đồng contribution nguồn nhóm, không tự suy mọi nguồn chồng lặp |
| 7. So vị trí | Equal-program, native ghép seed/Pareto; declared program và normalized ratios 0.11, mixed/zero/unknown tests + ZIP | Rà nguồn/coverage của mọi metric và giới hạn tổng/đơn vị phục vụ |
| 8.1. Ledger/interaction | Ledger, transfer, CSV/native và adapter nền tổng vùng 0.9 | Hợp đồng contribution nguồn nhóm và di dời vào background location cụ thể |
| 8.2. Traffic | Mạng chung/background/no private shortcuts/shared physical access; source/XML/namespace tests; queue lane/edge và selector giờ/seed/interval 0.10 | Corner cases nhiều project/vùng mạng và ledger OD nội bộ |
| 8.3. Drainage | SWMM chung/continuity/node-link/time; cùng grid bắt buộc, lệch/trùng peak và hai catchment full native 0.12 | Rà đủ coverage/binding/source theo hợp đồng và corner cases còn lại |
| 8.4. Utilities | Peak của tổng profile, capacity một lần, unknown không approve | Ledger chi tiết và nhất quán background dân số/utility/OD/dịch vụ |
| 8.5. Services | Shared school max-flow/min-cost, unknown và residual reassignment tests | Y tế/công viên có trạng thái unavailable; schema riêng chỉ thêm nếu mở rộng scope, không giả đang có |
| 8.6. Spatial | Union shadow, fixed receivers, loại diện tích 0, baseline removal tests | Geometry/overlap corner cases và metadata nguồn/đơn vị của từng feature |
| 9. Contract | Study/result/router/map package đã có | Rà mỗi trường provenance/coverage/assumption/runtime/child IDs và tương thích run cũ |
| 10. Jobs/storage | Test partial retry/cache/lease/process tree; PostgreSQL thật; UI retry; retention 0.9 opt-in giữ mọi artifact tham chiếu | Recovery khi nguồn/process không xác minh được, package image hiện tại và audit vận hành |
| 11. Uncertainty | CLI 0.12 36 SUMO/12 SWMM, HTTP hai bài toán/ZIP, UI case/seed/reload; sources theo case | Rà đầy đủ phương pháp/hợp đồng, không gọi spread là confidence interval |
| 12–13. Package/mốc | Code tách planning; dùng lại integrated demand/geometry/library | Theo dõi M0–M5 bằng bằng chứng, không ghi xong dựa vào tồn tại file |
| 14. Tests | Đối chiếu chi tiết bên dưới | Bổ sung các invariant chưa đủ phạm vi |
| 15. Bàn giao/demo | Hai HTTP native fixtures + ZIP + 9 nhóm UI; synthetic được ghi rõ | Audit artifact/method/map đầy đủ, retention, hướng dẫn tái hiện và chốt case interaction có kết luận đúng |
| 16. Kế hoạch thực hiện | Mốc N1–N4/M0–M5 đã ghi | Đây là kế hoạch, không phải evidence completion |

## Đối chiếu 13 invariant ở mục 14

1. **Có test trong fixture:** screening không đổi thứ tự; native same-parcel
   và đổi tên/đảo thứ tự cả ba parcel giữ số liệu vật lý. SUMO ID dựa geometry,
   không còn dựa tên project. Không suy từ đó sang mọi topology chưa kiểm tra.
2. **Có test:** equal-program giảm units và geometry ngoài region bị từ chối.
3. **Một phần:** điều kiện nằm trong context hash, SUMO pairs chung giờ/seed;
   chưa đủ coverage manifest kiểm tra phạm vi ảnh hưởng từng module.
4. **Một phần:** same-parcel dedup và shadow loại công trình bị thay thế; chưa
   đủ ledger nguồn chồng lặp và giữ/phá/di dời chi tiết.
5. **Có test:** hai peak khác giờ, capacity dùng chung và unknown status.
6. **Có test:** shared school allocation, reserved/background một lần và
   residual reassignment. Không áp dụng bằng chứng này cho y tế/công viên.
7. **Một phần:** SUMO conservation, private-route restriction và background
   stream tests; còn gate/ID/boundary/routing corner cases.
8. **Có test cốt lõi:** continuity/background/interaction; peak lệch/trùng,
   grid mismatch và missing binding; hai catchment full native kiểm tra wiring
   và sum đúng timestamp. Không suy sang mô hình ngập mặt đất hay mọi graph.
9. **Có test cốt lõi:** same-parcel và shared integrated single-site 0.14
   native cùng context/boundary; đủ 8 tập của ba project có screening test.
   Legacy site-only không tự chuyển sang nền chung. Còn case end-to-end các
   tổ hợp/thứ tự triển khai để đối chiếu demo mục 16.7 đầy đủ.
10. **Có test:** AB/ABC phase bằng option và demand không cộng phase trước.
11. **Có test:** unknown capacity/occupancy, synthetic labels, incomplete-trip
    bias và missing metrics chặn ranking; còn rà metadata mọi layer.
12. **Có test cốt lõi:** real child timeout/cancel/orphan cleanup, live owner
    không bị chiếm vì heartbeat cũ, partial retry, lease fencing, checksum
    tampering và cache context change; retention orphan có test, recovery giữ
    malformed owner/descendant và packaged native 0.14 có bằng chứng. Còn
    đối chiếu vận hành cuối và ghi đúng giới hạn host không xác minh được.
13. **Có bằng chứng trong phạm vi:** integrated regression, native planning
    và HTTP/browser thật. Không suy ra toàn repo hoặc độ chính xác địa phương.

## Thứ tự xử lý tiếp

1. Ledger/displacement và adapter explicit snapshot đã có code/test. Còn
   đối chiếu nguồn nhóm và location cụ thể của transfer vào background;
   không tự làm sạch mọi nguồn thiếu contribution.
2. Manifest/coverage/module method và metadata map/CSV đã có ở model 0.8;
   còn rà mọi source/metric invariant và timeseries selectors đầy đủ.
3. Retention đã có policy/CLI/test; còn gói chạy local/Docker hiện tại nhất
   quán và audit vận hành, không xóa artifact được run/cache/job tham chiếu.
4. Invariant/corner cases còn thiếu, native uncertainty model hiện tại, audit
   end-to-end cuối cùng. Chỉ ghi hoàn thành sau khi từng yêu cầu có evidence.
