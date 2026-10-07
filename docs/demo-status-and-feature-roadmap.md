# UrbanDynamics — demo hiện tại và kế hoạch bổ sung tính năng

**Cập nhật:** 06/10/2026.

**Bổ sung 07/10:** đã triển khai demo integrated cho chung cư tại Thủ Đức với SUMO/SWMM thực, bóng đổ, nhu cầu theo giờ và gợi ý chạy lại. Xem [hướng dẫn mới và giới hạn](integrated-building-impact.md). Nội dung kiểm kê phía dưới phản ánh demo công thức trước bản integrated; AI giải thích hoãn, máy 156 chưa deploy.
**Căn cứ:** mã nguồn hiện có, snapshot local và báo cáo kiểm thử ngày 05/10/2026. Tài liệu này không phải kết quả chạy lại toàn bộ test ngày 06/10.
**Phạm vi:** hỗ trợ urban planner đánh giá các loại công trình tại Thủ Đức; trường học là một ví dụ, ngoài ra có nhà ở, văn phòng, bệnh viện và công trình khác.

## 1. Tóm tắt hiện trạng

Demo đã có luồng:

**Hiện trạng + công trình dự định xây → dự tính tác động → đánh giá từng tiêu chí → tìm gợi ý theo ràng buộc/ngân sách → tính lại và so sánh.**

Người dùng không phải nhập sẵn thiết kế cải thiện. Hệ thống tạo gợi ý sau khi đánh giá công trình.

Hiện có hai phần cần ghép thành sản phẩm thống nhất:

1. **Trang demo tác động công trình:** `/simulation`, chạy cùng backend FastAPI.
2. **API và ETL dữ liệu ngập/giá đất:** đã xử lý dữ liệu thật, nhưng chưa tích hợp đầy đủ thành các lớp trên giao diện demo.

Frontend chính trong `frontend/public/index.html` vẫn là scaffold. Trang simulation là giao diện riêng, chưa phải toàn bộ web quy hoạch hoàn chỉnh.

## 2. Trang demo đã có gì?

Địa chỉ local sau khi khởi động stack: `http://127.0.0.1:8001/simulation`.

| Tính năng | Đã hoạt động | Giới hạn hiện tại |
|---|---|---|
| Chọn khu đất | Vẽ polygon trên bản đồ hoặc nhập GeoJSON; đo diện tích WGS84 | Chưa đối chiếu thửa đất/quy hoạch hoặc tự nhận diện hiện trạng |
| Thêm công trình | Vẽ footprint; nhập công năng, số tầng, số người và thiết kế bề mặt | Chưa có editor công trình 3D/chiều cao/hướng nhà |
| Bề mặt và cây xanh | Tính diện tích mái, sân cứng, sân thấm, đất xanh trước/sau | Theo đầu vào thiết kế; đất xanh chưa phải diện tích tán cây hay tiện nghi nhiệt |
| Dòng chảy do mưa | Ước tính thể tích nước chảy tràn, giữ lại và còn lại | Chưa tính địa hình, mạng cống, triều hoặc độ sâu/vùng ngập |
| Giao thông | Dự tính chuyến xe giờ cao điểm từ số người, hệ số chuyến đi, phương tiện và số người/xe | Chưa mô phỏng tuyến đi, ùn tắc, hàng chờ hoặc thời gian đi lại |
| Nước, nước thải, điện | Dự tính nhu cầu và so sánh phần tăng thêm với công suất còn lại | Hệ số/công suất do người dùng cung cấp; chưa mô phỏng mạng hạ tầng |
| Đánh giá tác động | Báo tốt hơn/xấu hơn/có đánh đổi/không đổi theo chỉ số; kiểm tra mục tiêu | Đánh giá áp lực môi trường/hạ tầng, chưa cân đối toàn bộ lợi ích của công trình |
| Gợi ý cải thiện | Tạo tối đa ba gợi ý rồi tính lại; kiểm tra ngân sách và mục tiêu còn thiếu | Tìm kiếm hữu hạn, chưa tối ưu toàn cục hoặc xác nhận khả thi thi công |
| Bảo toàn thiết kế | Gợi ý giữ nguyên footprint, diện tích mái, số tầng và số người | Chưa tìm phương án thay đổi hình khối, cổng hoặc chiều cao |
| Lưu/mở lại | Lưu PostGIS, UUID, phiên bản, nguồn giả định và SHA256; giữ bản ghi gốc | Chưa có quản lý dự án/người dùng hoặc dashboard lịch sử scenario |
| Xuất kết quả | JSON; in/lưu PDF qua trình duyệt | Chưa có báo cáo PDF được server tạo và kiểm soát bố cục |

