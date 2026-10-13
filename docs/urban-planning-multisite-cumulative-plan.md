# Kế hoạch so sánh nhiều khu đất và mô phỏng phát triển cộng dồn

Ngày lập/cập nhật: 11/10/2026. **Đã hoàn thành demo chức năng backend/preview
local trên dữ liệu synthetic** theo phạm vi bên dưới. Bằng chứng từng mục và
13 invariant nằm trong [audit cuối](planning-demo-final-audit.md).
Frontend map chính, hiệu chỉnh dữ liệu thật, counting và deploy là mốc sau.

Demo: `http://127.0.0.1:8007/simulation/planning`;
[hướng dẫn chạy/review](planning-demo-local-runbook.md).
Regression 110 passed; browser 16 nhóm; native đủ tám state/hai thứ tự,
uncertainty hai bài toán, chunked API, PostgreSQL và image Linux đều đạt.
Các mục lịch sử phía dưới giữ trạng thái ở thời điểm lập/cập nhật từng mốc;
không dùng các chữ "còn/chưa" ở mốc cũ để suy trạng thái hiện tại.

Quy ước trong trao đổi: **phần 1** là mô phỏng một khu đất/công trình;
**phần 2** là so sánh các vị trí thay thế A/B/C; **phần 3** là tác động cộng
dồn và giai đoạn triển khai của nhiều dự án cùng tồn tại.

**Bản kế hoạch dễ đọc, cập nhật theo code hiện tại:**
[Kế hoạch chi tiết phần 2 và 3](planning-parts-2-and-3-implementation-plan.md).
Bản đó ghi pipeline, input/output, module, điều kiện nghiệm thu và việc còn
lại; các mục dưới đây giữ đầy đủ yêu cầu và lịch sử triển khai.

**Đọc kế hoạch triển khai chi tiết:** mục 16.2 là nền chung, 16.3 là phần 2,
16.4 là phần 3, 16.5–16.6 là thứ tự bàn giao và công việc còn lại,
16.7 là kịch bản nghiệm thu demo. Phần 1 đủ cho demo cơ bản với giả định có
nhãn; xác nhận này không có nghĩa đã hiệu chỉnh cho quyết định thực tế.

### Lịch sử trạng thái khi rà soát tài liệu

Repo local đã có schema/context, screening, API study/job/revision, worker
riêng, tải kết quả và mô hình SUMO/SWMM chung trong
`backend/app/services/simulation/planning/`. Bằng chứng đã lưu gồm smoke HTTP
screening (`test-results/planning-studies/http-report.json`) và bộ 13 test
planning không lỗi (`test-results/planning-native.xml`), có chạy solver thật.
Đây là bằng chứng cho phạm vi test đó, không phải nghiệm thu toàn bộ kế hoạch.

Đã bổ sung phân bổ chỗ học dùng chung trên graph đi bộ synthetic, bóng đổ
union/vùng nhận bóng cố định, tiêu chí/Pareto, chuỗi node/link SWMM và preview
`/simulation/planning`. Regression gần nhất đạt 44 test; HTTP native và 8 nhóm
kiểm tra browser có bằng chứng local. Xem
[API handoff](planning-simulation-api-handoff.md) để chạy và tích hợp.

Độ nhạy đã có run riêng với case input công khai, ba seed ghép cặp, kiểm tra
Pareto/trọng số và cảnh báo khi ranking đổi theo seed dù trung bình case ổn
định. Lượt native site-selection đã chạy 36 SUMO/12 SWMM trên ba case. Xem
[chi tiết và bằng chứng](planning-uncertainty-demo.md).

Khôi phục/retry/cache job và partial child results đã có test; store
PostgreSQL/PostGIS đã có lượt kiểm tra thật trong container riêng. Regression
model 0.6 đạt 53 test, có sửa physical access/branch dùng chung cho các thiết
kế cùng parcel. Chi tiết và phạm vi bằng chứng ở
[báo cáo tiến độ](planning-demo-progress-report.md).
Model 0.7 bổ sung [ledger và case di dời](planning-baseline-ledger.md),
regression 59 test và 10 nhóm browser đạt. Các kết quả là local synthetic;
adapter nền tổng vùng và audit nguồn/coverage vẫn còn công việc.
Model 0.8 đã có [manifest nguồn/coverage từng module](planning-source-manifest.md),
regression 63 test, provenance focused 5 test, HTTP native cả hai case và
11 nhóm browser đạt; native uncertainty 36 SUMO/12 SWMM có source riêng từng
case. Đây vẫn là các mốc có phạm vi test, chưa nghiệm thu toàn bộ kế hoạch.
Các phần còn cần hoàn thiện/kiểm chứng gồm retention,
provenance/coverage và ledger nâng cao, cùng audit đầy đủ các yêu cầu dưới đây. Trường học là module
dịch vụ đầu tiên; healthcare/park capacity allocation chưa triển khai.
Kế hoạch mô tả đích cuối, không khẳng định mọi hạng mục đã hoàn chỉnh.

Cập nhật 0.9: [adapter nền tổng vùng và retention](planning-background-snapshot.md)
đã có code/test; nền được tách bằng contribution tường minh. CLI giữ artifact
đã tham chiếu, chỉ dọn orphan khi opt-in và store không còn job active. UI 12
nhóm đạt. Các giới hạn còn lại là corner cases, selectors/layer timeseries,
audit toàn bộ yêu cầu và package end-to-end hiện tại; các đoạn mốc trước ở
trên là lịch sử, không phải tuyên bố adapter/retention hiện chưa có.

Đối tượng sử dụng: urban planner đánh giá vị trí, công năng, quy mô và thứ tự
phát triển. Simulation là một tính năng trong map quy hoạch của nhóm. Phần này
bàn giao backend, dữ liệu kết quả theo không gian và hợp đồng API; frontend do
thành viên khác tích hợp. AI giải thích tiếp tục hoãn theo yêu cầu đã thống nhất.

## 1. Phần 1 — hiện trạng ban đầu để lập kế hoạch

Cập nhật hiện tại: single-site đã có shared study/context cùng hai phần mở
rộng, API/worker/native tương đương được kiểm tra. Những hạn chế về nhóm so
sánh ở đoạn dưới là trạng thái ban đầu; xem audit cuối và handoff cho luồng mới.

**Đủ cho demo cơ bản:** chọn một khu đất, nhập hoặc đổi công năng/quy mô,
chạy hiện trạng và phương án xây dựng, xem tác động đa feature và lưu kết quả.
Code hiện có preset residential/school/office/hospital/other, hình học, nhu cầu,
SUMO, SWMM, bóng đổ, snapshot, nguồn tham số, sensitivity và recommendations.

**Chưa hoàn chỉnh trải nghiệm so sánh công năng/quy mô:** mỗi lần predict là một
run riêng; chưa có nhóm phương án với điều kiện so sánh được khóa chung, bảng
so sánh chính thức và kiểm tra khả năng so sánh. Công viên chưa có preset/model
công năng riêng. Không coi `other` tự động mô hình hóa đầy đủ công viên.

Một số điểm từ code cần xử lý trước khi mở rộng:

| Thành phần | Hiện tại | Hệ quả |
|---|---|---|
| `IntegratedRequest` | Một `site`, một `development` | Danh sách buildings trong một site chưa phải nhiều dự án trên nhiều parcel |
| Giờ SUMO | Chọn giờ cao điểm theo development trong mỗi run | So hai run riêng có thể vô tình khác giờ |
| Mạng giao thông | Một `project_gate`, một điểm đấu nối gần site | Chưa có nhiều nguồn/đích dự án chạy chung |
| SWMM | Các bề mặt đổ về mạng mẫu S1/J1/O1 | Chưa có lưu vực/nút chung cho nhiều khu đất |
| Dịch vụ | Nhu cầu tổng hợp, capacity mẫu, có POI | Chưa tách đầy đủ trường học/y tế; POI không cung cấp công suất thực |
| Occupancy hiện trạng | Có footprint/height nhưng có thể thiếu người sử dụng | Không thể hiểu giá trị mặc định 0 là khu đất không có người |
| Lưu run | JSON local hoặc bảng PostGIS, cần `inputs.site` | Cần kho lưu riêng cho study/multi-site; không ép nhiều parcel vào schema một site |

Phần 1 tiếp tục dùng được trong phạm vi demo. Các hạng mục khóa điều kiện và
so sánh dùng chung dưới đây đồng thời hoàn thiện phần 1.

## 2. Hai tính năng cần xây

### 2.1 So sánh nhiều khu đất — lựa chọn thay thế nhau

