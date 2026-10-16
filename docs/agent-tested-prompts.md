# Các prompt đã dùng để kiểm thử AI agent

**Cập nhật hành vi ngôn ngữ:** các prompt 4–6 bên dưới là bản lịch sử đã chạy,
có yêu cầu trả lời tiếng Việt trong câu tiếng Anh. Các script hiện tại đã bỏ
yêu cầu đó: mặc định trả lời theo ngôn ngữ tin nhắn mới nhất; chỉ đổi sang ngôn
ngữ khác khi người dùng yêu cầu rõ. Script `scripts/check-agent-language.py`
kiểm tra đổi tiếng Anh → Việt → Anh trong cùng hội thoại. Bằng chứng lưu tại
`test-results/general-agent/language-result.json`.

Ngày tổng hợp: 15/10/2026. Preview: http://127.0.0.1:8192/.

Đây là **6 prompt nguyên văn còn được xác nhận trong script và bằng chứng kiểm
thử của đợt tích hợp agent Development + agent tổng quát**. Không phải danh sách
prompt ví dụ đề xuất, cũng không khẳng định bao phủ mọi thử nghiệm trong toàn bộ
lịch sử dự án. Prompt 1 và 2 phải chạy nối tiếp trong cùng hội thoại.

## 1. Phân tích vùng bản đồ, tìm và so sánh ba thửa

Điều kiện: không mở plan; viewport đã đặt ở vùng demo Thủ Đức có dữ liệu nền và
parcel. Script gửi viewport thật kèm yêu cầu, không ghi tọa độ vào câu chat.

```text
Không mở plan. Hãy chọn vùng map đang nhìn, phân tích dân số năm 2026 và dữ liệu nền, tìm 3 thửa diện tích 2.000–100.000 m². So sánh cả 3 theo diện tích lớn hơn, mật độ dân số cao hơn (chỉ là proxy nhu cầu), và khoảng cách đường nhỏ hơn; trọng số mỗi tiêu chí là 1. Ghi rõ tiêu chí thiếu và không coi đất là trống. Thực hiện bằng công cụ rồi tóm tắt ngắn.
```

Đã xác nhận gọi thành công `area_select`, `area_analyze`, `candidate_search`,
`candidate_compare`. Lượt kiểm thử lưu gần nhất mất khoảng 25,44 giây.

Nguồn: `scripts/check-general-agent-model.py`;
bằng chứng: `test-results/general-agent/model-workflow.json`.

## 2. Cùng một trường học trên hai ứng viên đầu

Điều kiện: tiếp tục hội thoại của prompt 1. “Hai ứng viên đầu” phải là thứ tự
danh sách tìm kiếm, không phải thứ tự bảng điểm.

```text
Dùng hai ứng viên đầu trong danh sách tìm kiếm vừa rồi. Chuẩn bị và chạy quick estimate cho cùng trường học 100 chỗ, 3 tầng, tổng sàn 600 m², 10 nhân viên, 100 người sử dụng mỗi ngày, cao mỗi tầng 3,2 m, khoảng lùi giả định 1 m, mưa 60 mm. Giữ đúng chương trình ở cả hai đất, không mở plan, chưa cần native. Nếu fit test không đạt thì nói rõ, không giảm quy mô. Trả lời ngắn trạng thái job.
```

Đã chuẩn bị và khởi chạy study cho đúng `1937234`, `1937204`.
Lượt lưu gần nhất mất khoảng 14,35 giây. Model ban đầu gửi sai tên một trường
đầu vào, bị validation từ chối, sau đó tự sửa và tạo study thành công.
Job chạy bất đồng bộ; đây là thời gian câu trả lời, không phải thời gian hoàn tất
mọi tác vụ worker. Kết quả hoàn thành sau đó được kiểm tra trên trình duyệt.

Nguồn: `scripts/check-general-agent-model.py`;
bằng chứng: `test-results/general-agent/model-workflow.json`.

