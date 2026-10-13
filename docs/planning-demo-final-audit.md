# Nghiệm thu demo planning — đối chiếu phạm vi đầy đủ

Ngày 11/10/2026. Model `planning-studies-0.14`. Phạm vi nghiệm thu là demo
backend/preview local của `urban-planning-multisite-cumulative-plan.md`,
dùng dữ liệu synthetic theo yêu cầu. Frontend map chính, hiệu chỉnh dữ liệu
địa phương, counting, AI giải thích và deploy là các mốc sau đã xác định trong
kế hoạch; không coi chúng là tính năng đã triển khai.

## 1. Bằng chứng bản hiện tại

| Gate | Bằng chứng authoritative trong workspace | Phạm vi |
|---|---|---|
| Regression | `test-results/planning-final-regression.xml`: 110 passed, 171,74 s | Toàn bộ `test_planning_*.py` và `test_integrated_simulation.py`, Windows; có solver thật |
| Native portfolio | `test-results/planning-portfolio/portfolio-report.json`: passed | Đủ tám state, hai thứ tự, ba seed/18h, marginal/interaction/ZIP và idempotency |
| Unknown | `test-results/planning-unknown-comparison/http-report.json`: passed | Live screening/native, API + worker, comparison/interaction null, ranking bị chặn, ZIP/CSV |
| Native uncertainty | `test-results/planning-single-site/http-uncertainty-report.json`: passed, 63,74 s | Cả site-selection/cumulative, reference/low/high, 7h/18h, ba seed, case inputs/ZIP/immutable result |
| PostgreSQL/PostGIS | `test-results/planning-single-site/postgres-report.json`: passed, 18,99 s | PostGIS 3.5.2, native, năm cold child/năm cache hits, idempotency/revision/cancel/retry/benchmark |
| Linux image | `test-results/planning-single-site/final-linux-native-report.json`: passed, 7,57 s | Native/cache/source/queue/link, cancel/timeout và worker entrypoint; không phải toàn suite Windows trên Linux |
| Browser | `test-results/planning-single-site/ui-report.json`: passed, 16 nhóm | Browser thật trên API/worker, current uncertainty/portfolio/unknown restore, layers và mobile |
| Chunked API | `test-results/planning-single-site/http-series-report.json`: passed, tám documents | Native + current uncertainty, chunks đầy đủ, units/source/selectors và immutable saved run |

Các lượt live có thể dùng lại child solver đã lưu khi context/engine/checksum
khớp. Không gọi thời gian đó là cold benchmark. Regression, Postgres và Linux
check chạy native độc lập trong store/workdir riêng. Unknown/interaction guard
không đổi physics; result mới có thêm comparability theo metric và null khi
constituent không đủ điều kiện. Run lịch sử giữ nguyên, không sửa ngược JSON.

Uncertainty jobs hiện tại có 72 SUMO/12 SWMM/3 network child cho site-selection
và 108 SUMO/18 SWMM/3 network child cho cumulative; trạng thái child đều
succeeded. Đây là số child được kiểm chứng, không khẳng định tất cả chạy cold.

## 2. Đối chiếu mọi mục của kế hoạch

