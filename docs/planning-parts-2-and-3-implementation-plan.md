# Kế hoạch chi tiết: so sánh vị trí và phát triển cộng dồn

Cập nhật: 11/10/2026. Phạm vi: backend simulation, API và preview local.
Frontend map chính do thành viên khác tích hợp. Không commit/push/deploy.
Object counting và AI giải thích tiếp tục hoãn; demo dùng dữ liệu synthetic
có nhãn trước khi hiệu chỉnh bằng dữ liệu địa phương.

## 1. Phần 1 hiện tại có đủ chưa?

**Đủ cho demo cơ bản một khu đất:** chọn parcel, nhập building plan, chạy
hiện trạng/phương án, xem tác động và lưu/mở lại kết quả. Luồng single-site
trên nền chung đã có API và worker; dùng cùng bộ tính với hai phần mở rộng.

Điều kiện sử dụng: dữ liệu nền/capacity/OD/cống synthetic phải được công khai.
Đây chưa phải dự báo đã hiệu chỉnh cho TP.HCM. API integrated cũ dùng mạng
site-only; frontend nên dùng hợp đồng planning chung để nối cả ba phần.

## 2. Mục tiêu và ranh giới hai phần

| Phần | Câu hỏi của urban planner | Các phương án |
|---|---|---|
| 2 — lựa chọn vị trí | Cùng chung cư nên đặt ở A, B hay C? | A/B/C loại trừ nhau; mỗi lần chỉ một phương án hoạt động |
| 3 — cộng dồn/giai đoạn | A/B/C cùng tồn tại thì hạ tầng bị tác động thế nào; triển khai thứ tự nào? | Các tập active A, B, C, AB, AC, BC, ABC; phase theo thứ tự đưa vào vận hành |

Ưu tiên quyết định vị trí, công năng, quy mô, bổ sung công suất và giai đoạn.
Chi tiết cổng/hình khối là thông số tùy chọn khi có hồ sơ thiết kế.

## 3. Nền chung cần khóa trước khi chạy

Tạo một `PlanningStudy`, đóng băng thành `StudyContext` có hash/version:

- AOI, parcel, công trình hiện hữu và chính sách giữ/thay thế/di dời.
- Dân nền, mạng đường/đi bộ, OD, giờ giao thông và seed.
- Vùng điện/nước/nước thải, capacity và profile theo giờ.
- Trường học, số chỗ, nhu cầu nền và khoảng cách tiếp cận.
- Lưu vực, mạng SWMM, outlet, trận mưa và bước thời gian.
- Geometry/height, ngày giờ bóng đổ và vùng nhận bóng cố định.
- Thư viện hệ số, nguồn, đơn vị, phạm vi phủ và trạng thái dữ liệu.

Các option dùng cùng context. Đổi dữ liệu tạo revision mới; run cũ giữ nguyên.
Snapshot tổng vùng đã chứa parcel phải khai báo contribution để tách tải
hiện hữu đúng một lần. Không tự suy phần chồng lặp từ tổng vùng.

Thiếu occupancy/capacity được giữ là unknown. Bảng so sánh không dùng số giả
định làm số đã biết: `before/after/delta=null` nếu không đủ dữ liệu; số dùng
để tính kịch bản được lưu riêng trong `scenario_values` khi áp dụng.

## 4. Phần 2: chọn vị trí

### Case nghiệm thu

Cùng chung cư 200 căn/600 cư dân đặt tại A hoặc B hoặc C trong một vùng pilot.
Plan của từng vị trí phải hợp lệ về geometry và cùng chương trình phục vụ.
Không giảm số căn ở một option để làm tải thấp hơn rồi xếp hạng cao hơn.

### Pipeline và điều kiện xong

| Bước | Xử lý | Đầu ra | Nghiệm thu |
|---|---|---|---|
| 2.1 Input/preflight | Validate program, parcel, bề mặt, hiện trạng, coverage, workload | Lỗi/giới hạn; số trạng thái/solver và ETA nếu có benchmark phù hợp | Input không hợp lệ bị chặn trước solver; thiếu benchmark hiện unavailable |
| 2.2 Screening | Tính nhu cầu, FAR/GFA, bề mặt/runoff sơ bộ, tiếp cận trường, bóng đổ | Baseline + A/B/C; bảng tác động nhanh | Cùng vùng/thời gian/đơn vị; unknown không biến thành 0 |
| 2.3 Shortlist | Người dùng chọn vị trí cần chạy native | Danh sách option đã khóa cùng nền | Giữ baseline chung và khai báo program |
| 2.4 Native | SUMO chung network/background/giờ/seed; SWMM theo binding lưu vực | Metric, road/node/link layers, series và artifact | Conservation/continuity hợp lệ; connector không tạo đường tắt cho xe nền |
| 2.5 So sánh | Before/after/delta, Pareto và trọng số tùy chọn | Bảng đánh đổi và comparability từng metric | Không chọn thắng dựa metric thiếu hoặc cohort giao thông không tương thích |
| 2.6 Độ nhạy | Ba seed ghép cặp và reference/low/high | Spread, thay đổi ranking/Pareto và cảnh báo | Không gọi spread là confidence interval; ranking bất ổn phải được báo |
| 2.7 Bàn giao | Lưu run; tải JSON/CSV/GeoJSON/ZIP | API examples, ID option và selectors | Reload giữ input/kết quả; layer đúng option/giờ/seed |