Câu hỏi: “Cùng nhu cầu bổ sung 200 căn/600 cư dân, đặt tại A, B hay C tốt hơn
theo các tiêu chí đã chọn?”

- Mỗi option chỉ xây tại một khu đất; những khu còn lại giữ hiện trạng.
- Cùng nhu cầu phục vụ, giờ đánh giá, trận mưa, năm/kịch bản dân số, thư viện
  hệ số, phạm vi đo và bộ seed.
- Trả về lợi ích, áp lực, vị trí bị ảnh hưởng, độ đầy đủ dữ liệu và đánh đổi.
- Không mặc định khu ít người ở/ít tải nhất là phương án tốt nhất; cần xét
  mục tiêu phục vụ, khả năng tiếp cận và tác động lên hiện trạng.

### 2.2 Nhiều dự án cộng dồn — các dự án cùng tồn tại

Câu hỏi: “Nếu A xây chung cư, B xây trường học, C xây thêm chung cư thì hạ
tầng và dịch vụ của cả khu thay đổi thế nào? Nên triển khai theo giai đoạn nào?”

- Dự án giữ polygon, công năng, quy mô, thời điểm đưa vào sử dụng và nguồn
  dữ liệu riêng, nhưng chạy trên nền chung.
- Giao thông chạy chung một mạng; các parcel cùng lưu vực chạy chung mạng
  thoát nước; điện/nước gom theo vùng phục vụ và cùng giờ.
- Có hiện trạng, từng dự án riêng, tổ hợp và các giai đoạn.
- Không lấy tổng delay hoặc tổng flooding của các run đơn lẻ làm kết quả chung.

## 3. Phạm vi demo đầu tiên và giới hạn tính toán

Chọn một vùng pilot Thủ Đức khoảng 2 × 2 km, tùy độ đầy đủ mạng và ngân sách
tính toán. Bắt đầu với 3 khu đất A/B/C cùng vùng nghiên cứu, 2–3 dự án và tối đa
3 giai đoạn. Đây là cấu hình pilot dự kiến, cần preflight xác nhận phù hợp.

- So vị trí: A-only, B-only, C-only, cùng 200 căn/600 cư dân.
- Cộng dồn: A = chung cư 200 căn; B = trường học có công suất được nhập;
  C = chung cư 150 căn. Công suất trường là giả định thiết kế, không phải
  suy ra từ diện tích đất.
- Chọn ngày đại diện và các cửa sổ giao thông chung, ban đầu sáng và chiều;
  giờ cụ thể cấu hình khi tạo study và giữ nguyên cho mọi option.
- Mưa thử low/base/high được công bố cụ thể bằng lượng mưa, thời lượng và
  phân bố thời gian; không tự gọi là chu kỳ lặp 10/50/100 năm khi thiếu IDF.
- Giữ giới hạn mạng hiện tại ở mức tối đa 4.000 drivable edges trong pilot;
  quá giới hạn phải báo thu hẹp vùng hoặc dùng chế độ screening.
- Không tải toàn TP.HCM vào một lần mô phỏng. Các vị trí ở những vùng mạng
  tách biệt được báo ngoài phạm vi MVP, không ghép số delay thành cùng bảng xếp hạng.

Preflight tính số lượt solver và ước lượng thời gian từ benchmark thực tế;
không hứa realtime. Chỉ chạy đầy đủ native solver cho shortlist sau screening.

## 4. Luồng người dùng trên map

### So sánh vị trí

1. Chọn A/B/C trên map; đặt tên và xác nhận đây là phương án thay thế nhau.
2. Nhập mục tiêu chung: công năng, số căn/người hoặc công suất phục vụ,
   tổng diện tích sàn dự kiến; chọn điều kiện thử và tiêu chí quan tâm.
3. Mỗi khu có phương án thiết kế sơ bộ phù hợp diện tích. Backend kiểm tra
   footprint nằm trong parcel và cân bằng bề mặt. Không tự dời cùng polygon
   building sang khu khác rồi coi là thiết kế hợp lệ.
4. Xem dữ liệu nền đã có/ước tính/còn thiếu và các khu không đáp ứng đầu vào.
5. Chạy screening, chọn shortlist, chạy simulation chi tiết.
6. Map nhận layer tác động của option đang chọn; bảng hiển thị cùng metric,
   cùng đơn vị, hiện trạng, sau xây, chênh lệch và phạm vi đo.
7. Lưu study để nhóm mở lại, đổi một thiết kế hoặc điều kiện và tạo revision.

### Cộng dồn/giai đoạn

1. Thêm các dự án A/B/C vào cùng study; mỗi dự án có site và building plan.
2. Khai báo giữ/thay thế công trình hiện hữu, cư dân mới/di dời nếu biết.
3. Đặt các tập dự án hoạt động: P1 = {A}; P2 = {A,B}; P3 = {A,B,C}.
4. Backend xây trạng thái hoàn chỉnh từng giai đoạn và mô phỏng lại.
5. Người dùng xem tác động của toàn bộ danh mục, phần tăng thêm khi đưa dự án
   tiếp theo vào và vị trí bắt đầu vượt mục tiêu theo kịch bản.

Giai đoạn MVP là các trạng thái vận hành giả định. Không mô phỏng bụi, đóng
đường, xe thi công hoặc tiến độ xây dựng; không tự dự báo tăng trưởng tới năm
2030/2035. Nếu dùng năm tương lai, phải có bộ giả định nền riêng cho năm đó.

## 5. Người dùng nhập gì, hệ thống tự làm gì?

| Đầu vào | Cách lấy trong MVP |
|---|---|
| Polygon khu đất/dự án | Từ thao tác chọn/vẽ trên map; xác nhận nguồn parcel |
| Công năng, quy mô phục vụ, số tầng/GFA, bề mặt, thiết bị | Từ building plan/preset; quy mô căn/người cần nhất quán |
| Hiện hữu giữ/phá, cư dân di dời | Người dùng xác nhận nếu biết; thiếu thì đánh dấu unknown và thử sensitivity |
| Mục tiêu chung/tiêu chí so sánh | Người dùng chọn; tách mục tiêu dự án khỏi quy định pháp lý |
| Danh mục dự án/giai đoạn | Người dùng chọn ID dự án đang hoạt động mỗi giai đoạn |
| Building/đường/đất phủ/dân số/POI | Snapshot nguồn nhóm, OSM, WorldCover, WorldPop, map_context |
| Tham số điện/nước/trips, lịch mặc định | Thư viện có phiên bản, đơn vị, phạm vi áp dụng và provenance |
| OD/lưu lượng/pha đèn | Ước tính khi thiếu; dùng counts đã kiểm chứng và gắn đúng road/time khi có |
| Cống, năng lực điện/nước/công suất cơ sở dịch vụ | Nhập dữ liệu được xác nhận hoặc dùng kịch bản tổng hợp có nhãn |
| Dữ liệu camera UIT-ADrone vừa thử | Chứng minh pipeline counting; chưa dùng để hiệu chỉnh khu A/B/C |

Không yêu cầu người dùng tự đoán hệ số động lực học xe hoặc thông số cống.
Nếu một kết luận phụ thuộc vào dữ liệu chưa biết, trả trạng thái chưa đủ căn cứ
hoặc kết quả theo khoảng giả định, không âm thầm điền thành dữ liệu thật.

## 6. Nền chung: StudyContext và tính công bằng

Tạo `StudyContext` bất biến gồm:

- Polygon vùng nghiên cứu và phạm vi mạng/biên tính toán của từng module.
- Manifest snapshot: ID/hash/phiên bản/thời điểm/phạm vi phủ từng lớp.
- Các baseline parcel và danh mục hiện hữu chung được khử trùng ID/geometry.
- Thư viện tham số, điều kiện mưa/giờ/ngày, assumptions, seed suite.
- Mạng giao thông chung, OD nền, các vùng dịch vụ/lưu vực/điện/nước khi có.
- Chính sách thay thế hiện trạng, dân số/giao thông nền và đơn vị đo.

Yêu cầu snapshot phải phủ cả vùng ảnh hưởng của module, không chỉ polygon
parcel. Có dữ liệu đường ở parcel không đủ để chạy routing tới biên AOI.
Nếu ghép nhiều snapshot, kiểm tra chồng lặp, nguồn ưu tiên, tuổi dữ liệu và
coverage; lưu manifest chung thay vì giả định có một file bao phủ mọi lớp.

Baseline vùng chỉ xây một lần trên cùng mạng/điều kiện. Mỗi option thay thế
phần hiện trạng tại parcel liên quan, giữ các phần khác đúng baseline. Không
lấy ba baseline 1 km chồng nhau rồi cộng dân số/đường/dịch vụ ba lần.