| Mục kế hoạch | Requirement cụ thể | Code và bằng chứng |
|---|---|---|
| 1 | Single-site giữ hoạt động; cùng nền khi mở rộng | `integrated.engine.predict_shared_study`, endpoint single-site; `test_planning_single_site.py` đối chiếu hai orchestration native độc lập, full state và topology; HTTP single-site và browser restore |
| 2 | Vị trí thay thế khác danh mục cùng tồn tại | Schema `mode`, active sets, equal/declared programs; API native/uncertainty cả hai mode; portfolio tám state |
| 3 | Pilot/workload có giới hạn; không hứa realtime | Schema tối đa 6 projects/12 options/4 phases/6 catchments/25 km²/4 hours/5 seeds; corridor tối đa 26 directed edges theo builder; preflight solver counts và benchmark đúng profile, unavailable khi chưa có mẫu |
| 4 | Chọn plan, screening/shortlist/native, layer, lưu/revision | JSON preview và router; option subset được khai báo trong study/revision; UI mode/restore/layer/time/cancel/retry; map chính tích hợp theo handoff |
| 5 | User nhập plan, hệ thống cung cấp nền/hệ số có nhãn | Presets và coefficient library; context/source manifest; unknown guard; chưa đưa camera vào counts |
| 6 | Frozen baseline/context, dedup, coverage, hai policies | `context.py`, `background.py`, `models.py`, `provenance.py`; background stale/missing/overcount/coverage bị reject; canonical reload/order/hash tests; snapshot mới tạo revision |
| 7.1 | Screening geometry/demand/access | `engine.evaluate`, integrated geometry/demand, services/spatial; screening không giả native metric; GFA/FAR/bề mặt/trường và normalized basis |
| 7.2 | Native dùng mạng/giờ/seed chung; phạm vi module rõ | `native.py`, `network.py`, traffic/drainage; real XML specification/access/binding tests; HTTP native uncertainty; shadow fixed receivers; y tế/công viên capacity unavailable |
| 7.3 | Before/after/delta/unit/scope/time/method/source/comparability; missing null; Pareto | `compare`, native paired rows, normalization, ranking; source/CSV tests, unknown live test; no criteria thì not_requested; thiếu criterion không ranking |
| 8.1 | Ledger giữ/trừ/thêm/sau, di dời, interaction | `baseline.py`, `background.py`, `engine.assemble`; relocation/inclusive/native tests; interaction guard theo constituent, null + giả định riêng; ledger ghi certainty |
| 8.2 | Một mạng, background một lần, route/namespace/conservation/cohort/queue | `traffic.py`, network registry/stable geometry IDs; paired hours/seeds; embedded separator IDs test; road/lane XML đối chiếu; external-OD-only được ghi rõ |
| 8.3 | Shared SWMM, background catchment, hydrograph/time/continuity/node/link | `drainage.py`, hydrograph tests hai lưu vực; shifted grid/invalid rejected; native interaction; node/link/series API; free outfall synthetic có nhãn |
| 8.4 | Tổng profile rồi peak, capacity vùng một lần, missing không approve | `utilities.py`, peak-of-sum test; unknown capacity/occupancy checks; portfolio phase 3 có ba breach |
| 8.5 | Nhu cầu/capacity dịch vụ dùng chung, không đổi đơn vị | `services.py`: max-flow/min-cost allocation; residual reassignment, shared school/unknown demand/capacity tests; B thêm chỗ dùng chung; healthcare/park chưa allocation |
| 8.6 | Union geometry/shadow, cùng receiver/time, bỏ building thay thế | `spatial.py`; fixed receiver/union/removal tests; baseline ledger; không suy thành nhiệt độ |
| 9 | Study/result/map/time contract có đủ dữ liệu truy vết | Schema, context, comparisons, marginal/interaction, normalization; source/map/CSV/ZIP tests; contract mapping ở mục 4 bên dưới |
| 10 | Durable queue/worker, partial/cancel/timeout/retry/cache, SQLite/Postgres, retention | Jobs/store/cache/runner/recovery; real process tree/lease/partial native tests; Postgres/Linux; child API; opt-in orphan GC giữ mọi artifact được tham chiếu |
| 11 | Seed pairing, random stream ổn định, sensitivity/weights/materiality | `uncertainty.py`, models settings; native background stream test; HTTP uncertainty; case/seed/weight/stability tests và browser; spread không được gọi confidence interval |
| 12 | Tách package, dùng chung kernel, named samples/scripts/handoff | Planning package dùng integrated demand/geometry/library/native runner; worker/preparer/smoke scripts tồn tại và chạy; samples validated; mapping file dự kiến ở mục 4 |
| 13 | Mốc A–F/M0–M5 theo evidence | Schema/context/queue → screening → native → shared capacity/services → portfolio → uncertainty/artifact; gates trong mục 1 và case mục 3 |
| 14 | 13 invariant | Đối chiếu từng invariant ở mục 3 dưới đây; full regression và native live |
| 15 | Hai case tái hiện, spatial API, tương tác native, nguồn/giới hạn | Portfolio ZIP/CSV/source + HTTP selection/uncertainty + UI; samples/runbook/handoff; không phê duyệt quy hoạch hay suy sức chứa đô thị từ synthetic |
| 16.1–16.2 | Single-site/nền N1–N4 | Audit này, shared single-site, manifest/dedup/unknown và recovery/partial child gates |
| 16.3 | Phần 2, sáu bước và case nhạy | Equal program validation, native case/seed, Pareto/weights, metadata và browser; API JSON/GeoJSON/ZIP |
| 16.4 | Phần 3, tám state/thứ tự/marginal/interaction | Portfolio live report; phase/state identity; allocation/peak/conservation/continuity; interaction nonzero |
| 16.5–16.6 | M0–M5/T1–T7 và feature handoff | Gates/schema/adapter/benchmarks/native/backend artifacts; API handoff và runbook, chưa thay frontend map chính |
| 16.7 | End-to-end hai case + regression + bàn giao | Reports mục 1, tám state/two orders, UI cancel/retry/restore, samples và artifacts mục 5 |