## 3. Đọc kết quả và giải thích so sánh khu đất

Điều kiện: study screening hai khu đất đã được tạo và worker đã hoàn thành bằng
luồng kiểm thử API. Script ghép job ID thật vào câu chat. Dưới đây là câu sau khi
điền ID của lượt đã lưu; khi chạy lại cần thay bằng job thuộc hội thoại hiện tại.

```text
Không cần mở plan. Hãy đọc urban_report và urban_results cho job a07027d3-031d-43d3-bdb2-0afc932fc616, rồi giải thích so sánh các khu đất cho cùng trường học. Nêu nguồn, tiêu chí còn thiếu và không coi đất là trống. Trả lời ngắn bằng tiếng Việt.
```

Đã xác nhận model gọi `urban_report`, `urban_results` và trả lời tiếng Việt với
các giới hạn dữ liệu. Không được dùng job ID từ hội thoại khác để vượt kiểm tra
quyền sở hữu job.

Nguồn: `scripts/check-general-agent.py`;
bằng chứng: `test-results/general-agent/live-result.json`.

## 4. Nhân bản phương án, sửa tòa nhà rồi chạy quick estimate

Điều kiện: plan kiểm thử có một tòa nhà, workspace binding trỏ đúng plan,
scenario và revision. Đây là prompt **có thay đổi dữ liệu** trong preview riêng.

```text
Duplicate the current scenario as "Luna verified alternative". In the duplicate, change the only building to 5 floors, preserving footprint, use and all unspecified fields. Then prepare and start a quick estimate for the whole scenario using defaults. Do not change the original scenario. Reply in Vietnamese with saved revision and job status.
```

Đã xác nhận luồng nhân bản, chỉnh công trình, chuẩn bị và khởi chạy mô phỏng.
Giữ nguyên phương án gốc, lưu thay đổi ở phương án nhân bản.

Nguồn: `scripts/check-development-agent-model.py`;
bằng chứng: `test-results/development-agent/model-write-result.json`.

## 5. Giải thích tòa nhà và kết quả quick estimate đã hoàn thành

Điều kiện: workspace đã gắn plan/scenario và job quick estimate đã hoàn thành.

```text
Use workspace_read and simulation_results to explain my current building and the completed quick result. State what baseline/capacity is missing. Do not edit or run another job. Reply in Vietnamese.
```

Đã kiểm tra trả lời dựa trên workspace và kết quả lưu, có nêu thiếu baseline/
capacity. Prompt này không yêu cầu sửa plan hay chạy job mới.

Nguồn: `scripts/check-development-agent.py`;
bằng chứng: `test-results/development-agent/live-result.json`.

## 6. Chat trực tiếp trên trình duyệt: đọc plan và số tầng

Điều kiện: đã mở plan/scenario kiểm thử trong web. Script bật nhánh
`AGENT_UI_CHAT=1`, nhập câu vào ô chat và nhấn Send.

```text
Use workspace_read to explain the currently selected plan, scenario and its building floor count. Do not edit or start a job. Reply briefly in Vietnamese.
```

Đã lưu phản hồi/trace từ thao tác chat trên trình duyệt.

Nguồn: `scripts/check-development-agent-browser.cjs`;
bằng chứng: `test-results/development-agent/browser-chat.json`.

## Các lượt chat bổ sung

### Bổ sung: 3 prompt kiểm tra ngôn ngữ

Đã chạy nối tiếp trong một hội thoại với model thật, cả ba đạt và đã đọc lại
phản hồi. Không prompt nào chỉ định ngôn ngữ câu trả lời.

```text
In one short sentence, what can you help me do on this urban planning map? Do not call tools.
```

Kết quả: tiếng Anh.

```text
Trong một câu ngắn, bạn có thể giúp tôi làm gì trên bản đồ quy hoạch này? Không gọi công cụ.
```

Kết quả: tiếng Việt.

```text
What is your role on this map? Give one short sentence without calling tools.
```