Hai chế độ so sánh cần công khai:

- `equal_program`: giữ cùng số căn/cư dân hoặc cùng công suất phục vụ; thiết kế
  từng site có thể khác. Option không chứa được chương trình phải báo không
  phù hợp về hình học/đầu vào, không tự giảm quy mô để tạo lợi thế.
- `declared_programs`: chương trình khác nhau, trả cả tổng tác động và chỉ số
  trên đơn vị phục vụ phù hợp. Không xếp trường học và chung cư bằng một chỉ
  số “trên căn hộ”; mục tiêu phục vụ phải do study định nghĩa.

Không chạy mọi option tại giờ cao điểm riêng rồi so trực tiếp. Cho phép phân
tích riêng giờ xấu nhất của mỗi option, nhưng tách khỏi bảng cùng giờ.

## 7. Tính năng 2: pipeline so sánh vị trí

### 7.1 Screening

Kiểm tra geometry, coverage, design feasibility, quy mô phục vụ và tính
nhất quán baseline. Tính diện tích/GFA/FAR, nhu cầu ngày/giờ, bề mặt không
thấm, runoff screening và tiếp cận dịch vụ trên mạng.

Giá đất và lịch sử ngập là bối cảnh có nguồn. Không suy ra giá thị trường
tương lai; không gọi khu đất hợp pháp để xây nếu chưa có quy hoạch áp dụng.

### 7.2 Native simulation trên shortlist

- SUMO: baseline vùng và từng option trên cùng mạng, cùng background flows,
  cùng cửa sổ và các seed ghép cặp. Project trips đặt tại đúng connector site.
- SWMM: chỉ so khác biệt theo vị trí khi có mạng/lưu vực tương ứng hoặc một
  cấu hình mạng tổng hợp công khai. Nếu vẫn dùng cùng mạng mẫu cho mọi site,
  metric chỉ phản ánh thiết kế/giả định, không được dùng để kết luận site nào
  thoát nước thực tế tốt hơn.
- Bóng đổ: dùng hình khối hiện hữu và của option; union bóng tại từng thời điểm,
  tách trong parcel và trên các đối tượng lân cận quan tâm.
- Dịch vụ: tách trường học, y tế, công viên; vị trí cho phép tính khoảng cách
  tiếp cận. Thiếu công suất thì chưa kết luận thiếu/chưa phục vụ bao nhiêu người.

### 7.3 Đầu ra so sánh

Mỗi metric trả `before`, `after`, `delta`, `unit`, `spatial_scope`,
`time_window`, `method`, `source_kind`, `comparability`, `limitations`.

`comparability` nhận `comparable`, `scenario_only`, `insufficient_data` hoặc
`not_comparable`. Missing là null kèm lý do, không thay thành 0.

Trả bảng đánh đổi/Pareto khi các metric đủ so sánh. Không có mặc định một
điểm tổng “site tốt nhất”. Nếu người dùng chọn trọng số, công bố trọng số,
cách chuẩn hóa, metric bị thiếu và kiểm tra độ ổn định của thứ hạng.

## 8. Tính năng 3: mô hình cộng dồn cho từng module

### 8.1 Công thức và ledger hiện trạng

Với nhu cầu có thể cộng theo cùng giờ:

```text
Load_option(t, zone)
  = Load_baseline(t, zone)
  - Load_existing_removed(t, zone)
  + Sum(Load_active_project_i(t, zone))

Delta_portfolio = Metric(all_active_projects) - Metric(baseline)
Marginal_B_given_A = Metric(A+B) - Metric(A)
```

Nhu cầu baseline đang thiếu không được coi là số 0 đã biết. Lưu ba thành phần
trong ledger để người dùng thấy phần nào có nguồn/ước tính/unknown. Cư dân di
dời trong vùng không tự tăng dân số toàn vùng; thay đổi vị trí vẫn có thể đổi
OD và vùng phục vụ. Dân số/trips dự án đã có trong nền phải được loại khỏi
nền trước khi thêm, tránh đếm hai lần.

Đối với interaction:

```text
Interaction_AB = [M(A+B) - M(0)] - [M(A) - M(0)] - [M(B) - M(0)]
```

Chỉ tính khi cùng metric, phạm vi, điều kiện và phiên bản. Đây là tương tác
trong mô hình, không phải chứng minh quan hệ nhân quả ngoài thực địa. Không
gán một “tỷ lệ lỗi do dự án B” từ marginal phụ thuộc thứ tự.

### 8.2 Giao thông

Refactor `road_network.prepare` và `solvers.traffic` để nhận nhiều project:

- ID node/edge/vehicle namespace theo project; connector và lịch riêng.
- Một mạng công cộng, background OD một lần, dòng phát sinh của mọi project.
- Cấu trúc so sánh kiểm soát được ảnh hưởng của connector; không để tuyến nền
  đi xuyên qua private connector của option không hoạt động.
- Project-to-project trips chỉ bật nếu OD generation có ledger chống trùng:
  một chuyến từ nhà A đến trường B phải là một xe/chuyến, không cộng cả hai
  đầu thành hai chuyến. MVP có thể dùng external-OD-only và ghi rõ chưa mô
  phỏng liên kết nội bộ, thay vì tự giả tỷ lệ internal capture rồi trừ tùy ý.
- Tách dòng external trips, internal trips và background; bảo toàn vehicles.
- Xuất edge/lane theo khoảng thời gian: volume, speed, travel time, queue,
  cùng throughput/completed/unfinished/undeparted và backlog.
- Mean delay phải kèm mẫu số và tỷ lệ hoàn thành. Nếu nghẽn làm ít xe hoàn
  thành, không xếp option tốt hơn chỉ vì mean delay của nhóm hoàn thành thấp.
- Muốn phân biệt tác động lên dân hiện hữu, báo chỉ số cohort background riêng
  và cohort project riêng; không đổi mẫu số rồi coi là cải thiện toàn mạng.

MVP không suy ra time-of-day counts của cả vùng từ một camera. Bước counting
tích hợp sau chỉ hiệu chỉnh các edge/window có coverage và sai số đã kiểm chứng.

### 8.3 Mưa–thoát nước

- Mỗi parcel/bề mặt là subcatchment, có outlet, rainfall và tham số thấm.
- Các parcel cùng lưu vực nối vào graph cống/nút/hồ/cửa xả chung.
- Dòng chảy từ phần lưu vực ngoài parcel vẫn có mặt một lần trong baseline.
- Chạy SWMM cả mạng cho mỗi tổ hợp: hydrograph và thời điểm đỉnh của các
  project có thể chồng nhau; không cộng các giá trị peak đơn lẻ.
- Xuất node overflow volume/duration, water level và link flow theo thời gian;
  kiểm tra continuity và cấu hình biên.
- Khi thiếu mạng thật: tạo pilot graph nhất quán cao độ/đường kính/kết nối,
  giữ graph giữa các option, gắn `synthetic_network`. Không suy vị trí cống
  thật chỉ từ đường OSM; DEM thô không tạo được cao độ đáy cống.

Nước thải tính nhu cầu riêng; chưa tự đổ vào mạng mưa. Ngập 2D/triều và áp lực
mạng nước vẫn ngoài phạm vi MVP nếu chưa có solver/dữ liệu phù hợp.

### 8.4 Điện, nước và nước thải

- Tính từng dự án theo cùng trục giờ, cộng theo vùng phục vụ được khai báo.
- `peak_power = max_t(sum_i(power_i(t)))`, không cộng các peak khác giờ.
- Capacity là dữ liệu của vùng/asset dùng chung, không nhân spare capacity
  theo số dự án. Tách capacity, baseline load và remaining capacity.
- Không có zone mapping thì báo nhu cầu tổng vùng nghiên cứu; chưa kết luận
  một trạm điện/ống cụ thể quá tải. Vùng phục vụ tổng hợp phải có nhãn.
- MVP chỉ screening năng lực; không gọi đây là power flow/áp lực nước.

### 8.5 Dịch vụ, dân cư và tiếp cận

- Tách nhóm dịch vụ và đơn vị: chỗ học theo nhóm tuổi, năng lực y tế theo
  loại chỉ tiêu, tiếp cận công viên. Không cộng chúng vào một capacity chung.
- Dân số nền từ raster phải clip/tổng hợp theo vùng duy nhất, ghi phương pháp
  phân bổ pixel; không cộng nhiều bbox chồng nhau.
- Khi chỉ có vị trí: báo khoảng cách/thời gian đi bộ trên graph và người trong
  vùng tiếp cận theo giả định; không tuyên bố thiếu bao nhiêu chỗ học.