### Các loại gợi ý hiện có

- Chuyển một phần sân cứng sang đất xanh hoặc sân thấm.
- Bổ sung dung tích giữ nước.
- Đặt mục tiêu giảm tỷ lệ xe cá nhân khi có căn cứ cho khả năng chuyển phương tiện.
- Đặt mục tiêu tiết kiệm nước và giảm điện cao điểm.
- Báo `partial_improvement` nếu có cải thiện nhưng chưa đạt đủ mục tiêu.
- Báo `no_feasible_improvement` nếu không tìm được cải thiện trong ràng buộc.

Gợi ý hiện được tạo bằng quy tắc và tìm kiếm phương án. **Chưa tích hợp AI Club/LLM.** Các mức tiết kiệm và chi phí trong ví dụ là giả định phần mềm, chưa phải hiệu quả thực tế hoặc báo giá.

## 3. Các lớp dữ liệu/API đã có

| Lớp / chức năng | Kết quả đã kiểm tra | Cần hoàn thiện |
|---|---|---|
| Ngập lịch sử DataSuds | 425 quan sát nguồn; 131 trong ranh giới demo Thủ Đức; API lọc không gian/thời gian | Overlay, popup nguồn, lọc ngày trên giao diện chung |
| Nguy cơ ngập | Quy tắc kết hợp mưa với vùng gần điểm từng ngập, có căn cứ và metadata | Nhận lưới mưa đầy đủ, làm mới dự báo và hiển thị hạn dùng |
| Kịch bản mưa | `POST /api/v1/scenarios/rain` đánh giá mưa giả định theo cùng quy tắc | Phân biệt rõ với mô phỏng building và mô hình thủy lực |
| Ảnh ngập GFM | Đã xử lý raster thật ngày 01/10/2026; vùng cắt có 0 pixel ngập dương tính | Chưa có exclusion mask riêng; không suy ra toàn vùng khô; cần ảnh/sự kiện phù hợp để demo |
| Giá đất chính thức | Parser có 195 hàng ứng viên; 1 feature Trần Não được công bố với phạm vi một phần | Duyệt PDF và hai đầu đoạn; hướng tới tối thiểu 25 đoạn đã kiểm chứng |
| Danh mục lớp | API trả trạng thái, metadata; truy vấn GeoJSON theo bbox/thời gian | Giao diện quản lý lớp, nguồn và độ bao phủ |
| Mưa và dân cư | Có pipeline/config trong repo; demo Khôi đang dùng đầu vào mưa tại một điểm | Chưa có bằng chứng nghiệm thu lớp dân cư/lưới mưa đầy đủ trong bộ snapshot và harness đã kiểm tra; cần bàn giao/tích hợp |