### Các kết quả planner xem

| Nhóm | Kết quả |
|---|---|
| Giao thông | Delay xe nền/xe dự án, hàng chờ theo đường/thời điểm, completed/unfinished/undeparted |
| Thoát nước | Runoff, tràn tại node, flow/depth tại link và thời điểm peak |
| Điện/nước/nước thải | Nhu cầu, peak điện, phần dư/thiếu capacity từng vùng hoặc unknown |
| Trường học | Nhu cầu được phục vụ/chưa phục vụ và khả năng tiếp cận |
| Hình học | GFA/FAR, diện tích bề mặt và bóng trên cùng vùng đo |

Không có một vị trí tốt nhất cho mọi mục tiêu. Kết quả có thể cho A tốt hơn
về tiếp cận nhưng B ít áp lực giao thông hơn; planner chọn tiêu chí để cân nhắc.
Giá đất/ngập lịch sử là bối cảnh có nguồn, chưa phải metric dự báo từ xây dựng.

## 5. Phần 3: tác động cộng dồn và thứ tự triển khai

### Case nghiệm thu

- A: chung cư 200 căn.
- B: trường 600 chỗ.
- C: chung cư 150 căn.
- Tám trạng thái: baseline, A, B, C, AB, AC, BC, ABC.
- Hai thứ tự: A → AB → ABC và B → AB → ABC.

Phase mô tả các dự án đang vận hành; chưa mô hình hóa quá trình thi công,
tăng trưởng dân số theo năm hoặc thời gian đi vào sử dụng nếu chưa có input.

### Pipeline và điều kiện xong

| Bước | Xử lý | Đầu ra | Nghiệm thu |
|---|---|---|---|
| 3.1 Ledger | Tách background, hiện hữu giữ/bỏ và tải mới; khai báo di dời | Bảng trước/trừ/thêm/sau theo parcel/vùng | Không đếm đôi cư dân, công trình hoặc contribution |
| 3.2 Active sets | Deduplicate option và phase cùng tập project | Một state cho mỗi tập active | AB=BA; phase AB bằng option AB; thiết kế thay thế cùng parcel không cùng active |
| 3.3 Utilities | Cộng profile theo cùng giờ rồi lấy peak; dùng capacity vùng một lần | Nhu cầu/peak/headroom/checks | Không cộng peak riêng; capacity unknown không thành within_capacity |
| 3.4 Dịch vụ | Phân bổ nhu cầu nền + project vào danh mục trường chung | Chỗ học thiếu và nhóm được phục vụ | Một chỗ dùng một lần; B có thể phục vụ A/C và dân nền |
| 3.5 SUMO chung | Mọi project active và background chạy cùng mạng | Delay/queue/conservation từng state | Nền chỉ một lần; không đi qua connector inactive; báo chuyến chưa hoàn thành |
| 3.6 SWMM/hình học chung | Tổng runoff đúng timestamp; cùng graph; union bóng/bề mặt | Node/link series, peak và geometry | Không cộng peak của các run riêng; kiểm tra continuity và binding |
| 3.7 Đóng góp/thứ tự | Tính marginal/interaction; tìm phase đầu vượt capacity | Bảng trạng thái/giai đoạn và đánh đổi | Cùng tập active ở hai thứ tự cho cùng trạng thái; ghi nguồn capacity |
| 3.8 Review phương án | Planner sửa vị trí/quy mô/capacity hoặc thứ tự và chạy revision | Một phương án thay đổi có kết quả đối chiếu | Không coi gợi ý chưa chạy là cải thiện đã được chứng minh |

### Công thức

```text
delta(S)       = result(S) - result(baseline)
marginal(B|A)  = result(AB) - result(A)
interaction(AB) = delta(AB) - delta(A) - delta(B)
peak điện     = max_t [background(t) + tổng tải project active(t)]
```

Chỉ tính chênh lệch khi metric cùng đơn vị/phạm vi và đủ điều kiện so sánh.
Interaction thể hiện tính phi tuyến; dấu âm/dương cần diễn giải theo metric,
không tự quy thành tốt/xấu. SUMO hiện dùng external-OD-only có nhãn; chuyến
nội bộ A→B cần ledger riêng trước khi thêm để tránh đếm một chuyến hai lần.

## 6. Tổ chức backend và tích hợp frontend