- Khi có capacity/occupancy: phân bổ nhu cầu tới facility có thể tiếp cận với
  giới hạn capacity. Mỗi người/nhóm nhu cầu phân bổ một lần trong mỗi loại
  dịch vụ; không để A và C cùng dùng một chỗ trống.
- Capacity chưa biết có thể chạy low/base/high công khai. Module trường học
  đầu tiên được ưu tiên; các dịch vụ khác thêm khi có schema riêng.

### 8.6 Đất phủ, bóng đổ và hình học

Union polygon trước khi tính tổng diện tích, tỷ lệ xanh, tán cây và bóng đổ;
không lấy tổng phần trăm hoặc cộng bóng chồng nhau. Dùng cùng vùng đánh giá,
ngày/giờ và đối tượng nhận bóng. Project bị thay thế phải bị loại khỏi geometry
hiện trạng. Chưa suy ra giảm nhiệt độ từ phần trăm bóng mát.

## 9. Hợp đồng dữ liệu dự kiến

Thêm package `app/services/simulation/planning/` dùng lại kernel hiện có.
Không thay ý nghĩa `IntegratedRequest` hoặc kết quả run 1.4 đã lưu.

```text
PlanningStudy
  schema_version, mode: site_selection | cumulative
  title, study_area, snapshot_manifest_id, conditions, seed_suite
  comparison_policy, criteria, objectives
  projects[]: id, site, baseline_policy, development, provenance
  options[]: id, active_project_ids[], program_targets
  phases[]: id, active_project_ids[], background_scenario_id
  service_zones[], catchment_bindings[], utility_zone_bindings[]
```

Trường binding nâng cao do hệ thống/mẫu cung cấp, người dùng chỉ xác nhận khi
có hồ sơ. Project overlap bị từ chối trong MVP; hai thiết kế trên cùng parcel
chỉ được phép là options loại trừ nhau. Không dùng bounding box bao tất cả
parcel như diện tích xây dựng của danh mục.

```text
PlanningResult
  study_id, revision_id, context_hash, status
  baseline, options[], phases[]
  comparisons[], marginal_effects[], interaction_effects[]
  metrics: before/after/delta/unit/scope/time/provenance/comparability
  spatial_artifacts: roads, nodes, catchments, service_access, shadows
  validity, coverage, assumptions, unavailable_modules, runtime
  child_run_ids[], engine_versions, artifact_manifest
```

Mỗi feature GeoJSON có `study_id`, `option_id`/`phase_id`, `project_id` khi
áp dụng, source/engine object ID, time window, unit và provenance. Kết quả
theo thời gian trả bằng artifact phân trang/chunk, tránh nhét toàn bộ vào GeoJSON.

## 10. API, job và lưu trữ

Hợp đồng endpoint mục tiêu dưới đây: một phần đã có trong router
`planning_scenarios.py`, cần nghiệm thu theo các giai đoạn bên dưới trước khi
bàn giao. Những trường trạng thái/khả năng nâng cao vẫn là yêu cầu cần hoàn thiện.

| API | Chức năng |
|---|---|
| `POST /api/v1/planning/studies/preflight` | Kiểm tra geometry/coverage/comparability, dự toán số lượt solver |
| `POST /api/v1/planning/studies` | Lưu study revision, trả ID; không tự chạy solver |
| `GET /api/v1/planning/studies/{id}` | Đọc input, snapshot manifest và revision |
| `POST /api/v1/planning/studies/{id}/runs` | Tạo job screening/native, trả 202 và job ID |
| `GET /api/v1/planning/jobs/{id}` | Tiến độ từng option/module, lỗi và trạng thái |
| `POST /api/v1/planning/jobs/{id}/cancel` | Hủy job và tiến trình solver con thuộc job |
| `GET /api/v1/planning/runs/{id}` | Bảng so sánh/tổ hợp/giai đoạn và thông tin nguồn |
| `GET /api/v1/planning/runs/{id}/map` | GeoJSON theo option/phase, layer và cửa sổ thời gian |
| `GET /api/v1/planning/runs/{id}/artifacts` | Manifest/link tải JSON, CSV, GeoJSON, ZIP input/output |

Job có queued/running/succeeded/partial/failed/cancelled, timeout từng solver,
heartbeat và giới hạn concurrency. Option lỗi không biến thành metric 0; run
partial không được xếp hạng như run hoàn chỉnh. Chỉ restart child job chưa
hoàn thành, không chạy lại toàn study vô điều kiện.

Dùng worker riêng và hàng đợi bền vững: PostgreSQL cho môi trường có warehouse;
SQLite cho local nếu không có Postgres. Không chỉ dùng BackgroundTasks trong
request để đảm bảo job sống qua API restart. Tạo bảng study/revision/job/run
riêng; artifacts nằm trong storage của service với checksum và chính sách giữ.

Run bất biến, input thay đổi tạo revision; idempotency key gắn với input hash.
Cache theo context, design, network, điều kiện, engine version và seed, không
chỉ theo parcel ID. Model/coverage thay đổi phải mất cache tương ứng. API tải
artifact dùng ID hợp lệ và quyền truy cập hiện có của hệ thống, không nhận
đường dẫn file/URL tùy ý từ frontend.

## 11. Độ nhạy, seed và cách diễn giải

- Reuse catalog hệ số đã có; thêm ID cho capacity vùng, service allocation,
  OD nội bộ và các binding tổng hợp.
- Screening dùng 1 seed; shortlist ban đầu dùng ít nhất 3 seed ghép cặp cho
  baseline/options. Đây là phép kiểm tra biến thiên, chưa mặc định đủ hiệu chỉnh.
- Tạo random stream ổn định theo background/project/seed; thêm project B
  không làm toàn bộ giờ xuất phát ngẫu nhiên của A/background đổi ngoài ý muốn.
- Thử low/base/high cho tham số thiếu nguồn và ghi danh sách tổ hợp đã chạy.
  Không gọi min/max của vài case là khoảng tin cậy thống kê.
- Phân biệt sai số input và biến thiên ngẫu nhiên solver. “Hơn 0,2 giây” chưa
  đủ xếp hạng nếu chênh lệch không ổn định hoặc nhỏ hơn ngưỡng ý nghĩa do study chọn.
- Số nhà ở/trường học là lợi ích phục vụ; nhu cầu điện tăng không tự đồng nghĩa
  phương án xấu. Đánh giá áp lực theo mục tiêu, capacity và mức chắc chắn.

## 12. Cấu trúc file dự kiến

```text
backend/app/services/simulation/planning/
  models.py                 schema study/project/options/phases/results
  context.py                nền chung, coverage, manifest và hash
  baseline.py               ledger hiện hữu/thay thế/di dời
  screening.py              geometry/demand/access screening
  comparison.py             cùng điều kiện, delta, Pareto/comparability
  portfolio.py              tổ hợp dự án và giai đoạn
  traffic.py                nhiều connector/OD trên một mạng SUMO
  drainage.py               nhiều subcatchment trên graph SWMM chung
  utilities.py              cộng profile theo giờ và vùng phục vụ
  services.py               routing/phân bổ capacity theo nhóm dịch vụ
  spatial.py                union geometry và map artifacts
  uncertainty.py            seed/assumption cases và stability
  jobs.py                   điều phối, timeout/cancel/retry/cache
  store.py + schema.sql     study/job/result persistence
backend/app/routers/planning_scenarios.py
scripts/planning-worker.py
scripts/prepare-planning-study.py
scripts/test-planning-studies-local.py
backend/tests/test_planning_*.py
docs/samples/planning-site-selection.json
docs/samples/planning-cumulative.json
docs/planning-simulation-api-handoff.md
```

Refactor phần dùng chung trong `integrated/` theo adapter, giữ single-site
API hoạt động. Không copy toàn bộ engine sang package mới rồi để hai bản lệch
logic. Những hàm thuần demand/geometry tiếp tục dùng chung; network builders,
solver runners và extractors được tách để nhận context tổng quát.

## 13. Thứ tự triển khai và nghiệm thu

Ước lượng dưới đây là ngày công kỹ thuật, chưa gồm thời gian chờ nguồn dữ liệu
hoặc tích hợp frontend. Điều chỉnh sau benchmark; không phải cam kết lịch.