Nguồn ngập lịch sử: [DataSuds — bộ dữ liệu ngập TP.HCM](https://dataverse.ird.fr/dataset.xhtml?persistentId=doi:10.23708/8Y16HU). Giữ attribution và điều kiện giấy phép CC BY-NC 4.0 khi sử dụng.

Giá đất hiện là bảng giá chính thức theo đoạn đường, chưa phải giá giao dịch thị trường hoặc dự báo tăng giá sau khi xây công trình. Một feature được duyệt chưa đủ để coi là heatmap giá đất phủ Thủ Đức.

## 4. Ví dụ kết quả hiện tại

Ví dụ **hoàn toàn giả định**: khu đất khoảng 12.095,93 m², mưa 60 mm, công trình phục vụ 600 người.

| Chỉ số | Công trình dự định xây | Gợi ý 1 tự sinh |
|---|---:|---:|
| Nước còn lại sau giữ nước giả định | 544,32 m³ | 295,54 m³ |
| Chuyến xe giờ cao điểm | 80 chuyến/giờ | 60 chuyến/giờ |
| Nhu cầu nước | 48 m³/ngày | 30 m³/ngày |
| Nước thải | 38,4 m³/ngày | 24 m³/ngày |
| Điện cao điểm | 60 kW | 45 kW |

Gợi ý có chi phí theo đơn giá giả định khoảng 829,08 triệu VND, trong ngân sách giả định 1 tỷ. Công trình, số tầng và 600 người được giữ nguyên.

Kết quả là **cải thiện một phần**: nước còn lại vẫn cao hơn hiện trạng khoảng 214,10 m³. Hệ thống liệt kê mục tiêu chưa đạt; không tự tăng ngân sách hoặc thu nhỏ công trình để báo kết quả tốt.

## 5. Bằng chứng kiểm thử và trạng thái bàn giao

- Lần kiểm tra 05/10: **77/77 test Windows**, **77/77 test Linux**, đều với PostGIS thật, không bỏ qua test database.
- **10 nhóm kiểm tra Edge headless đạt**: luồng hai đầu vào, gợi ý sinh sau đánh giá, lưu/mở lại, xuất JSON, chống kết quả cũ, validation, vẽ polygon/footprint, mobile và mất CDN.
- Backend, ETL và frontend scaffold build thành công. Build scaffold chưa chứng minh frontend sản phẩm đã hoàn thành.
- Test trình duyệt chặn tải tile server; kiểm tra thao tác hình học bằng Leaflet, chưa xác nhận chất lượng bản đồ nền.
- Thay đổi simulation mới đang ở workspace local, chưa commit/push và chưa được GitHub Actions kiểm tra cho phiên bản này; chưa deploy máy 156.

Chi tiết: [báo cáo test simulation](building-simulation-test-report.md), [hướng dẫn luồng hiện tại](building-impact-prediction.md), [báo cáo dữ liệu Khôi](khoi-local-test-report.md). Các số liệu 36/36 hoặc 62/62 trong phần lịch sử là các đợt test trước.

## 6. Tính năng nên thêm — thứ tự ưu tiên

Thứ tự dưới đây là đề xuất triển khai. Ưu tiên traffic theo lựa chọn của nhóm; công việc thu thập dữ liệu giao thông nên bắt đầu ngay, song song với tích hợp giao diện.

| Ưu tiên | Tính năng | Giá trị đối với planner | Điều kiện nghiệm thu |
|---|---|---|---|
| P0 | Bản đồ chung cho scenario, ngập lịch sử, cảnh báo và giá đất | Thấy công trình trong bối cảnh khu vực | Lớp bật/tắt được, popup có nguồn/thời gian/phạm vi; không trình bày vùng thiếu dữ liệu là an toàn |
| P0 | Tự điền hiện trạng và quản lý giả định | Giảm nhập tay, tách dữ liệu khảo sát khỏi giả định | Dữ liệu có nguồn được tự điền; trường thiếu được yêu cầu bổ sung, không tự gán giá trị thực tế |
| P0 | Bộ dữ liệu giao thông cho một khu pilot | Tạo nền cho mô phỏng ùn tắc đáng kiểm chứng | Mạng đường, lưu lượng/hướng rẽ, pha đèn, cổng và số liệu hàng chờ/thời gian đi lại được kiểm tra |
| P1 | Traffic simulation bằng SUMO trên khu pilot | Đánh giá ảnh hưởng của cổng và hoạt động công trình lên tuyến/nút | Hiện trạng được hiệu chỉnh và kiểm chứng trước khi mô phỏng sau xây; báo sai số và phạm vi |
| P1 | AI giải thích có bằng chứng | Hỏi bằng tiếng Việt, hiểu đánh đổi và đề xuất bước tiếp theo | AI dùng số liệu đã tính, dẫn nguồn, nói rõ thiếu dữ liệu; gợi ý mới phải được engine tính lại |
| P1 | Tiếp cận dịch vụ và lợi ích phục vụ | Cân đối áp lực tăng với số người được hưởng lợi | Tính theo mạng đường, dân cư và công suất dịch vụ; phân biệt độ bao phủ dữ liệu với nhu cầu thực |
| P1 | Giao diện đánh đổi và kiểm tra độ nhạy | Planner thấy kết quả phụ thuộc giả định nào | Thay đổi một giả định có kiểm soát; cùng điều kiện khi so sánh; khoảng thử không gọi là xác suất tin cậy |
| P2 | Bóng đổ theo giờ | Đánh giá nắng/bóng mát và ảnh hưởng công trình lân cận | Có chiều cao/hình học, thời gian và vị trí; kiểm tra bằng trường hợp hình học đã biết |
| P2 | Tiện nghi nhiệt ngoài trời | Đánh giá tác động cây xanh/hình khối tới người đi bộ | Có dữ liệu bề mặt, cây xanh, khí tượng và đối chiếu; ghi đúng đại lượng nhiệt |
| P2 | Mô hình ngập thủy lực cho lưu vực nhỏ | Dự tính độ sâu/vùng/thời gian ngập và tác động lân cận | Có địa hình, cống, mưa, triều, tham số và sự kiện kiểm chứng; kiểm tra cân bằng nước |
| P2 | Nâng chất lượng dữ liệu nền | Mở rộng giá đất, mưa, dân cư và ảnh ngập có căn cứ | Các đoạn giá đất được duyệt; snapshot mưa còn hạn; lớp dân cư có nguồn và thời điểm |

P0/P1/P2 thể hiện thứ tự đề xuất, chưa phải cam kết đã có tính năng hoặc đã đủ dữ liệu. Không chờ P2 mới bắt đầu cải thiện các lớp nền: duyệt giá đất và nhận mưa/dân cư nên chạy song song.

## 7. Kế hoạch traffic simulation cụ thể

### Dữ liệu cần

| Nhóm | Nội dung |
|---|---|
| Mạng đường | Geometry, số/bề rộng làn, chiều đi, tốc độ giới hạn, kết nối làn và các hạn chế rẽ |
| Nút giao/đèn | Hướng rẽ, vạch dừng, pha xanh/vàng/đỏ, chu kỳ và lịch điều khiển |
| Lưu lượng nền | Xe theo hướng, khung giờ và loại phương tiện; tách xe máy, ô tô, buýt, tải |
| Tuyến/OD | Phân bố điểm xuất phát–đích đến hoặc tuyến và hướng rẽ đủ để tạo nhu cầu di chuyển |
| Building | Công năng, lịch hoạt động, người sử dụng, thời điểm đến/rời và cơ cấu phương tiện |
| Cổng/đón trả | Vị trí và hướng vào/ra, bãi xe, sức chứa và thời gian dừng |
| Kiểm chứng | Hàng chờ, tốc độ và thời gian đi lại ở những điểm/khung giờ đo được |

OSM là nền để dựng mạng; cần kiểm tra các thuộc tính bị thiếu hoặc được suy đoán khi nhập. [Tài liệu SUMO nhập OSM](https://eclipse.dev/sumo/docs/Networks/Import/OpenStreetMap.html).

### Pipeline đề xuất

1. Chọn một công trình và vùng mạng gồm các nút chịu ảnh hưởng, đường dẫn vào và nơi hàng chờ có thể lan tới.
2. Tải OSM, kiểm tra tại hiện trường/bản vẽ và sửa mạng SUMO.
3. Thu thập lưu lượng, hướng rẽ, pha đèn và dữ liệu kiểm chứng. Có thể bắt đầu bằng khoảng đếm 15 phút; đây là lựa chọn thu thập cho pilot.
4. Tạo nhu cầu hiện trạng theo thời gian và loại xe; hiệu chỉnh với dữ liệu đo.
5. Kiểm chứng bằng đợt/khung giờ khác với dữ liệu dùng để hiệu chỉnh khi đủ dữ liệu.
6. Thêm công trình, cổng và nhu cầu mới; giữ cùng điều kiện nền để đo thay đổi.
7. Thử các gợi ý: đổi cổng, bố trí đón trả trong khuôn viên, thay lịch hoạt động hoặc giảm xe cá nhân có căn cứ.
8. Chạy lại, so sánh thời gian đi lại, hàng chờ, thời gian chờ và xe chưa hoàn thành chuyến. Dùng nhiều lượt chạy/seed khi mô hình có yếu tố ngẫu nhiên.

SUMO có công cụ hiệu chỉnh lưu lượng/tốc độ theo quan trắc; phải kiểm chứng mô hình hiện trạng trước khi dùng kết quả sau xây. [SUMO Calibrator](https://eclipse.dev/sumo/docs/Simulation/Calibrator.html).

Nếu chưa có số liệu nền: vẫn có thể trình diễn kỹ thuật bằng nhu cầu giả định có nhãn, nhưng chưa tuyên bố dự báo ùn tắc thực tế. Traffic animation chỉ cho thấy engine chạy, chưa chứng minh mô hình chính xác.

## 8. AI và các mô hình tiếp theo

### AI trong web

- Nhận context: khu đất, công trình, thời gian, nguồn, kết quả, mục tiêu và ràng buộc.
- Giải thích vì sao một chỉ số xấu hơn hoặc chưa đạt mục tiêu.
- Đề xuất thay đổi trong các hành động backend hỗ trợ; backend kiểm tra và chạy lại engine.
- Trả lời thiếu dữ liệu khi người dùng hỏi độ sâu ngập, thời gian ùn tắc hoặc giá thị trường chưa có.
- Giữ kết quả tính toán và gợi ý có phiên bản để truy lại; không cho AI tự tạo số liệu.

### Ngập

Bước nâng cấp phù hợp là mô hình mưa–dòng chảy/mạng thoát nước trên một lưu vực nhỏ. SWMM hỗ trợ nhóm bài toán này và giải pháp giữ/thấm nước. Muốn bản đồ độ sâu ngập ngoài đường cần mô hình bề mặt 2D và trao đổi nước với mạng cống được thiết lập/kiểm chứng đúng. [EPA SWMM](https://www.epa.gov/water-research/storm-water-management-model-swmm).

### Nhiệt

Làm bóng đổ hình học trước; tiếp theo mới mô hình tiện nghi nhiệt khi đủ dữ liệu. SOLWEIG sử dụng hình học/chiều cao và khí tượng để tính môi trường bức xạ, nhiệt độ bức xạ trung bình và các chỉ số tiện nghi nhiệt; không tự diễn giải kết quả thành mức giảm nhiệt độ không khí. [Tài liệu SOLWEIG](https://umep-dev.github.io/solweig/).

## 9. Lộ trình đề xuất tới demo 17/10

Đây là lịch mục tiêu, cần điều chỉnh theo nhân lực và tiến độ dữ liệu.

| Mốc | Công việc | Kết quả cần bàn giao |
|---|---|---|
| 06–08/10 | Ghép bản đồ/API; chọn khu traffic pilot; bắt đầu khảo sát; nhận bàn giao mưa/dân cư | Một khu demo thống nhất, danh sách nguồn và các trường còn thiếu |
| 09–11/10 | Dựng mạng/nhu cầu traffic; đối chiếu hiện trạng; thêm tiếp cận dịch vụ; kết nối AI adapter | So sánh tác động có nguồn; traffic có trạng thái dữ liệu và kết quả kiểm chứng ban đầu |
| 12–14/10 | Hoàn thiện gợi ý, báo cáo, độ nhạy; chạy local; review/push và CI cho phiên bản mới | Luồng hoàn chỉnh, test/report rõ ràng; chỉ bật tính năng đã qua gate |
| 15–16/10 | Deploy máy 156, backup/rollback, diễn tập | Demo tái hiện được trên máy đích |
| 17/10 | Trình diễn | Building → tác động → đánh giá → gợi ý → tính lại → báo cáo |

Nếu traffic chưa được kiểm chứng kịp: trình bày phần nhu cầu/công suất hiện có và phạm vi pilot thử nghiệm với nhãn phù hợp. Bóng đổ/nhiệt/ngập thủy lực chỉ đưa vào demo khi đủ dữ liệu và qua kiểm tra, không ép vào lịch bằng đầu ra thiếu căn cứ.

## 10. Phân công đề xuất

- **Khôi:** dữ liệu ngập/giá đất, nâng chất lượng các lớp này và kiểm chứng phần dòng chảy.
- **Duy:** mưa/dân cư, dữ liệu dùng chung, kho, cập nhật định kỳ và CI/deploy.
- **Frontend:** bản đồ chung, editor building, nguồn/độ bao phủ, bảng đánh đổi và luồng scenario.
- **AI Club:** endpoint model và diễn giải có nguồn, tích hợp qua backend.
- **Traffic pilot:** cần phân công người chịu trách nhiệm khảo sát, dựng SUMO và kiểm chứng; chưa mặc định giao thêm toàn bộ phần này cho Khôi.

Phân công trên là đề xuất dựa trên vai trò hiện có, cần nhóm thống nhất tải công việc.

## 11. Tiêu chí chốt demo

- Chọn công trình thuộc nhiều công năng, không chỉ trường học.
- Chỉ nhập hiện trạng + thiết kế dự định; gợi ý được tạo sau đánh giá.
- Mỗi feature có đơn vị, nguồn, thời điểm, phạm vi và mức độ kiểm chứng.
- Phân biệt dữ liệu thật, thiết kế giả định và kết quả mô hình.
- Tốt/xấu theo từng tiêu chí; thể hiện cả lợi ích phục vụ và áp lực tăng khi đã có module tương ứng.
- Gợi ý giữ đúng quy mô/ràng buộc/ngân sách; báo rõ mục tiêu chưa đạt.
- Traffic, nhiệt và ngập chỉ công bố các đại lượng engine thực sự hỗ trợ và đã được kiểm tra.
- Kết quả lưu/mở lại được; AI giải thích đúng số liệu; lỗi nguồn/model có trạng thái rõ.
- Phiên bản mới được kiểm thử local, qua CI và diễn tập trên máy 156 trước trình diễn.

**Ưu tiên đề xuất:** ghép demo thành một bản đồ thống nhất, thu thập và kiểm chứng traffic pilot, thêm AI có bằng chứng và lợi ích tiếp cận dịch vụ; sau đó nâng các mô hình vật lý theo dữ liệu thực tế.