Coverage được chứng minh cho mạng/graph **generated synthetic** đã khai báo,
không cho hạ tầng thật quanh Thủ Đức. Snapshot inclusive thiếu coverage của
toàn mạng bị chặn; các polygon/binding/đơn vị không hợp lệ bị chặn trước solver.
Không claim adapter tự xử lý mọi source của nhóm chưa bàn giao contribution.

## 3. Đối chiếu 13 invariant và hai case nghiệm thu

| # | Bằng chứng cụ thể |
|---|---|
| 1 | Frozen/order screening; native ba parcel đổi tên/thứ tự giữ metric trong 1e-6; solver IDs theo geometry; same-parcel physical access tests |
| 2 | Equal-program giảm units bị từ chối, footprint ngoài parcel/region bị từ chối; không tự đổi target |
| 3 | Context source/version/hour/rain/seed hash; inclusive stale/coverage rejects; generated traffic/walking coverage bao actual geometry; row/map source/unit/window đối chiếu |
| 4 | Same-parcel baseline một lần; inclusive contribution subtract một lần; keep/remove/native relocation; retained geometry/receiver tests |
| 5 | Peak-of-sum cho peak lệch/trùng; capacity shared, unknown không approve; ba breaches phase 3 |
| 6 | Shared school allocation và residual reassignment; reserved/background một lần; unknown capacity/demand không thành zero |
| 7 | Real native conservation, background departure stream ổn định, no private shortcuts, same-parcel dedup và namespace chứa separator; completed/unfinished/undeparted cùng report |
| 8 | Native shared SWMM + continuity/background/binding; hai hydrograph đúng grid và full native hai catchment; nonzero interaction/node-link series |
| 9 | Native single-site independent orchestration cùng context/topology; option rỗng bằng baseline; full physical state từng tập giống nhau giữa A-first/B-first |
| 10 | Phase AB/ABC bằng option tương ứng; đủ tám screening và tám native states; không tích lũy tải phase trước |
| 11 | Live unknown screening/native JSON/CSV null và ranking blocked; synthetic không nâng observed; incomplete completed cohort không được ranking; invalid constituent không được interaction |
| 12 | Real cancel/timeout/orphan tree, lease fencing/partial retry, immutable/idempotent study, context/version/checksum cache invalidation; Postgres/Linux; GC bảo vệ reference |
| 13 | Full 110 planning+integrated tests; independent actual native solver; HTTP/UI cả phần 1/2/3; không chỉ mock kết quả |

Case phần 2: chung cư 200 căn/600 cư dân/24.000 m² tại A/B/C, dùng nền chung;
view baseline/option/layers và chạy reference/low/high, ba seed, 7h/18h.
Criteria do study chọn; không có default overall winner. Run/revision cũ giữ
nguyên khi input thay đổi, ZIP chứa solver inputs/outputs đã kiểm checksum.

Case phần 3: A chung cư 200 căn, B trường 600 chỗ, C chung cư 150 căn.
Tám state và hai thứ tự đã chạy. B-first giải quyết chỗ học sớm; A-first
đưa nhà ở vào sớm. Cả hai có cùng AB/ABC. ABC vượt 500 kW điện, 180 m³/ngày
nước và 130 m³/ngày nước thải ở phase 3 trong **fixture synthetic**.
SWMM interaction AB ≈ −2,029 m³ và ABC ≈ +2,832 m³; không coi đây là causal
attribution hoặc độ sâu ngập thực địa. Browser có cancel/retry actual job;
native partial retry test chỉ chạy phần chưa hoàn chỉnh và giữ child phù hợp.