| Giai đoạn | Công việc | Bàn giao/điều kiện xong | Ước lượng |
|---|---|---|---:|
| A | Study schema, nền chung, ledger, criteria, job/storage | Preflight và revision bất biến; không trùng baseline | 3–4 ngày |
| B | Screening A/B/C, equal-program, API so sánh | Bảng và GeoJSON; option thiếu dữ liệu được chặn đúng | 2–3 ngày |
| C | SUMO nhiều connector, so vị trí cùng mạng/giờ; shadow; nguồn SWMM | Baseline + 3 vị trí; cùng cohort/background/seed | 3–5 ngày |
| D | Demand/geometry cộng dồn, zone capacity, service theo loại | A/B/C và các tổ hợp; peak giờ đúng, capacity dùng chung | 3–4 ngày |
| E | SUMO portfolio, SWMM graph chung, phases | Hai dự án cùng gây ảnh hưởng một nút; phase tái hiện được | 4–6 ngày |
| F | Sensitivity, artifacts, API handoff, kiểm thử end-to-end | Báo cáo giới hạn/dữ liệu và fixtures cho frontend | 2–3 ngày |

Tổng ước lượng ban đầu là 17–25 ngày công cho toàn phạm vi, không phải số ngày
còn lại từ trạng thái backend thử nghiệm hiện tại. Bản demo hẹp có thể bàn giao
theo mốc: A+B trước, C cho so vị trí, D+E cho cộng dồn. Nếu cần rút gọn, giảm
số module native/tổ hợp trước; vẫn phải có ít nhất một mạng dùng chung để
chứng minh tính tương tác cộng dồn.

**Ưu tiên kế tiếp cụ thể:** A+B với 3 khu đất và cùng 200 căn/600 cư dân; sau đó
C và cộng dồn traffic/nhu cầu D. SWMM dùng mạng tổng hợp công khai nếu chưa có
mạng cống thật. Không chờ camera counting phủ toàn vùng mới bắt đầu.

## 14. Các kiểm thử có ý nghĩa

1. Cùng site/design/input đổi tên hoặc thứ tự project vẫn cho kết quả tương
   đương trong tolerance của solver; hash không phụ thuộc thứ tự không có ý nghĩa.
2. Equal-program không cho option tự giảm số căn/người để cải thiện thứ hạng.
3. Cùng giờ/mưa/source version; thiếu coverage vùng ảnh hưởng bị chặn trước solver.
4. Baseline cư dân/đường/POI/catchment chồng nhau được tính một lần; công trình
   bị phá bỏ biến mất khỏi geometry và load ledger.
5. Hai peak điện khác giờ cho peak tổng bằng max của tổng profile, không bằng
   tổng peak. Một capacity chung không được dùng lại độc lập cho từng dự án.
6. Hai khu cùng có nhu cầu trường học không được phân bổ vượt số chỗ trống.
7. SUMO: vehicle conservation, namespace không trùng, không route qua project
   inactive, không âm thầm bỏ chuyến không tìm được đường; báo failure/coverage.
8. SWMM: continuity, outlet hợp lệ, lưu vực ngoài parcel không mất/đếm đôi;
   case hai hydrograph cùng đỉnh gây kết quả khác cộng hai peak đơn lẻ.
9. Tổ hợp một project tương đương single-site với cùng nền; tổ hợp rỗng bằng
   baseline; A+B và B+A bằng nhau khi không có chính sách thứ tự khác nhau.
10. Phase {A,B} bằng chạy riêng option {A,B} trên cùng nền; không mang gấp đôi
    load của A từ phase trước sang.
11. Thiếu capacity trả unknown/scenario-only; không nâng synthetic thành observed;
    delay có unfinished trips không được xếp hạng thiếu điều kiện.
12. Job cancel/timeout/restart giữ artifact nhất quán, idempotency không tạo
    duplicate solver run, cache invalidates đúng khi đổi context/version.
13. Giữ regression single-site API và tests hiện có. Native tests dùng solver
    thật cho case nhỏ; không chỉ mock để tuyên bố tương tác đã hoạt động.

Với 3 dự án, có thể dùng 8 trạng thái gồm rỗng và mọi tổ hợp trong fixture
screening. Native mặc định chạy baseline, từng dự án, full portfolio và các
phase cần thiết; deduplicate các tập giống nhau. Không mặc định mở rộng 2^N
cho danh mục lớn. Kiểm tra marginal theo shortlist, không hứa tìm tối ưu toàn cục.

## 15. Kịch bản trình diễn và điều kiện công bố

**Demo so vị trí:** chọn A/B/C, nhập cùng chương trình nhà ở, xem nguồn và
screening, chạy shortlist, bật layer đường/dịch vụ/bóng đổ và bảng trade-offs.
Không chuẩn bị sẵn kết quả để B luôn thắng; engine phải tạo ra kết quả thực.

**Demo cộng dồn:** bật A, thêm B, thêm C trên cùng study. Hiển thị nhu cầu cộng
theo giờ, đường/nút chịu tác động, phần tăng thêm của từng giai đoạn và dữ liệu
đang giả định. Một fixture tổng hợp được thiết kế gần ngưỡng có thể chứng minh
hai dự án cùng vượt ngưỡng; phải ghi rõ đây là tình huống thử tổng hợp.

Điều kiện bàn giao:

- Có input/output và artifacts tái hiện được cho cả hai demo.
- Backend trả dữ liệu đủ cho frontend dùng layer chung; không xây lại bản đồ.
- Có ít nhất một ví dụ tương tác chạy native trên mạng chung, không chỉ tổng
  số nhu cầu; không bắt buộc mọi dataset thực đều phải tạo ùn tắc/ngập.
- Báo rõ kết luận nào phụ thuộc dữ liệu thật, model estimate hoặc synthetic.
- Chưa tuyên bố “sức chứa tối đa của đô thị” hay đủ cơ sở phê duyệt quy hoạch
  khi capacities/OD/cống còn giả lập.

Tài liệu liên quan: [kế hoạch single-site](integrated-building-impact-plan.md),
[map context handoff](simulation-map-context-handoff.md),
[hệ số và sensitivity](simulation-demand-coefficients.md),
[kết quả counting](traffic-counting-server152.md).

## 16. Kế hoạch thực hiện chi tiết từ trạng thái repo hiện tại

Mục này trả lời yêu cầu lập kế hoạch cho phần 2 và 3. Code local đã có nhiều
thành phần trong mục 12; cần hoàn thiện và nghiệm thu trên nền đó. Các mốc ở
đầu tài liệu là lịch sử. Bằng chứng mới nhất: regression 108 test trước chỉnh
comparison unknown; 30 focused test và live HTTP sau chỉnh null; browser 15
nhóm; native đủ tám tập và hai thứ tự triển khai. Chưa thay audit toàn bộ bằng
số test. Xem bản kế hoạch dễ đọc ở đầu tài liệu và audit để biết phạm vi.

### Bảng đọc nhanh

| Phần | Quyết định mà planner cần hỗ trợ | Demo nghiệm thu |
|---|---|---|
| 1 — một khu đất | Đổi công năng/quy mô tại khu này có tác động gì? | Giữ case chung cư Thủ Đức hiện có làm regression |
| 2 — vị trí thay thế | Cùng chương trình phát triển nên đặt ở A, B hay C? | Baseline chung, ba phương án, bảng đánh đổi và layer theo vị trí |
| 3 — phát triển cộng dồn | Khi A/B/C cùng hoạt động, điểm nghẽn ở đâu và nên đưa dự án nào vào trước? | Tổ hợp chạy trên mạng chung, so giai đoạn và tải tăng thêm |

Phần 1 đủ cho demo cơ bản trong phạm vi giả định đã công bố. Xác nhận này
không phải một lượt test mới hoặc xác nhận độ chính xác địa phương. Với phần
2/3, triển khai tiếp trên package `planning/` đang có; các bảng bên dưới là
kế hoạch hoàn thiện và nghiệm thu, không phải danh sách mọi thứ chưa viết.

### Dữ liệu chuẩn bị cho hai case

| Dữ liệu | Cách chuẩn bị | Khi chưa có dữ liệu địa phương |
|---|---|---|
| Parcel và building plan A/B/C | Polygon từ map; công năng, số căn/người/GFA, bề mặt từ plan | Dùng fixture hợp lệ và ghi nguồn synthetic |
| Hiện trạng dân số/công trình | Snapshot của hệ thống; khai báo giữ/phá và occupancy | Unknown hoặc case tổng hợp; không mặc định đất trống |
| Đường và kết nối | Snapshot mạng đường của nhóm/OSM; kiểm tra topology và phạm vi ảnh hưởng | Mạng synthetic để kiểm thử solver, tách khỏi kết luận tại vị trí thật |
| Lưu lượng/OD/đèn tín hiệu | Dữ liệu có road ID, hướng, giờ; OD và pha đèn được xác nhận nếu có | Profile/OD/pha đèn synthetic có phiên bản; thử low/base/high |
| Mưa và thoát nước | Trận mưa dùng chung; lưu vực, cống, cao độ và outlet | Graph SWMM synthetic; không gọi kết quả là dự báo ngập thực tế |
| Điện/nước/nước thải | Thư viện hệ số hiện có, profile theo giờ và vùng phục vụ | Nhu cầu ước tính; capacity synthetic hoặc unknown |
| Trường học | POI/vị trí, graph đi bộ, công suất còn trống, nhóm nhu cầu | Công suất và nhu cầu synthetic; POI đơn thuần không chứng minh số chỗ |
| Bóng đổ | Geometry/height, cùng ngày giờ, cùng vùng nhận bóng | Geometry synthetic có nhãn; không chuyển bóng đổ thành nhiệt độ |