Kết quả: chuyển lại tiếng Anh, không bị giữ theo lượt tiếng Việt trước đó.

### Bổ sung: 2 prompt kiểm tra dataset

Đã chạy bằng model thật, không ép ngôn ngữ trả lời; cả hai phản hồi bằng tiếng
Anh. Điều kiện: viewport demo Thủ Đức đã chọn, có nguồn parcel/giá đất và POI.
Lượt mới nhất còn gửi snapshot 233 POI thật đã lấy từ trình duyệt của system.

```text
What are the land price references in the selected area? Show prices, units and effective dates.
```

Model gọi thành công `layer_query`; nêu giá tham chiếu VND/m², ngày hiệu lực và
cảnh báo các phép ghép tự động/chưa kiểm duyệt, tên đường nguồn khác đường hiển thị.

```text
Find me a place to build a house for 4 people. It should be near supermarkets, parks, and hospital.
```

Model gọi thành công `amenity_site_search`. Vùng kiểm thử không có ứng viên đạt
hết các khoảng cách trong mẫu 25 thửa, nên trả phương án gần đạt có nhãn, không
tuyên bố là đất trống hay đủ điều kiện xây nhà. Dữ liệu POI bổ sung dùng extract
OSM thật, không tạo giả. Nhà bốn người vẫn cần thêm ngân sách/quy mô/công năng
trước khi kết luận thiết kế phù hợp hoặc chạy mô phỏng.

Nguồn: `scripts/check-agent-datasets.py`;
bằng chứng: `test-results/general-agent/datasets-result.json`.

## Kiểm thử đường/hẻm và phạm vi

### Street/alley and scope regression

Script: `scripts/check-agent-street-search.py`; evidence:
`test-results/general-agent/street-search-result.json`. These two turns are run
in the same conversation, deliberately keeping the visible map at unrelated
Thủ Đức coordinates:

```text
tìm khu vực để xây căn nhà 4 tầng ở hẻm 114 đường trần quốc tuấn quận gò vấp
```

Expected: resolve the named alley from actual warehouse road geometry, then search
source parcels in a disclosed 100 m buffer; do not assume the visible map is the
requested location, or that four floors are legally permitted.

```text
tìm những khu vực gần bệnh viện, công viên để xây nhà
```

Expected: ask whether to continue the saved area or select a district/neighborhood;
do not silently launch a new candidate search in the previous area/viewport.
The backend now enforces this at the model tool boundary, not only in instructions.
Earlier dataset prompts without geographic scope are historical tests; current
`check-agent-datasets.py` adds “in the currently selected area” to explicitly reuse
the selected extent. Direct manual area-selection tools remain explicit user actions.

## Phần kiểm thử không có prompt chat

- Các kiểm thử backend (hiện 41 bài) gọi hàm/tool trực tiếp để kiểm tra validation, dữ liệu
  thiếu, công thức xếp hạng, quyền sở hữu và tính nhất quán đầu vào. Không phải
  22 prompt ngôn ngữ tự nhiên.
- Luồng API kiểm thử còn gọi tool trực tiếp để chuẩn bị dữ liệu, study và job.
  Các tham số này nằm trong script, không được tính thành prompt chat.
- 9 kiểm tra trình duyệt của agent tổng quát dùng hội thoại/kết quả đã lưu để
  kiểm tra UI, bảng, báo cáo, reload và mobile. Không gửi thêm 9 prompt tới model.
- Các câu ví dụ trong README/hướng dẫn không mặc nhiên là câu đã chạy qua model.
- Danh sách này không chứa system prompt hoặc schema tool. Chúng là cấu hình
  agent trong `backend/app/services/agent/service.py` và `tool_schema.py`.

Các bằng chứng JSON/ảnh trong `test-results` là artifact local; một số file bị
ghi đè khi chạy lại. Không có bản lưu riêng cho mọi lần thử thất bại/trung gian.
