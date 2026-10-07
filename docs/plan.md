# Kế hoạch triển khai MVP UrbanDynamics đến 17/10/2026

**Cập nhật phần Khôi ngày 07/10:** phạm vi dữ liệu là TP.HCM mở rộng, gồm Bình Dương, Bà Rịa–Vũng Tàu và Côn Đảo. Khôi nhận toàn bộ ETL mưa từ Duy. Dùng [hướng dẫn ETL toàn TP](khoi-citywide-etl.md) cho ranh giới, lịch cập nhật và API hiện hành. Các mô tả Thủ Đức và phân công mưa cho Duy bên dưới là lịch sử kế hoạch. Lưới lấy mẫu mặc định 10 km; scheduler hiện dùng Python stdlib với khóa leader và lịch riêng từng job.

**Cập nhật phạm vi simulation ngày 06/10:** dùng [kế hoạch tác động tổng hợp của building](integrated-building-impact-plan.md) cho công việc tiếp theo. Kế hoạch này bao gồm ngập/dòng chảy, giao thông, điện/nước/nước thải, xanh/nhiệt, dân cư/dịch vụ và bối cảnh giá/quy hoạch; cho phép dữ liệu tổng hợp có nhãn theo thông tin ban tổ chức mà người dùng cung cấp. Những mốc và yêu cầu dữ liệu thật trong các phần cũ bên dưới là lịch sử kế hoạch, không thay thế phạm vi mới.

## 1\. Mục tiêu và kiến trúc

Xây dựng web hỗ trợ urban planners và nhà đầu tư khảo sát Thủ Đức trên bản đồ 3D, chọn khu vực, xem dữ liệu, so sánh địa điểm và nhận phân tích AI có dẫn nguồn. Phạm vi Thủ Đức dùng ranh giới thành phố trước thay đổi hành chính năm 2025; các phường hiện tại được hiển thị như lớp bổ sung.

Chốt công nghệ:

- **Frontend:** React, TypeScript, Vite và MapLibre GL JS. Dùng [OpenFreeMap](<https://openfreemap.org/>) làm bản đồ nền; MapLibre hỗ trợ [hiển thị tòa nhà 3D](<https://maplibre.org/maplibre-gl-js/docs/examples/display-buildings-in-3d/>). Chiều cao suy ra phải có nhãn ước tính.
- **Backend:** FastAPI, SQLAlchemy và Alembic.
- **Kho dữ liệu:** PostgreSQL + PostGIS, dùng chung cho dữ liệu không gian, chuỗi thời gian và kết quả phân tích.
- **ETL:** Python, GeoPandas, GDAL/Rasterio; APScheduler chạy trong một container ETL duy nhất.
- **AI:** backend gọi dịch vụ local của AI Club qua adapter HTTP. URL, tên model và thông tin xác thực được cấu hình bằng biến môi trường.
- **Triển khai:** Docker Compose trên máy **156**, GitHub Actions build và kiểm tra trước khi deploy.

Luồng dữ liệu: **nguồn → ETL → PostGIS/tệp raster → backend → bản đồ và AI**. Frontend sử dụng dữ liệu đã nhập vào hệ thống, giúp thao tác bản đồ không phải chờ website nguồn.

## 2\. Các tính năng và dữ liệu triển khai

| Phần | Nguồn và cách thực hiện | Kết quả MVP |
|---|---|---|
| **Bản đồ ngập lịch sử — Khôi** | Dùng [bộ dữ liệu ngập TP.HCM của DataSuds](<https://dataverse.ird.fr/dataset.xhtml?persistentId=doi:10.23708/8Y16HU>). Tải GeoPackage qua file ID `50143`, đối chiếu TSV `50148`, chuyển CRS sang WGS84 và lọc bằng ranh giới Thủ Đức. | Điểm ngập, clustering, lọc theo ngày, nguyên nhân và mức độ sâu; popup có nguồn và độ chính xác vị trí. Công bố số điểm thực sự nằm trong Thủ Đức sau khi lọc tọa độ. |
| **Ảnh ngập vệ tinh — Khôi** | Tìm sản phẩm [Copernicus GFM](<https://www.docs.eodc.eu/notebooks/gfm-download.html>), tải raster giao khu vực, kiểm tra lớp ngập và exclusion mask. | Overlay vùng ngập quan sát theo thời điểm khi có raster hợp lệ. Ngày chụp và vùng không thể đánh giá được hiển thị rõ. |
| **Cảnh báo nguy cơ ngập — Khôi** | Kết hợp mưa dự báo Open-Meteo với điểm từng ngập. Tính ngưỡng mưa 3 giờ P90 từ dữ liệu lịch sử 2016–2025 cùng tháng, chỉ xét các khoảng có mưa. | Đánh dấu “mưa lớn dự kiến gần điểm từng ngập” khi vượt ngưỡng; vùng lân cận mặc định 250 m. Hiển thị mưa, ngưỡng và sự kiện lịch sử làm căn cứ. |
| **Giá đất — Khôi** | Trích bảng giá theo [Nghị quyết 87/2025/NQ-HĐND](<https://congbao.hochiminhcity.gov.vn/cong-bao/van-ban/nghi-quyet/so/87-2025-nq-hdnd/ngay/26-12-2025/tai-ve/48983?cbid=48993>), ghép tên đường và hai đầu đoạn với hình học đường OSM, duyệt thủ công kết quả ghép. | Tô màu đoạn đường theo giá đất ở, thương mại và sản xuất; giữ đơn vị VND/m² và năm hiệu lực. Mục tiêu demo tối thiểu 25 đoạn đã kiểm chứng; đoạn chưa ghép được được ghi là thiếu dữ liệu. |
| **Mưa — Duy** | Open-Meteo forecast và historical API; lấy theo lưới khoảng 5 km, giữ độ phân giải nguồn. | Lớp mưa, biểu đồ theo giờ và tổng 3/24 giờ. Nội suy màu phải có nhãn để tránh hiểu là quan trắc cấp đường. |
| **Dân cư — Duy** | [WorldPop Global2](<https://api.worldpop.org/v2/>), chọn bản Việt Nam năm 2025, cắt Thủ Đức. Đây là dân số mô hình hóa. | Lớp mật độ và tổng dân số ước tính trong khu vực; bảo toàn tổng dân số khi đổi lưới. |
| **Công trình, đường, cây xanh — nhóm frontend và ETL** | OSM/Overpass: trường học, bệnh viện, trạm y tế, đường, footprint tòa nhà và các polygon xanh được khai báo. | Điểm công trình; bán kính 500/1.000 m; mật độ đường, tỷ lệ footprint và diện tích xanh đã lập bản đồ. Ghi rõ độ bao phủ nguồn. |

Các lớp giao thông trực tiếp, quy hoạch theo thửa và mạng thoát nước chỉ được bật sau khi có nguồn, quyền sử dụng và dữ liệu kiểm chứng. Mô phỏng giao thông, tối ưu đèn bằng RL và mô hình thủy lực nằm ở giai đoạn sau MVP.

**Bổ sung bốn tính năng hỗ trợ quyết định:**

- **Phân tích vùng:** vẽ polygon hoặc chọn phường để xem dân cư, công trình, mật độ đường, cây xanh, lịch sử ngập và các đoạn giá đất có dữ liệu.
- **So sánh hai khu vực:** hiển thị cùng chỉ số, cùng thời điểm và độ bao phủ. Người dùng chọn tiêu chí quan trọng; MVP không tạo một điểm tổng hợp thiếu căn cứ.
- **Kịch bản mưa:** nhập tổng mưa 3 giờ, áp dụng cùng quy tắc cảnh báo và xem các điểm từng ngập liên quan. Gắn nhãn “kịch bản giả định”.
- **Báo cáo có bằng chứng:** xuất báo cáo HTML có bản đồ, chỉ số, nguồn, thời gian, giới hạn và phân tích AI.

Mọi lớp đều có thông tin nguồn, giấy phép, thời gian quan sát, ngày nhập và độ phân giải. Bộ DataSuds mang giấy phép **CC BY-NC 4.0**, cần giữ attribution và giới hạn sử dụng tương ứng.

## 3\. Dữ liệu, API và AI

### Ưu tiên bổ sung: so sánh tác động công trình

Ngày 05/10 chỉnh luồng đánh giá tác động công trình: nhập hiện trạng + công trình dự định xây → dự tính chỉ số → đánh giá → tìm gợi ý theo ngân sách/ràng buộc → tính lại. Người dùng không nhập sẵn thiết kế cải thiện. Module dự tính bề mặt, thể tích dòng chảy, chuyến xe cao điểm, nước, nước thải và điện theo hệ số có nguồn do planner cung cấp; đối chiếu phần công suất còn trống trước khi xây. Lưu từng lần chạy có phiên bản; trang demo tại `/simulation`. Chưa dự báo độ sâu/vùng ngập hoặc ùn tắc/thời gian chờ. Chi tiết tại [hướng dẫn simulation hiện tại](building-impact-prediction.md).

Các bước tiếp theo: thay hệ số/công suất giả định trong demo bằng khảo sát hoặc dữ liệu hạ tầng có nguồn; bổ sung chiều cao và mạng đường cho bóng đổ/tiếp cận dịch vụ; hiệu chỉnh mô hình thủy lực và giao thông trên một khu vực nhỏ; tích hợp diễn giải AI từ kết quả đã tính. Tiến độ phụ thuộc dữ liệu và nguồn lực nhóm, chưa được coi là tính năng đã hoàn thành.

**ETL và lưu trữ**

- Lưu bản gốc, checksum, lần chạy và phiên bản nguồn để truy vết.
- Kiểm tra CRS, đơn vị, ngày, geometry và bản ghi trùng trước khi công bố snapshot mới.
- Giữ phiên bản thành công gần nhất khi nguồn lỗi; hiển thị trạng thái cũ và thời điểm cập nhật.
- Mưa cập nhật mỗi giờ; GFM kiểm tra mỗi 6 giờ; OSM mỗi tuần; ngập lịch sử, dân cư và giá đất kiểm tra phiên bản mỗi tháng.
- Lưu `observed_at`, `valid_from`, `ingested_at` riêng. Dữ liệu dự báo lưu thêm thời điểm phát hành.
- Tạo chỉ mục không gian, tổng hợp lưới 500 m và vector tiles cho lớp lớn. Tệp raster và dữ liệu gốc nằm trên volume bền vững.

**Giao diện API tối thiểu**

| API | Vai trò |
|---|---|
| `GET /api/v1/layers` | Danh mục lớp, nguồn, thời gian và trạng thái khả dụng. |
| `GET /api/v1/layers/{id}/features` | GeoJSON theo viewport và thời gian cho lớp nhỏ. |
| `GET /api/v1/tiles/{layer}/{z}/{x}/{y}.mvt` | Vector tiles cho lớp lớn. |
| `POST /api/v1/areas/analyze` | Chỉ số của polygon và bằng chứng tương ứng. |
| `POST /api/v1/areas/compare` | So sánh hai polygon theo cùng tiêu chí. |
| `POST /api/v1/scenarios/rain` | Kết quả kịch bản mưa. |
| `POST /api/v1/assistant/query` | Câu trả lời AI, nguồn và hành động bản đồ đã kiểm tra. |
| `GET /health`, `GET /ready` | Kiểm tra tiến trình và khả năng phục vụ dữ liệu. |

Bộ lọc thời gian chỉ cung cấp các khoảng nguồn hỗ trợ. Ví dụ mưa theo giờ không có lựa chọn “30 phút”; lớp dân cư theo năm không giả lập lịch sử theo ngày.

**AI trong web**

- Người dùng hỏi bằng tiếng Việt, ví dụ: “So sánh hai khu vực này về nguy cơ ngập và tiếp cận bệnh viện.”
- Backend tính chỉ số bằng PostGIS trước; AI diễn giải số liệu đã tính và đề xuất bước khảo sát tiếp theo.
- AI nhận context gồm vùng chọn, lớp đang mở, thời gian và bằng chứng. Mọi câu trả lời số liệu phải gắn nguồn tương ứng.
- Chỉ cho phép các hành động bản đồ đã định nghĩa: mở lớp, chuyển camera, chọn thời gian và yêu cầu phân tích vùng. Backend kiểm tra hành động trước khi frontend thực hiện.
- AI Club bàn giao endpoint và tên model trước **05/10**. Khi dịch vụ chưa sẵn sàng hoặc bị lỗi, màn hình phân tích số liệu vẫn hoạt động và chatbot hiển thị trạng thái dịch vụ.
- AI phải nêu thiếu dữ liệu khi câu hỏi đòi hỏi giá giao dịch, độ sâu ngập dự báo hoặc dữ liệu giao thông chưa có.

## 4\. Lịch triển khai và bàn giao

| Mốc | Công việc và điều kiện hoàn thành |
|---|---|
| **01–03/10** | Dựng PostGIS, migrations, frontend map và hợp đồng API. Nhập ranh giới Thủ Đức, bộ ngập DataSuds, mưa mẫu và dân cư. Bản đồ hiển thị điểm ngập từ geometry thật. |
| **04–07/10** | Hoàn thành ETL định kỳ, time filter, popup nguồn, công trình công cộng và phân tích polygon. Xác nhận endpoint AI Club. |
| **08–11/10** | Hoàn thiện cảnh báo nguy cơ ngập, kiểm tra raster GFM, ghép giá đất, so sánh khu vực và adapter AI. |
| **12–14/10** | Hoàn thiện kịch bản mưa, báo cáo, kiểm tra AI và tối ưu hiệu năng. Hoàn tất kiểm thử local trước deploy máy 156. |
| **15–16/10** | Chốt phiên bản demo, kiểm tra backup/rollback và diễn tập toàn bộ luồng trên máy 156. |
| **17/10** | Demo: chọn hai vùng → so sánh → xem lịch sử ngập → thử kịch bản mưa → hỏi AI → xuất báo cáo. |

Phân công giữ theo tài liệu: **Khôi** phụ trách ngập và giá đất; **Duy** phụ trách ETL dùng chung, dân cư, mưa, database và CI/CD; **nhóm frontend** phụ trách map, lớp dữ liệu và giao diện phân tích; **AI Club** cung cấp model local.

GitHub Actions sẽ kiểm tra backend, frontend và ETL, build image gắn commit SHA, rồi deploy thủ công qua runner riêng trên máy 156. Chạy migrations và smoke test khi rollout; giữ image trước để rollback. PostgreSQL có volume bền vững, backup hằng ngày và thử khôi phục trước demo.

## 5\. Kiểm thử và tiêu chí nghiệm thu

- Đối chiếu 425 dòng TSV với GeoPackage; kiểm tra CRS, ngày và số điểm thuộc Thủ Đức bằng phép giao không gian.
- Kiểm tra đơn vị mưa, thời gian phát hành dự báo, ngưỡng cảnh báo và trường hợp không có điểm ngập lịch sử.
- Kiểm tra GFM ở vùng có ngập, không ngập và vùng bị loại trừ; không suy ra ngập chỉ từ sự tồn tại của ảnh.
- Đối chiếu giá đất với PDF, quy đổi đúng đơn vị và xác nhận hai đầu từng đoạn đường.
- Kiểm tra phân tích vùng với polygon đã biết diện tích; xử lý vùng vượt phạm vi, vùng thiếu dữ liệu và hình học không hợp lệ.
- Kiểm tra ETL khi timeout, nguồn đổi định dạng và chạy lặp; snapshot hợp lệ trước đó phải tiếp tục phục vụ.
- AI được thử bằng câu hỏi có số liệu, thiếu dữ liệu, so sánh vùng và yêu cầu hành động không hỗ trợ; câu trả lời số liệu phải truy được nguồn.
- Trên máy demo: phản hồi giao diện dưới 500 ms; API lớp đã cache đạt p95 dưới 500 ms; phân tích polygon dưới 2 giây; map đầu tiên dưới 5 giây. AI có trạng thái xử lý riêng.
- Demo thành công khi các lớp chính và luồng phân tích hoạt động trên máy 156, có nguồn rõ ràng, và dữ liệu thiếu được hiển thị đúng.

Các mặc định đã chốt: giao diện tiếng Việt, MVP đến 17/10/2026, PostGIS, AI local, máy 156, cảnh báo nguy cơ ngập có giải thích và phạm vi Thủ Đức trước mở rộng TP.HCM. Kế hoạch triển khai được lưu vào `docs/assigned-feature-plan.md`, liên kết từ README và báo cáo nguồn dữ liệu khi bắt đầu thực hiện