Đóng băng các dữ liệu trên thành một snapshot/context trước khi chạy. Nếu
tổng vùng đã chứa các parcel đăng ký, phải tách phần đóng góp của parcel bằng
adapter và kiểm tra ledger trước khi thêm tải phương án; không trừ theo phỏng
đoán. Code hiện có adapter `background.py`; cần kiểm chứng theo đúng nguồn
nhóm bàn giao. Dữ liệu mới tạo revision/context mới.

### Checklist thực hiện và kết quả phải bàn giao

1. **Chốt nền:** chuẩn bị hai fixture, manifest nguồn, ledger hiện trạng,
   phạm vi từng module và lỗi preflight. Bàn giao input JSON có thể mở lại.
2. **Phần 2 screening:** baseline + A/B/C cùng chương trình; bảng nhu cầu,
   tiếp cận và bề mặt. Chặn so sánh khi quy mô hoặc dữ liệu không tương thích.
3. **Phần 2 native:** SUMO/SWMM trên nền chung; ba seed ghép cặp và case độ
   nhạy. Bàn giao bảng đánh đổi, trạng thái ranking và artifact solver.
4. **Phần 3 tải dùng chung:** chạy tập rỗng và các tổ hợp; cộng profile theo
   giờ, phân bổ chỗ học một lần, giữ ledger trước/trừ/thêm/sau.
5. **Phần 3 native/giai đoạn:** SUMO và SWMM chung cho danh mục active;
   tính marginal và interaction, so thứ tự đưa dự án vào vận hành.
6. **Bàn giao:** API examples, JSON/CSV/GeoJSON/ZIP, hướng dẫn local, lỗi và
   trạng thái job; chạy regression phần 1 và end-to-end hai case. Frontend
   nhóm tích hợp lên map chung theo hợp đồng API.

Quy ước kết quả cho một metric có cùng đơn vị/phạm vi/thời gian:

```text
delta(S) = result(S) - result(baseline)
marginal(B | A) = result(A+B) - result(A)
interaction(A,B) = delta(A+B) - delta(A) - delta(B)
peak điện vùng = max theo giờ của [background + tổng tải các project active]
```

Interaction dùng để nhận diện tác động phi tuyến, không tự chuyển thành điểm
"tốt/xấu". Với delay trung bình, phải kiểm tra cohort và số chuyến hoàn thành
trước khi diễn giải chênh lệch. Trường mới tăng nhu cầu điện nhưng đồng thời
giảm thiếu chỗ học: trình bày hai tác động và mục tiêu người dùng chọn.

Các mục 16.2–16.5 dưới đây quy định công việc chi tiết và cổng nghiệm thu cho
từng bước. Ưu tiên hoàn thiện luồng hai bài toán trước, sau đó mới hiệu chỉnh
bằng counting/capacity/cống địa phương; AI giải thích tiếp tục hoãn.

### 16.1 Chốt phần 1 làm nền

Phần 1 **đủ cho demo cơ bản một khu đất** trong phạm vi dữ liệu và giả định đã
công bố. Giữ một case chung cư Thủ Đức làm regression: chọn parcel, nhập plan,
đánh giá hiện trạng/sau xây, xem nguồn và tải kết quả. Mỗi thay đổi ở phần 2/3
phải giữ case này hoạt động. Chưa coi kết quả synthetic là dự báo đã hiệu chỉnh
để quyết định quy hoạch thực tế.

Trong phạm vi backend của chúng ta, người dùng tập trung nhập công năng/quy
mô, chọn khu đất và mục tiêu quy hoạch. Vị trí cổng/hình khối chi tiết chỉ là
đầu vào bổ sung khi có hồ sơ; không bắt buộc biến demo thành công cụ thiết kế
kiến trúc. Hệ thống tự cung cấp dữ liệu nền hoặc giả định có nhãn, cho phép mở
các tham số nâng cao khi cần kiểm tra độ nhạy.

### 16.2 Mốc chung — xác nhận nền dùng chung trước khi so sánh

| Bước | Việc cụ thể | File/module chính | Điều kiện nghiệm thu |
|---|---|---|---|
| N1 | Lập bảng yêu cầu mục 6–15 đối chiếu với code, test và artifact; tách đã có code/chưa kiểm chứng/chưa có | `docs/planning-demo-progress-report.md`, `backend/tests/test_planning_*.py` | Mỗi yêu cầu có bằng chứng hoặc công việc còn lại rõ ràng |
| N2 | Đóng băng AOI, nguồn nền, baseline, mưa/giờ/seed/thư viện hệ số; kiểm tra coverage theo từng module | `context.py`, `models.py` | Các option dùng cùng context; lớp thiếu/ước tính/synthetic được công khai |
| N3 | Rà ledger hiện hữu, phá bỏ/giữ lại, occupancy unknown và di dời; khử trùng parcel/nguồn | `engine.py`, `context.py`, `utilities.py`, `services.py` | Không đếm đôi dân số/tải; thiếu hiện trạng không biến thành 0 đã biết |
| N4 | Đối chiếu job/retry/cache/recovery đã có với cancel/timeout và artifact thực | `jobs.py`, `store.py`, `cache.py`, `recovery.py`, `runner.py` | Retry giữ nguyên input, dùng lại child hoàn chỉnh; không publish run đầy đủ khi còn lỗi |

Hoàn thành N2/N3 trước khi dùng bảng so sánh để diễn giải tác động. N4 là điều
kiện để chạy native ổn định và bàn giao, không thay thế việc xác nhận mô hình.

### 16.3 Phần 2 — chọn vị trí phù hợp cho cùng chương trình phát triển

**Case chính:** cùng chung cư 200 căn/600 cư dân tại A, B hoặc C. Ba phương án
loại trừ nhau. Các vị trí ở cùng AOI và phạm vi mạng đủ phủ; mỗi khu có building
plan phù hợp hình học, giữ cùng mục tiêu GFA và quy mô phục vụ.

1. **Chuẩn hóa input và preflight.** Kiểm tra chương trình bằng nhau, footprint
   trong parcel, tổng bề mặt, hiện trạng từng khu, coverage và điều kiện chung.
   Khu không chứa được chương trình được báo không phù hợp; không tự giảm số
   căn để làm tác động thấp hơn. Thử cả thiết kế thay thế trên cùng parcel.
2. **Hoàn thiện screening.** Trả diện tích/GFA/FAR, nhu cầu điện/nước/nước thải,
   runoff sơ bộ, tiếp cận trường và bề mặt/bóng đổ. Giá đất/lịch sử ngập chỉ là
   thông tin bối cảnh có nguồn. Shortlist do người dùng chọn.
3. **Xác nhận native so sánh công bằng.** Baseline và A/B/C cùng mạng SUMO,
   background OD, giờ và ít nhất ba seed ghép cặp. SWMM dùng đúng binding
   lưu vực/mạng; nếu synthetic thì kết luận theo kịch bản synthetic. Kiểm tra
   connector không tạo đường tắt cho xe nền hoặc gây lợi thế giả cho một site.
4. **Hoàn thiện kết quả phục vụ planner.** Mỗi metric có trước/sau/delta, đơn vị,
   phạm vi, thời gian, phương pháp, nguồn và trạng thái so sánh. Trả Pareto và
   đánh đổi; trọng số chỉ dùng khi người dùng chọn. Delay đi cùng completion,
   backlog và cohort xe nền, không chỉ trung bình các chuyến hoàn thành.
5. **Kiểm tra độ ổn định.** Chạy các giả định low/base/high cho dữ liệu thiếu,
   kiểm tra đổi seed/trọng số có đổi kết luận không. Kết luận không ổn định
   phải được hiển thị; không ép hệ thống chọn một vị trí thắng.
6. **Bàn giao frontend.** JSON mẫu, bảng metric, GeoJSON theo option/giờ/seed,
   job status, lỗi preflight và run có thể mở lại. Frontend nhóm dùng các layer
   này trên map chung. Preview độc lập dùng để kiểm tra hợp đồng backend.