## 4. Mapping các tên dự kiến sang hợp đồng thực tế

Mục 9/12 của kế hoạch dùng schema/cấu trúc file **dự kiến**. Hợp đồng hiện tại:

| Tên dự kiến | Nơi thực hiện/truy xuất |
|---|---|
| `screening.py`, `portfolio.py` | `engine.py`: evaluate/assemble/state keys; `native.py` orchestrates solver, không tạo file stub |
| `store.py + schema.sql` | SCHEMA trong `store.py`; SQLite/Postgres tables study/run ở planning_documents, queue/child/cache/benchmark riêng |
| revision/status/context hash | Study ID là revision; parent_revision_id trong study; job status và result_id qua `/jobs/{id}`; hash ở study và `result.context.sha256` |
| coverage/assumptions/source/version | `result.context.data_coverage`, source_manifest, library, inputs/conditions; uncertainty cases có effective input/hash riêng |
| runtime/child IDs/engine versions | Job timestamps/progress/children; benchmark/preflight; `/jobs/{id}/children`, child result IDs; result.engine_versions/child_cache |
| artifact_manifest | Native network/state artifacts có file hash/size; ZIP source-manifest + inputs/result/maps/solver files; checksum gate trước tải |
| time artifacts/chunks | `/runs/{id}/timeseries` theo object/offset/limit≤300; road hour/seed và SWMM catchment/sample; thiếu sample null |
| fields of comparisons | comparison/traffic_comparison/drainage_comparison; marginal rows và interaction.metrics + comparability_by_metric + unavailable_reasons/scenario_values |

## 5. Named artifacts và hướng dẫn bàn giao

- `scripts/planning-worker.py` và module worker: chạy queue bền vững, đã kiểm
  entrypoint trong Linux và live Docker.
- `scripts/prepare-planning-study.py`: đã chạy với output riêng, tạo năm
  JSON schema-validated, không sửa input historical.
- `scripts/test-planning-studies-local.py`: native/uncertainty live API;
  `test-planning-portfolio-local.py`: tám state/two orders;
  `test-planning-missing-local.py`: unknown JSON/CSV;
  `test-planning-series-local.py`: chunks và selectors.
- `scripts/test-planning-postgres-local.py`, `planning-linux-native-check.py`,
  `test-planning-ui.cjs`: storage/package/browser gates.
- `docs/samples/planning-site-selection.json`, `planning-cumulative.json`,
  `planning-single-site.json`, `planning-rehousing.json`,
  `planning-inclusive-background.json`: fixtures/handoff.
- `docs/samples/planning-portfolio-a-first.json`,
  `planning-portfolio-b-first.json`: inputs đầy đủ tám state đã chạy.
- `test-results/planning-portfolio/A-first.zip`, `B-first.zip`: JSON/CSV,
  ledger/source manifest/GeoJSON và solver artifacts, zip integrity đạt.
- [API handoff](planning-simulation-api-handoff.md),
  [runbook local](planning-demo-local-runbook.md),
  [kế hoạch dễ đọc](planning-parts-2-and-3-implementation-plan.md).

Report files/runtime được gitignore. API preview local 8007 và worker cùng
volume giữ kết quả để review. Không có commit/push/deploy trong lượt này.

## 6. Giới hạn và bước sau demo

Đã làm bộ tính theo kịch bản; chưa hiệu chỉnh OD/pha đèn/cống/capacity thật.
Synthetic locations gần Thủ Đức không chứng minh mô hình hóa đường/cống thật.
Services hiện allocation trường học; healthcare/park capacity unavailable.
Traffic external-OD-only; phase là trạng thái vận hành, chưa model thi công/
growth theo năm. Không có ngập 2D/triều, power flow/áp lực nước, thermal comfort,
predict giá đất, legal approval hoặc tối ưu toàn thành phố.

Counting gắn road/direction/time, capacity/cống địa phương và các module dịch
vụ khác là bước tiếp theo của kế hoạch. Frontend teammate tích hợp hợp đồng
API vào map; deploy sau khi có cấu hình máy. Các mục này không được ghi là
đã hoàn thành bởi backend demo local.