| Thành phần | Trách nhiệm |
|---|---|
| `planning/models.py`, `context.py`, `provenance.py`, `background.py` | Input, frozen context, nguồn/coverage, adapter contribution |
| `engine.py`, `utilities.py`, `services.py`, `spatial.py` | State, ledger, nhu cầu, phân bổ dịch vụ, hình học |
| `native.py`, `traffic.py`, `drainage.py` | Orchestrate SUMO/SWMM trên nền chung |
| `comparison.py`, `normalization.py`, `uncertainty.py` | Đánh đổi, comparability, basis phục vụ và độ nhạy |
| `store.py`, `jobs.py`, `runner.py`, `recovery.py`, `cache.py` | Queue/worker, artifact, cancel/retry và lưu trữ |
| Router planning, `map_output.py`, `series_output.py` | API, GeoJSON và series có phân trang |

Luồng frontend: **chọn parcel/plan → preflight → tạo study → enqueue run →
poll job → đọc kết quả → chọn option/phase/layer/time → lưu/mở lại**.

API gốc `/api/v1/planning`: `POST /studies/preflight`, `POST /studies`,
`POST /studies/{id}/runs`, `GET /jobs/{id}`, `GET /runs/{id}`, cùng
`/runs/{id}/map`, `/timeseries` và `/artifacts`. Xem query/body cụ thể trong
[API handoff](planning-simulation-api-handoff.md).

## 7. Trạng thái triển khai và thứ tự việc còn lại

Demo backend/local hiện đã nghiệm thu; xem
[audit đầy đủ](planning-demo-final-audit.md). Bảng dưới phân biệt bằng chứng
demo với các bước tích hợp/hiệu chỉnh tiếp theo.

| Hạng mục | Bằng chứng local hiện có | Việc tiếp theo |
|---|---|---|
| Nền chung và single-site | Frozen context, revision/ledger, shared native, HTTP single-site và audit hợp đồng | Khi có snapshot thực, kiểm tra adapter theo contribution được bàn giao |
| Phần 2 | HTTP native/uncertainty, ba seed, bảng/Pareto và browser; missing guards đã kiểm tra | Hiệu chỉnh nguồn địa phương sau demo |
| Phần 3 | Native đủ tám state và hai thứ tự; marginal/interaction, phase capacity và browser đã đối chiếu | Review mục tiêu/capacity thực khi có hồ sơ |
| Vận hành | PostgreSQL/PostGIS local; image Linux; cancel/retry/cache; chunked series; runbook | Deploy khi có cấu hình máy và được yêu cầu |
| Bàn giao | API handoff, samples, JSON/CSV/GeoJSON/ZIP và audit | Người phụ trách frontend tích hợp map chính |

Regression đầy đủ cuối: **110 test đạt** sau các chỉnh unknown/interaction.
Live API/worker xác nhận unknown trả null, giữ giả định riêng; browser đạt
**16 nhóm**. PostgreSQL/Linux và native uncertainty cũng đã kiểm tra lại.
Các số này có phạm vi cụ thể trong audit, không khẳng định độ chính xác thực địa.

Thứ tự hoàn thiện đã thực hiện: **audit hợp đồng/unknown → nghiệm thu phần 2 →
nghiệm thu tám state/hai thứ tự phần 3 → chốt artifact/hướng dẫn**.
Tiếp theo là người phụ trách frontend tích hợp API lên map chính.
Không đưa lại việc camera counting vào đường găng của demo chức năng.

### Kết quả mẫu đã chạy, để kiểm chứng phần 3

Ở fixture synthetic hiện tại, B-first giảm thiếu chỗ học ở phase 1 từ 134
xuống 0, còn A-first đưa nhà ở vào sớm hơn. Hai thứ tự có cùng kết quả AB/ABC.
ABC vượt capacity điện, nước và nước thải ở phase 3; đây là ngưỡng synthetic,
không phải công suất thực của Thủ Đức. SWMM đã có interaction khác 0.

Mẫu đã lưu: `docs/samples/planning-portfolio-a-first.json` và
`docs/samples/planning-portfolio-b-first.json`. Báo cáo local ở
`test-results/planning-portfolio/portfolio-report.json` (gitignore).

## 8. Điều kiện bàn giao và phần sau demo

Chỉ nghiệm thu demo khi hai case chạy end-to-end, phần 1 không regression,
13 invariant của kế hoạch gốc có bằng chứng, artifact tái hiện được, và API
trả đúng nguồn/unknown/comparability để frontend tích hợp.

Sau đó: counting gắn road/direction/time để hiệu chỉnh OD; dữ liệu capacity
và mạng cống thật; module y tế/công viên có schema nhu cầu/capacity riêng.
Mô phỏng ngập 2D, nhiệt độ, giá đất hoặc tối ưu toàn thành phố cần mô hình
và nghiệm thu riêng, không nằm trong kết quả hiện có.

Demo local: <http://127.0.0.1:8007/simulation/planning>.
Yêu cầu chi tiết và invariant nằm trong
[kế hoạch đầy đủ](urban-planning-multisite-cumulative-plan.md), mục 6–16.
