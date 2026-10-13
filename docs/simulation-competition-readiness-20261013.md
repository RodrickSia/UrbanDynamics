# Đánh giá sức cạnh tranh của simulation — 13/10/2026

## Nhận định

**Đã có nền tảng để làm một demo cạnh tranh; chưa đủ bằng chứng để đánh giá là ứng viên thắng track.** Điểm mạnh là luồng ra quyết định theo parcel và tác động cộng dồn. Rủi ro lớn là kết quả còn phụ thuộc giả định, kiểm chứng thực địa ít, và phần simulation chưa được nghiệm thu trong frontend chính của nhóm.

Đánh giá này dành cho phần simulation đã kiểm tra, không phải chấm điểm toàn bộ sản phẩm của nhóm hay dự đoán thứ hạng. Không có thông tin về sản phẩm các đội đối thủ hoặc phản hồi người dùng đủ để suy ra khả năng thắng.

## Đối chiếu đề bài chính thức

Nguồn: [Vietnam Map Challenge — đề bài Tasco](https://docs.google.com/document/d/11fRaBedWrh4XwWld9_dqoMTgj-lNi88Buzr5y3i0QOE/edit). Đề bài có hướng quy hoạch/hạ tầng và cho phép dữ liệu synthetic/mock đại diện cho dữ liệu có thể được các cơ quan chia sẻ.

| Tiêu chí BTC | Tối đa | Đánh giá phần simulation |
|---|---:|---|
| Giải quyết vấn đề và tác động | 20 | Có use case so sánh địa điểm/quy mô/giai đoạn; cần một ví dụ cho thấy kết quả làm thay đổi quyết định của planner |
| Phù hợp Việt Nam | 15 | Parcel địa phương, OSM, xe máy và bối cảnh thiếu dữ liệu phù hợp; cần làm rõ phạm vi và cách triển khai khi được cấp dữ liệu |
| Sáng tạo, khác biệt | 20 | Nối bản đồ với what-if và tác động cộng dồn có giá trị; chưa chứng minh tính mới so với các sản phẩm khác |
| Dữ liệu và AI | 20 | Nguồn bất biến, provenance và detector/tracking có sẵn; cần đo sai số counting và trình diễn liên kết AI → dữ liệu → kết quả simulation |
| Khả thi và demo | 15 | Có API/worker, solver native và kết quả lưu; cần luồng tích hợp frontend chính, thời gian đáp ứng và cơ chế vận hành rõ ràng |
| Trình bày và UX | 10 | Demo kiểm thử có map và deep link; chưa nghiệm thu trải nghiệm cuối cùng của cả nhóm |

Các đánh giá trong cột cuối là nhận định kỹ thuật của chúng ta; không phải điểm BGK.

## Bằng chứng đang có

- Chọn nhiều parcel thật từ snapshot hệ thống; nhập building plan; cùng chương trình khi so vị trí; tạo các kịch bản xây riêng/xây cùng và giai đoạn.
- SUMO trên topology OSM; SWMM; demand điện/nước/nước thải theo hệ số; bóng đổ theo geometry; đường đi bộ tới điểm trường OSM. Có so sánh và nguồn/giả định đi kèm.
- WorldPop, ESA WorldCover và footprint OSM đã được freeze trong bối cảnh. Có cảnh báo công năng quy hoạch có thể xung đột.
- Counting pretrained + tracking đã visualize 3 clip test trên 152, có bounding box và sự kiện qua vạch: 17/19/13 lượt. Chưa có ground truth độc lập để báo cáo độ chính xác counting.
- Lưu lượng mặc định mới: 19 lượt/16,67 giây → 4.104 xe/giờ tổng hai hướng. SUMO hai lớp ô tô/xe máy nhận proxy 3.888 xe/giờ. Đây là giả định chuyển từ clip ngắn, không phải lưu lượng quan trắc từng đường hoặc OD đã hiệu chỉnh.

## Những điểm có thể làm mất sức thuyết phục

### Case mới sau khi cập nhật lưu lượng

[Mở demo đã lưu](http://127.0.0.1:8007/simulation/planning?job=7ae2d330-34b8-4389-94fc-7b77ab8219ca&option=together_3).

Job `7ae2d330-34b8-4389-94fc-7b77ab8219ca`, run `dc054c7a-5199-4d56-bae2-2fb0ea2595c4`: parcel 1959486/1958467/1958799, 5 options/3 phases, giờ 18, seed 2026. Hoàn tất sau retry với giới hạn solver 600 giây; bảo toàn số xe SUMO và cân bằng SWMM đạt. Nền cố định 216 ô tô + 3.672 xe máy/giờ. Dữ liệu và kết quả lưu ở `test-results/planning-flow-default/`.

| Phương án | Xe dự kiến | Hoàn thành | Tồn đọng cuối lượt | Trễ TB xe hoàn thành (s) | Hàng chờ tối đa (m) |
|---|---:|---:|---:|---:|---:|
| P1 riêng | 3.895 | 2.782 | 1.113 | 37,92 | 357,11 |
| P2 riêng | 3.895 | 3.710 | 185 | 42,48 | 99,02 |
| P3 riêng | 3.895 | 3.459 | 436 | 40,45 | 463,14 |
| P1 + P2 | 3.902 | 3.902 | 0 | 42,66 | 38,11 |
| Cả 3 | 3.909 | 3.909 | 0 | 43,44 | 41,61 |

Tồn đọng gồm xe đã vào nhưng chưa hoàn thành và xe chưa vào mạng; lượt mô phỏng kết thúc ở giây 4.200. Các con số thuộc mô hình giả định, không phải quan trắc tại những parcel này. P1 riêng có delay thấp hơn nhưng hơn 1.000 xe chưa hoàn thành, nên không được diễn giải thành phương án ít tác động nhất. Sự khác biệt lớn giữa xây riêng và xây cùng cần được kiểm tra bằng nhiều seed và sensitivity; bảng này **chưa xác nhận xếp hạng địa điểm ngoài thực tế**.

Kiểm thử: 19 test hợp đồng trước đó; tập bổ sung counting/jobs **16/16 đạt** (có overlap, không cộng thành tổng độc lập); UI builder đạt mặc định tự động và override bằng 0. Hai lần timeout đầu được giữ trong lịch sử job, không giấu thành lượt thành công ngay lần đầu.

Đã kiểm tra deep link mở lại đúng `together_3`, giữ nền 3.888 xe/giờ, chuyển sang P3 và render lớp đường SUMO, không có lỗi JavaScript. Báo cáo `saved-result-ui-report.json`, ảnh `p3-traffic-map.png` và `saved-result.png` nằm trong thư mục bằng chứng trên. File JSON kết quả khoảng 38 MB khi pretty-print; cần tối ưu payload/lazy loading và thời gian chạy trước khi coi là trải nghiệm production.

1. **Chỉ chứng minh con số tăng sau khi xây.** Planner cần thấy thay đổi đó ảnh hưởng lựa chọn parcel, quy mô hoặc phân kỳ như thế nào; so với chi phí/lợi ích và ràng buộc nào.
2. **Gán một lưu lượng cho mọi đường.** Đủ làm fallback minh bạch, chưa đủ để khẳng định xếp hạng địa điểm đúng thực tế. Cần sensitivity; sau đó có thể phân cấp theo loại đường/làn với hệ số có căn cứ hoặc giả định được công bố.
3. **Số counting chưa kiểm chứng.** Video đẹp không thay thế sai số đo. Camera mapping, vị trí/thời điểm và cửa sổ đo dài hơn vẫn thiếu.
4. **Nhiều năng lực hạ tầng chưa biết.** Nhu cầu tăng có thể tính, nhưng chưa kết luận quá tải điện/nước/trường học khi thiếu nền tải và capacity. Bóng đổ không phải nhiệt độ; tràn nút SWMM không phải bản đồ độ sâu ngập 2D.
5. **Quy hoạch chưa đủ để kết luận được phép xây.** Case thực hiện có xung đột công năng; phải trình bày là what-if, không phải phương án được duyệt.
6. **Chưa chứng minh luồng sản phẩm cuối.** Demo kiểm thử và contract API đã có; người phụ trách frontend chính cần nối parcel/building plan, job, map layers và kết quả so sánh thành một luồng.
7. **Thời gian chạy native là rủi ro UX có bằng chứng.** Khi đổi proxy nền từ 800 lên 3.888 xe/giờ, case 3 parcel có một child SUMO timeout ở 120 rồi 300 giây; lần sau đã mô phỏng tới 3.928/4.200 giây và còn 428 xe đang dừng. Demo phải có tiến trình, kết quả lưu/cached và scope nhỏ cho chạy tương tác; việc nới timeout không tự giải quyết trải nghiệm chờ.

## Ưu tiên trước cuộc thi

### P0 — Một quyết định rõ ràng và luồng demo liền mạch

- Chốt một câu hỏi: “Cùng một chương trình chung cư, chọn đất A/B/C hay phân kỳ xây như thế nào để giảm tác động lên khu vực?”
- Dùng baseline và các phương án trên cùng nền, seed và giả định. Nêu cả lợi ích nhà ở và tác động hạ tầng; không chỉ trình diễn nhiều lớp map.
- Nối frontend chính qua API có sẵn. Hiển thị tiến trình, nguồn và kết quả; dùng kết quả đã lưu cho pitch, cho phép chạy mới với phạm vi nhỏ.
- Dành một case cho xung đột công năng thật; không diễn giải các parcel có cảnh báo thành địa điểm xây hợp lệ.

### P1 — Chứng minh độ tin cậy trong phạm vi demo

- Đếm tay độc lập cả 3 clip; so sự kiện/hướng/loại xe, báo sai lệch và lỗi bỏ sót/đếm trùng.
- Chạy sensitivity lưu lượng thấp/cơ sở/cao; cho biết kết luận chọn phương án có đổi hay không. Mức lưu lượng cơ sở vẫn là synthetic.
- Khi cần demo kiểm tra quá tải, dùng một gói capacity/nền tải giả lập nhất quán, có nhãn và phạm vi; giữ phần chưa biết trong snapshot thật là unknown.
- Bổ sung occupancy/nền dân cư giả định có nhãn cho case synthetic riêng nếu cần minh họa delta điện/nước/trips. Case parcel thật hiện để occupancy unknown, nên nhiều delta vẫn null; không chuyển unknown thành 0 để làm bảng trông đầy đủ.
- Báo backlog/completed fraction cùng delay để tránh phương án có ít xe hoàn thành trông “tốt” hơn một cách sai lệch.

### P2 — Bàn giao và mở rộng

- Hoàn thiện sơ đồ camera → counting → road/time mapping → hiệu chỉnh demand → simulation. Trình bày rõ bước nào đã làm và bước nào cần quyền camera.
- Chuẩn bị pitch về người dùng, giá trị quyết định, chiến lược dữ liệu và cách tích hợp hệ sinh thái bản đồ.
- Hoãn thêm nhiều mô hình khi chưa có một case quyết định và luồng người dùng được kiểm chứng. Phần giải thích AI vẫn hoãn theo yêu cầu trước đó.

## Kết luận

Hướng làm phù hợp đề bài và có thể cạnh tranh ở mức prototype. Muốn tăng cơ hội đạt giải, ưu tiên **case ra quyết định thuyết phục, liên kết AI có bằng chứng, và luồng demo trên map chính**. Không cần có dữ liệu thật cho toàn thành phố để dự thi, nhưng cần phân biệt giả định và quan trắc, chứng minh kết luận bền đến đâu khi thay đổi giả định.