**Nghiệm thu phần 2:** chạy được baseline + A/B/C từ input đã lưu; đổi thứ tự
option không đổi kết quả; đổi program không hợp lệ bị chặn; unknown không bị
thay bằng 0; các layer chỉ đúng option/time; ZIP tái hiện được solver. Có ít
nhất một bảng đánh đổi và một case kết luận nhạy với giả định hoặc seed.

### 16.4 Phần 3 — tác động cộng dồn và thứ tự phát triển

**Case chính:** A là chung cư 200 căn, B là trường 600 chỗ, C là chung cư 150
căn. Có baseline, A, B, C riêng, tổ hợp AB/ABC và các giai đoạn. Công suất
trường/năng lực hạ tầng dùng giả định công khai khi thiếu dữ liệu thực.

1. **Danh mục và trạng thái giai đoạn.** Mỗi dự án có parcel, baseline policy,
   plan và binding vùng/lưu vực. Phase là tập dự án đang hoạt động, không cộng
   lại load của phase trước. Các thiết kế trên cùng parcel không được cùng
   hoạt động. Không suy ra thay đổi nền theo năm khi chưa có giả định riêng.
2. **Nhu cầu và capacity chung.** Cộng điện/nước/nước thải theo cùng thời điểm
   và vùng phục vụ, rồi lấy peak. Trừ tải hiện hữu bị thay thế một lần. Trả
   khoảng thiếu/vượt công suất theo nguồn capacity; unknown vẫn là unknown.
3. **Phân bổ dịch vụ chung.** Nhu cầu trường của A/C và dân nền cùng sử dụng
   một danh mục trường. Mỗi chỗ học được dùng một lần; thêm trường B làm thay
   đổi khả năng phục vụ. Y tế/công viên chỉ thêm khi có schema nhu cầu và
   capacity riêng; chưa có thì liệt kê unavailable, không trộn đơn vị.
4. **Giao thông tương tác thật trong mô hình.** Chạy toàn bộ dự án active trên
   một mạng SUMO, background một lần. Báo đường/nút ảnh hưởng, xe nền, queue,
   completed/unfinished/undeparted. External-OD-only phải ghi rõ; thêm chuyến
   A→B sau khi có ledger bảo đảm một chuyến không bị tính ở cả hai đầu.
5. **Thoát nước và hình học chung.** Parcel trong cùng lưu vực vào graph SWMM
   chung, background runoff một lần; kiểm tra continuity, node/link time
   series. Union bóng đổ/bề mặt trên vùng đo cố định. Không cộng các peak tràn
   hoặc phần trăm bóng từ run riêng để tạo kết quả ABC.
6. **So thứ tự và đóng góp tăng thêm.** So P1={A}, P2={A,B}, P3={A,B,C} với
   thứ tự P1={B}, P2={A,B}, P3={A,B,C}, giữ nền và điều kiện tương đương. Trả
   marginal/interaction và phase đầu vượt mục tiêu. Đây là thứ tự vận hành
   giả định, chưa mô phỏng thi công hoặc dự báo đô thị theo năm.

**Nghiệm thu phần 3:** tập rỗng bằng baseline; AB=BA; cùng tập active cho cùng
kết quả dù xuất hiện ở option hay phase; capacity không bị dùng lặp; một
project tương đương mô hình một site khi điều kiện/boundary giống nhau. Có
ít nhất một case native trên mạng chung cho thấy tương tác không bằng cộng
kết quả riêng. Không thiết kế fixture để một phương án luôn thắng.

### 16.5 Thứ tự bàn giao và phạm vi sau demo

| Mốc | Kết quả review được | Cổng chuyển bước |
|---|---|---|
| M0 | Audit N1–N4, fixtures có nguồn/nhãn và lỗi đầu vào rõ | Baseline/coverage và job không còn lỗi cản trở chạy mẫu |
| M1 | Phần 2 screening + so sánh A/B/C + API/layer | Chương trình/điều kiện chung và missing xử lý đúng |
| M2 | Phần 2 native + seed/độ nhạy + artifact | Tái hiện được kết quả, trình bày đúng giới hạn ranking |
| M3 | Phần 3 nhu cầu/capacity/dịch vụ/phase | Không đếm đôi; peak theo giờ và allocation đúng |
| M4 | Phần 3 native SUMO/SWMM tương tác | Conservation/continuity và tương tác được kiểm chứng |
| M5 | Chạy end-to-end hai case, regression phần 1, bàn giao nhóm | Input/result/CSV/GeoJSON/ZIP và hướng dẫn local thống nhất |

Mốc 3 có thể thực hiện song song về mặt kỹ thuật với mốc 2 sau khi nền chung
ổn định; mỗi mốc phải có bằng chứng trước khi ghi hoàn thành. Ước lượng toàn
phạm vi ở mục 13 không phải ước lượng công việc còn lại; cập nhật sau audit M0.

Sau M5 mới ưu tiên counting gắn road/time để hiệu chỉnh lưu lượng, dữ liệu
cống/capacity địa phương và module y tế/công viên riêng. Demo chức năng có
thể dùng dữ liệu synthetic hợp lý, nhưng khi thay bằng nguồn thật phải tạo
context/revision mới và chạy lại. AI giải thích tiếp tục hoãn. Việc tích hợp
map chính thuộc frontend của nhóm; deploy server lập mốc riêng sau khi có
cấu hình vận hành và kết quả local được review.

### Cập nhật triển khai 0.10

[Layer theo thời gian](planning-spatial-timeseries.md) đã bổ sung queue SUMO
theo lane/edge, seed selector và geometry/sample node/link SWMM. Có bằng
chứng native/XML/API/UI local trên instance 8006 riêng. Các yêu cầu còn lại
vẫn theo audit, đặc biệt invariant/corner cases, program-normalized metrics
và packaging/uncertainty end-to-end model hiện tại; chưa nghiệm thu toàn bộ.

### Cập nhật triển khai 0.11

[Normalized program và invariant](planning-program-normalization.md) đã có:
tổng delta và tỷ lệ theo basis khai báo, mixed/zero/unknown được đánh dấu,
JSON/CSV/preview; đủ 8 trạng thái screening. Đổi tên ba parcel không làm đổi
native delay/queue sau sửa identity geometry. Regression 81 test đạt;
packaged Linux và HTTP hai case đã chạy trên Docker API local 8007. Còn
single-site equivalence cùng context, hydrograph/binding corner cases,
uncertainty/PostgreSQL phiên bản hiện tại và audit hợp đồng/nghiệm thu đầy đủ.

### Cập nhật triển khai 0.12

[Hydrograph và độ nhạy](planning-hydrographs-and-current-uncertainty.md):
kiểm tra cùng timestamp/report step, timeline/peak minute, test lệch/trùng
peak và hai catchment native full pipeline. Regression 90 test đạt; CLI
36 SUMO/12 SWMM, API uncertainty cả hai bài toán đã chạy/lưu/ZIP thành công.
Còn single-site equivalence cùng boundary/context, benchmark/preflight,
PostgreSQL hiện tại và audit nghiệm thu đầy đủ, không coi các mốc là toàn bộ.

### 16.6 Danh sách triển khai và nghiệm thu — ghi lại trước audit cuối

Cập nhật cuối: T1–T7 đã có bằng chứng backend/local trong
[audit cuối](planning-demo-final-audit.md). Bảng dưới giữ checklist thực hiện;
frontend map chính/nguồn thực/deploy không được tính là đã hoàn thành.

Đối chiếu ngày 11/10/2026. Mốc mới nhất là
[single-site cùng context 0.14](planning-single-site-common-context.md):
regression 101 test, PostgreSQL hiện tại, packaged Linux/native và HTTP ba
case đã có bằng chứng. [Handoff/guard tiếp theo](planning-series-and-recovery-audit.md)
đã kiểm tra uncertainty hai bài toán, browser 14 nhóm và API chuỗi phân trang.
T1/T2 và phần PostgreSQL của T6 đã tiến triển; vẫn cần audit nghiệm thu toàn
bộ và case end-to-end tổ hợp/thứ tự triển khai. Các bước sau hoàn thiện code
hiện có.

| Thứ tự | Công việc cụ thể | Thành phần phụ trách | Kết quả review được | Điều kiện xong |
|---|---|---|---|---|
| T1 | Hoàn thiện preflight: workload, giới hạn mạng, coverage, số solver và thời gian từ benchmark cùng cấu hình worker | `planning/context.py`, `benchmark.py`, `jobs.py`, `store.py` | JSON preflight, số đo runtime, trạng thái chưa có benchmark | Không dùng số đo khác model/máy/đầu vào để hứa thời gian; job lỗi/hủy không thành mẫu chạy đầy đủ |
| T2 | Chốt tương đương một project giữa luồng single-site và planning khi dùng cùng context/boundary | `integrated/`, `planning/native.py`, tests | Case chung cư Thủ Đức, bảng đối chiếu từng metric và sai số cho phép | Cùng nền, giờ, mưa, seed, mạng và ledger; không so hai mạng mẫu khác nhau rồi kết luận tương đương |
| T3 | Chốt hợp đồng snapshot của nhóm: ID, geometry, source/version, units, coverage, timestamp và contribution hiện trạng | `planning/background.py`, `baseline.py`, `provenance.py` | Mẫu JSON nền, manifest và lỗi dữ liệu | Unknown giữ nguyên; không đếm đôi dân số/tải; snapshot mới tạo revision mới |
| T4 | Nghiệm thu phần 2: A/B/C bằng chương trình, bảng đánh đổi, ranking và độ nhạy | `comparison.py`, `normalization.py`, `uncertainty.py`, API | Run A/B/C, CSV, GeoJSON, ZIP, case ranking không ổn định | Đổi thứ tự/tên không đổi vật lý; metric thiếu không bị điền 0; ba seed được đối chiếu theo cặp |
| T5 | Nghiệm thu phần 3: trạng thái active, tải dùng chung, dịch vụ, native và hai thứ tự triển khai | `engine.py`, `utilities.py`, `services.py`, `traffic.py`, `drainage.py` | Bảng tổ hợp, marginal/interaction, phase đầu vượt mục tiêu | Capacity/nền một lần; AB=BA; cùng tập active cho cùng kết quả; conservation/continuity đạt |
| T6 | Kiểm tra bản hiện tại trên PostgreSQL và image Linux; hủy/retry/cache, lưu/mở lại và artifact | `store.py`, `runner.py`, `recovery.py`, scripts kiểm thử | Report ghi model/engine, job ID, checksum và phạm vi test | Kết quả không thay đổi sau khi lưu; retry không lấy child khác context; không công bố full run khi partial |
| T7 | Bàn giao backend cho frontend map và diễn tập hai case | Router, API handoff, samples, preview | Request/response mẫu, danh sách layer/selector, lỗi và hướng dẫn local | Frontend nối project/option/phase đúng ID, xem trước/sau/delta và mở lại đúng input |

T1–T3 là nền cho kết luận của T4/T5. T4 và T5 dùng chung các bộ phận đã có;
không cần viết hai service solver độc lập. T6 kiểm tra đúng phiên bản sau các
sửa đổi; T7 là cổng bàn giao. Chỉ ghi hoàn thành khi có artifact tương ứng.

#### Cách tính và trình bày theo feature

| Feature | Phần 2: so vị trí | Phần 3: cộng dồn | Đầu ra bắt buộc |
|---|---|---|---|
| Giao thông | Cùng OD nền/giờ/seed, thay nơi phát sinh chuyến của cùng chương trình | Mọi dự án active chạy chung SUMO; theo dõi xe nền và xe dự án | Delay theo cohort, queue theo đường/thời gian, completed/unfinished/undeparted; nguồn OD/đèn |
| Thoát nước | Cùng trận mưa và cấu hình nền; bề mặt từng vị trí đấu nối đúng lưu vực | Chạy SWMM chung theo lưu vực; cộng hydrograph cùng timestamp | Runoff, tràn tại node, flow/depth tại link, thời điểm peak; continuity và nhãn mạng synthetic |
| Điện | So nhu cầu và phần dư công suất vùng phục vụ mỗi vị trí | Cộng profile cùng giờ, lấy peak tổng; không cộng peak riêng | kWh/ngày, kW peak, headroom/vượt công suất hoặc unknown |
| Nước/nước thải | So nhu cầu với vùng cấp/thu gom tương ứng | Nền và tải giữ/trừ/thêm theo vùng; capacity dùng một lần | m³/ngày, thiếu/vượt capacity; hệ số và lịch sử dụng |
| Trường học | So số học sinh chưa được phục vụ và khả năng tiếp cận | Phân bổ nhu cầu nền+A+C vào trường hiện hữu+B một lần | Chỗ thiếu, nhóm được phục vụ, tuyến/khoảng cách đi bộ; capacity có nguồn/giả định |
| Bề mặt/bóng đổ | Cùng vùng nhận bóng, ngày/giờ; so diện tích trước/sau | Union bề mặt và bóng trên trạng thái chung, xử lý công trình bị thay thế | m²/tỷ lệ, layer hình học và thời gian; không gọi bóng đổ là nhiệt độ |

Giá đất, ngập lịch sử và POI có thể làm lớp bối cảnh từ map của nhóm. Chỉ thêm
metric mô phỏng giá đất/nhiệt độ khi có mô hình và cổng kiểm chứng riêng;
không suy rằng mô phỏng xây dựng hiện tại đã dự báo được những đại lượng đó.

#### Giới hạn đầu vào và khuyến nghị cho planner

- Luồng cơ bản: chọn khu đất, công năng, quy mô phục vụ, plan sơ bộ và mục tiêu;
  phần 3 thêm danh mục dự án và tập active theo giai đoạn.
- Dữ liệu nền và hệ số lấy từ hệ thống/thư viện; thông số chưa biết dùng
  kịch bản synthetic công khai hoặc unknown. Mở phần nâng cao để người dùng
  xác nhận occupancy, di dời, capacity hoặc giả định khi có hồ sơ.
- So vị trí ưu tiên cùng chương trình. Nếu người dùng muốn so quy mô khác
  nhau, hiển thị cả tác động tuyệt đối và normalized basis hợp lệ; không xếp
  thấp tải hơn thành tốt hơn khi phương án phục vụ ít người hơn.
- Khuyến nghị ở cấp quy hoạch: đổi vị trí, giảm/tăng quy mô, bổ sung công suất
  dịch vụ/hạ tầng hoặc đổi giai đoạn. Mỗi khuyến nghị cần một phương án chạy
  lại để chứng minh tác động, thay vì chỉ mô tả lợi ích dự kiến.
- Vị trí cổng/hình khối là tham số tùy chọn khi có thiết kế; không phải yêu
  cầu bắt buộc của luồng planner. AI giải thích và counting tiếp tục hoãn.

### 16.7 Hai kịch bản nghiệm thu và gói bàn giao

**Case phần 2 — chọn nơi đặt chung cư:**

1. Nạp A/B/C cùng vùng pilot; mỗi vị trí có plan hợp lệ cho 200 căn/600 cư dân.
2. Khóa snapshot, chương trình, giờ/mưa/seed và tiêu chí; chạy preflight.
3. Chạy screening rồi native cho shortlist; mở baseline và từng option.
4. So áp lực lên xe nền, thoát nước, tải hạ tầng và chỗ học; hiển thị nguồn,
   unknown và Pareto. Chạy độ nhạy để kiểm tra độ ổn định của kết luận.
5. Đổi input tạo revision; mở run cũ vẫn thấy input/kết quả cũ. Tải ZIP.

**Case phần 3 — chung cư, trường học và chung cư bổ sung:**

1. Nạp A=200 căn, B=trường 600 chỗ, C=150 căn; giữ nền/capacity synthetic có nhãn.
2. Tạo baseline và các tập A, B, C, AB, AC, BC, ABC để đủ đối chiếu ba dự án.
3. So thứ tự A→AB→ABC với B→AB→ABC: tính tải toàn trạng thái, marginal của
   dự án thêm vào và phase đầu vượt mục tiêu. Trạng thái AB phải giống nhau.
4. Mở layer đường/nút-cống/trường/bóng của từng trạng thái và thời điểm;
   chứng minh ít nhất một tương tác native khác cộng delta đơn lẻ.
5. Hủy một job rồi retry; kiểm tra lưu kết quả, cache và tải artifact đầy đủ.

Gói bàn giao gồm input JSON của hai case, schema/request/response mẫu, bảng
before/after/delta và chương trình phục vụ, CSV, GeoJSON có metadata, ZIP
solver, report test theo phiên bản, cùng hướng dẫn local. Người làm frontend
tích hợp vào map hiện có; preview là nơi kiểm tra hợp đồng backend.

**Điều kiện kết thúc demo:** hai case trên chạy end-to-end trên phiên bản đã
kiểm tra; phần 1 không regression; các invariant mục 14 được đối chiếu bằng
bằng chứng; giới hạn dữ liệu/mô hình được ghi trong kết quả; nhóm frontend
có đủ hợp đồng để tích hợp. Sau đó mới hiệu chỉnh bằng dữ liệu địa phương và
quay lại object counting.
