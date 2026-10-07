# Kế hoạch simulation tác động tổng hợp của công trình

**Cập nhật triển khai:** 07/10/2026. A–D đã có luồng đa feature, SUMO/SWMM và bóng đổ chạy thực trên dữ liệu tổng hợp; AI giải thích được hoãn theo người dùng. Xem [bản triển khai và giới hạn](integrated-building-impact.md). E có workflow bàn giao; máy 156 chưa có runner/`.env`, chưa deploy. Các phần SOLWEIG/2D/EPANET/EnergyPlus vẫn có điều kiện.

## 1. Mục tiêu và phạm vi

Người dùng nhập building plan → hệ thống lấy hiện trạng, chọn tham số và tạo dữ liệu tổng hợp cho phần thiếu → tính tác động trước/sau → đánh giá áp lực và lợi ích → sinh gợi ý → chạy lại toàn bộ module liên quan.

Đây là simulation nhiều nhóm tác động, không giới hạn giao thông. Căn cứ phạm vi: `Features needed for urban planners.docx`, code hiện có và các yêu cầu tiếp theo về nhiệt, điện/nước, thiết kế cải thiện. Không giới hạn công năng ở trường học.

Người dùng cho biết ban tổ chức cho phép dữ liệu giả hợp lý. Kế hoạch này dùng dữ liệu tổng hợp có quy tắc và nhãn cho những đầu vào không thể lấy được. Kết quả có nền tổng hợp chứng minh hành vi của mô hình trong kịch bản, chưa chứng minh độ chính xác tại địa điểm thực tế.

## 2. Các feature và đầu ra

| Feature | Đầu ra trước/sau | Engine đề xuất | Ưu tiên |
|---|---|---|---|
| Mật độ xây dựng và hình khối | Footprint, tổng diện tích sàn, mật độ, FAR, chiều cao | Hình học GIS; tổng diện tích sàn từ bản vẽ khi có, không mặc định mọi tầng bằng footprint | P0 |
| Đất xanh, tán cây và bề mặt không thấm | Diện tích xanh mặt đất, tán cây, impervious area và biến động | Overlay GIS; tách tán cây chồng lên sân/mái khỏi đất xanh | P0 |
| Mưa–dòng chảy và giữ nước | Thể tích, lưu lượng theo thời gian khi có engine phù hợp, dung tích giữ/thấm | Engine hệ số hiện có trước; SWMM cho mạng kịch bản | P0 → P1 |
| Thoát nước/ngập | Nút quá tải, nước tràn, thời gian; bản đồ độ sâu chỉ khi có mô hình bề mặt | SWMM 1D cho mạng; 2D/coupling là giai đoạn riêng | P1; 2D P2 |
| Giao thông và đón trả | Chuyến đến/rời, chậm trễ, hàng chờ, tuyến bị ảnh hưởng, xe chưa hoàn thành | Mô hình phát sinh chuyến → SUMO | P1 |
| Nước cấp | Nhu cầu ngày/giờ và cao điểm; chênh so năng lực mạng kịch bản | Mô hình nhu cầu theo công năng/lịch; EPANET nếu mô phỏng áp lực mạng | P0; EPANET P2 |
| Nước thải | Lưu lượng ngày/giờ, tải tăng tại điểm thu gom, quá tải mạng kịch bản | Mô hình nhu cầu/return fraction → SWMM sanitary khi có mạng | P0 → P1 |
| Điện | kWh/ngày và kW cao điểm theo lịch/tải; chênh so giới hạn kịch bản | Mô hình tải theo thiết bị/công năng; EnergyPlus về sau | P0; chuyên sâu P2 |
| Bóng đổ và tiện nghi nhiệt | Giờ nắng/bóng mát, thay đổi Tmrt/chỉ số tiện nghi được engine hỗ trợ | Hình học mặt trời; SOLWEIG khi đủ đầu vào | Bóng đổ P0/P1; nhiệt P1/P2 |
| Dân cư và tiếp cận dịch vụ | Dân số cư trú tăng/di dời, số người có thể phục vụ, tiếp cận theo mạng, tải dịch vụ | WorldPop + công suất/lịch dịch vụ + mạng đường | P0/P1 |
| Mật độ đường và kết nối | Đường thêm/mất, kết nối đi bộ/xe, thay đổi thời gian tiếp cận | GIS/network routing; đường chỉ thay đổi khi plan có thay đổi đường | P0/P1 |
| Giá đất, chi phí và quy hoạch | Giá tham chiếu, chi phí giải pháp, kiểm tra mục tiêu quy hoạch; thử giá trị giả định riêng nếu cần | Lookup + thư viện chi phí/tiêu chí; không tự dự báo uplift từ khoảng cách | Bối cảnh P0; dự báo giá P2 |

Mưa, triều và khí tượng là điều kiện ngoại cảnh để thử phương án, không phải feature mà một building nhỏ tự làm thay đổi trong các engine đề xuất. Lịch sử ngập và giá đất chính thức cũng là lớp bối cảnh; không sửa các quan trắc hoặc giá chính thức để tạo tác động dự đoán.

Tiếng ồn, phát thải giao thông, carbon công trình và rác thải có thể bổ sung P2 khi xác định phương pháp/tham số riêng. Chưa đưa vào điểm tổng hợp của demo trước khi có module tính và nguồn giả định.

## 3. Người dùng phải nhập gì?

Không yêu cầu người dùng nhập mọi hệ số engine. Tách **thiết kế người dùng quyết định** khỏi **tham số hệ thống quản lý**. Các trường chuyên sâu có thể lấy từ mẫu được gắn nhãn, hoặc nhập ở chế độ nâng cao.

### 3.1 Building plan chung

| Nhóm | Trường cần nhập/xác nhận | Đơn vị/ghi chú |
|---|---|---|
| Vị trí | Polygon khu đất; footprint công trình; hạng mục hiện hữu giữ/phá | WGS84 cho bản đồ; engine dùng hệ tọa độ phù hợp tính toán |
| Quy mô | Công năng/diện tích từng công năng, số tầng, chiều cao, diện tích sàn khi biết, hướng | m², m; hỗn hợp nhiều công năng được tách |
| Người sử dụng | Số căn và cư dân; học sinh/nhân viên; giường bệnh/bệnh nhân/khách theo công năng | Tách người cư trú, nhân viên và khách; không cộng người có mặt thành dân số thường trú |
| Lịch | Giờ hoạt động, ngày làm việc, ca, phân bố đến/rời và mức sử dụng | Lịch theo giờ/khung giờ; tổng phân bố chuẩn hóa |
| Bề mặt | Mái, sân cứng, sân thấm, xanh; chọn vật liệu | Polygon/diện tích, không chồng lặp mặt đất |
| Cây | Giữ/chặt/trồng; vị trí, loại mẫu, tán và chiều cao dự kiến | Tách cây lúc trồng với cây trưởng thành |
| Giới hạn cải thiện | Hạng mục được thay đổi, quy mô tối thiểu, ngân sách hoặc chọn so sánh chi phí | Nếu không nhập ngân sách, báo chi phí, không nói nằm trong ngân sách |

### 3.2 Đầu vào theo module

| Module | Người dùng nhập hoặc chọn mẫu thiết kế | Phần tùy chọn nâng độ chính xác |
|---|---|---|
| Mưa/ngập | Cao độ nền thiết kế/độ nâng nền, điểm xả; bể giữ nước và cách xả; sân thấm/mái xanh | Hồ sơ cao độ/hệ mốc, dung tích ban đầu, tiết diện thiết bị xả, địa chất/thử thấm |
| Giao thông | Cổng vào/ra, hướng/bề rộng, chỗ đỗ theo loại, đón trả và xe dịch vụ | Tỷ lệ phương tiện/nguồn–đích đã khảo sát, thời gian dừng đã đo; không bắt người dùng đoán |
| Nước | Bếp, tưới, thiết bị nước, tái sử dụng; giờ sử dụng đặc thù | Lưu lượng thiết bị/số lượt dùng, hồ sơ điểm đấu nối |
| Nước thải | Loại hoạt động, phần xử lý/tái sử dụng, điểm thu gom nếu thiết kế có | Lưu lượng đo/thiết kế và kết nối được xác nhận |
| Điện | Điều hòa, thiết bị lớn, thang máy/bơm, sạc xe, PV/pin nếu có; lịch hoạt động | Công suất, hiệu suất, setpoint, vỏ công trình, diện tích cửa kính, thông số PV/pin |
| Nhiệt/bóng đổ | Hình khối/chiều cao, vật liệu mái/sân, cây và mặt nước | Đặc tính quang/nhiệt vật liệu và cây đo/nhà sản xuất |
| Dịch vụ/dân cư | Công suất phục vụ thực của dự án, địa điểm/cửa tiếp cận, giờ hoạt động; cư dân mới và phần di dời | Khu vực phục vụ dự kiến, giới hạn tuyển sinh/khám, tải hiện hữu nếu biết |
| Quy hoạch/chi phí | Các ràng buộc đã biết, phần không được sửa, báo giá nếu có | Hồ sơ quy hoạch/đấu nối được cấp cho chủ dự án; không mặc định người dùng có dữ liệu này |

### 3.3 Những hệ số không bắt buộc nhập tay

Hệ thống tự chọn các thư viện ở mục 4 theo công năng, vật liệu và kịch bản. Mỗi giá trị có đơn vị, nguồn, ngày/phiên bản, phạm vi áp dụng và loại `reference`/`estimated`/`synthetic`. Bản triển khai đã có thư viện tổng hợp `thu-duc-demo-library-1.1`; xem phạm vi tham số và giới hạn trong [hướng dẫn](integrated-building-impact.md). Các hệ số địa phương được hiệu chỉnh vẫn cần bổ sung.

## 4. Danh mục hệ số/điều kiện cần cho các model

Đây là danh mục cho phạm vi demo đề xuất, không phải toàn bộ tham số của mọi solver. Chỉ mở tham số tương ứng engine đang sử dụng; không trộn mô hình hệ số đơn giản với tham số vật lý không được engine tiêu thụ.

| Nhóm | Hệ số/đầu vào hệ thống phải quản lý | Nguồn hoặc tạo tổng hợp |
|---|---|---|
| Dòng chảy hiện tại | C mái/sân cứng/sân thấm/xanh (0–1), trận mưa mm, dung tích giữ nước còn trống m³ | Thư viện vật liệu có tài liệu; mưa nguồn/kịch bản; thiết kế. Không tự nhận C là số đo tại khu đất |
| SWMM runoff | Diện tích/độ dốc/chiều rộng dòng chảy, tỷ lệ không thấm, nhám, depression storage; một bộ thấm Horton hoặc Green–Ampt theo cấu hình | Hình học + địa hình; tham số tham khảo hoặc tổng hợp trong miền phù hợp |
| Cống/ngập | Graph cống, cao độ đáy, kích thước/nhám, nút/cửa thu/cửa xả, bơm/van, storage, thủy đồ mưa và mực nước biên | Tạo mạng tổng hợp khi không có; cùng mốc cao độ; giới hạn năng lực low/base/high từ các cấu hình mạng |
| Ngập bề mặt 2D | Cao độ lưới, nhám, building obstacles/porosity theo solver, biên, trao đổi cống–mặt, thời bước | DEM công khai + chỉnh/synthetic ở pilot; resample 30 m xuống 1 m không tạo thêm thông tin thực |
| Phát sinh chuyến | Chuyến/người hoặc theo đơn vị công năng; phân bố đến/rời; tỷ lệ từng phương tiện; occupancy từng loại xe; xe dịch vụ; pass-by/đổi tuyến nếu dùng | Thư viện theo công năng, tham khảo có nguồn hoặc tổng hợp có nhãn |
| SUMO nền/hành vi | OD/tuyến, lưu lượng theo giờ/loại xe, hướng rẽ; làn/kết nối/tốc độ; pha đèn; chiều dài/rộng xe, accel/decel, tau/minGap và tham số lateral nếu bật | OSM + model defaults/reference + synthetic; kiểm tra tính khả thi, không coi defaults là hiệu chỉnh tại TP.HCM |
| Đón trả/đỗ | Sức chứa, thời gian dừng, tỷ lệ vào từng cổng/đón trả, thời gian phục vụ | Thiết kế + phân bố tổng hợp có giới hạn, không tạo xe vô hạn |
| Nước cấp | Suất lít/người/ngày hoặc lưu lượng/số lượt thiết bị; lịch giờ, người hiện diện; tưới/bếp và phần tái sử dụng | Thư viện công năng/thiết bị và lịch dự án; không đếm hai lần nhu cầu |
| EPANET khi dùng | Graph ống, cao độ/nút, chiều dài/đường kính/nhám, bơm/van/bể, đầu nước biên, nhu cầu các nút và pattern | Mạng tổng hợp nhất quán; không suy ra mạng phục vụ thực từ vị trí đường gần nhất |
| Nước thải | Return fraction, lịch/delay nếu có, dòng thải đặc thù, infiltration/inflow khi mô phỏng mạng | Tham khảo/synthetic; không tính nước tưới bay hơi thành nước thải, không áp return fraction lên phần tái dùng hai lần |
| Điện nhu cầu | W/m² hoặc tải từng thiết bị, lịch tải, diversity/coincidence có định nghĩa; HVAC COP/setpoint khi model hỗ trợ | Thư viện công năng/thiết bị và mẫu tổng hợp; tránh áp hệ số đồng thời thêm lần nữa lên lịch đã thể hiện đồng thời |
| Điện mạng | Công suất/giới hạn nhánh, tải nền đồng thời, topology/thông số điện nếu chạy power flow | Synthetic. Bảng kW còn dư chỉ là screening; không gọi kết quả đó là điện áp/power flow |
| Bóng đổ/nhiệt | Hình học, ngày/giờ/vị trí, DSM/DEM, cây; khí tượng/radiation; albedo/emissivity và cấu hình canopy theo model | Nguồn công khai + vật liệu/cây thiết kế + synthetic phần thiếu |
| Dịch vụ/dân cư | Dân số lưới/cơ cấu tuổi khi có, năng lực từng dịch vụ, tải đã dùng, nhu cầu theo nhóm; tốc độ/mode routing và ngưỡng tiếp cận | WorldPop/OSM, tham khảo hoặc synthetic công suất; tổng dân cư bảo toàn khi đổi lưới |
| Giá/chi phí/mục tiêu | Giá chính thức và thời điểm; đơn giá/BOQ; mục tiêu xanh/dòng chảy/hạ tầng/tiếp cận và trọng số nếu dùng | Giá thật được bảo toàn; chi phí/targets tổng hợp có nhãn; không mặc định targets là quy định pháp lý |

Mô hình nhiệt có thể báo Tmrt hoặc chỉ số tiện nghi engine hỗ trợ. Không suy ra mức giảm nhiệt độ không khí bằng một hệ số giảm cây xanh tùy ý. Mô hình điện phân biệt kW tức thời/cao điểm và kWh tích phân theo thời gian.

## 5. Ma trận dữ liệu: có sẵn, fetch và tạo tổng hợp

**Sẵn có** là file/snapshot local đã thấy. **Fetch** là có nguồn/phương thức công khai được khảo sát, chưa phải probe/tải thành công mới cho khu pilot. **Tổng hợp** là việc nhóm phải tạo; hiện chưa có những bộ mới trong repo.

| Feature | Có sẵn local | Có thể lấy không cần xin cơ quan địa phương | Thiếu nhưng tạo tổng hợp được |
|---|---|---|---|
| Xây dựng/hiện trạng | Ranh giới; editor site/footprint và hai variant; chưa có hiện trạng tự nhận diện | OSM footprint; Open Buildings Temporal chiều cao/hiện diện ước lượng | Công trình thiếu thuộc tính; hiện trạng bề mặt cho pilot; ghi vùng synthetic |
| Xanh/tán cây | Các diện tích do người dùng nhập | OSM xanh; Dynamic World/Sentinel-2 | Vị trí/chiều cao/tán cây và vật liệu chưa biết; không coi đất xanh là tán cây |
| Mưa/dòng chảy | JSON mưa history/forecast tại một điểm; engine hệ số | Open-Meteo, IMERG; SoilGrids cho bối cảnh đất | Hyetograph thử nghiệm và tham số thấm/vật liệu; không gán tần suất lặp trận mưa thiếu phân tích |
| Ngập/thoát nước | DataSuds 131 quan sát trong demo; GFM raster 01/10 với 0 positive trong kết quả xử lý; lớp risk quy tắc | Copernicus GLO-30/FABDEM; ảnh GFM và mưa công khai | Cống, cửa thu, cao độ chi tiết, biên triều thử nghiệm, trạng thái ban đầu. Chỉ là mạng/lưu vực giả định |
| Giao thông | JSON OSM dùng ghép giá; engine trips/h hệ số | Tải mạng OSM đầy đủ; TomTom Flow cần key/kiểm tra phủ; báo cáo/phụ lục tham khảo | OD, counts, modal split, pha đèn, đón trả và hành vi xe; TomTom Volume không có VN trong coverage đã kiểm tra |
| Nước | Engine demand theo người; chưa có mạng/tải thật | Tài liệu/thiết bị/mẫu công năng; chưa xác minh API mở công suất mạng local | Graph mạng nếu cần, load pattern, bơm/bể, head/capacity; dùng cho scenario tổng hợp |
| Nước thải | Engine fraction × water; chưa có mạng thu gom | Báo cáo dự án công khai để tham khảo, không phải mạng hoàn công hiện tại | Mạng, tải nền, kết nối/biên; có thể dùng chung topology thoát nước khi loại hệ thống được định nghĩa đúng |
| Điện | Engine kW/người; chưa có tải nền/mạng thật | DOE/EnergyPlus reference models, thông số thiết bị, khí tượng; mẫu Mỹ cần điều chỉnh | Lịch/tải thiết bị chưa biết và mạng/giới hạn thử nghiệm |
| Bóng đổ/nhiệt | Footprint tùy chọn; chưa có DSM/met package/engine | Open Buildings Temporal, khí tượng, Landsat ST và land cover | Cây, vật liệu, chiều cao thiếu; mẫu tổng hợp cùng bối cảnh cho mọi phương án |
| Dân cư/dịch vụ | GPKG mật độ cấp quận; pipeline WorldPop có config, chưa nghiệm thu snapshot dân cư chi tiết | WorldPop 100 m; OSM public facilities/roads | Công suất/tải dịch vụ, phân bố cư trú/khách còn thiếu; không dùng users trường thành cư dân mới |
| Đường/kết nối | OSM JSON; chưa có routing frontend/module đã nghiệm thu | OSM connectivity/access tags | Thuộc tính thiếu và đường/cổng mới theo plan; đường hiện hữu giữ nếu plan không sửa |
| Giá đất/quy hoạch | PDF 195 hàng ứng viên; 1 feature giá duyệt | Mở rộng bảng giá; portal quy hoạch dùng tham khảo, bulk quyền chưa xác minh | Giá thị trường/chi phí/targets thử nghiệm được tạo riêng; không tạo giá chính thức hay quy hoạch pháp lý giả |

Các nguồn mới có thể cần đăng ký tài khoản, API key hoặc điều kiện sử dụng dù không phải xin cơ quan địa phương. Mức phủ/thời điểm phải kiểm tra; dữ liệu cũ không tự trở thành mới bằng cách đổi timestamp. WorldPop năm hiện tại là ước lượng, không phải điều tra tại chỗ; chiều cao Open Buildings V1 tới 2023 cần ghi đúng năm.

## 6. Quy tắc tạo dữ liệu tổng hợp hợp lý

1. Lưu bộ cấu hình, nguồn tham khảo cho miền tham số, seed và phiên bản generator; tái hiện cùng đầu vào.
2. Gắn provenance từng trường/lớp: `observed`, `estimated`, `reference`, `synthetic`, `user_design`. Dữ liệu remote modeled như WorldPop/mưa mô hình không gắn nhãn observed.
3. Giữ hình học thật ở phần có thật. Các mạng/cao độ thêm bằng giả định có extent và nhãn rõ; không thay raster/giá chính thức bằng số giả.
4. Tạo cấu hình **low/base/high cho từng yếu tố**, chưa gán xác suất. Không gọi tất cả là tốt/trung bình/xấu vì hướng tốt phụ thuộc đại lượng.
5. Bảo toàn diện tích, dân số và cân bằng nước; luồng xe phải có nguồn/đích và tính xe chưa chèn/chưa tới đích; tải điện/nước không âm và không đếm hai lần.
6. Cống/ống có topology, kích thước/cao độ/độ dốc hợp lệ; triều và cao độ cùng mốc. Xe có tuyến khả thi; pha đèn không xung đột; sức chứa bãi/đón trả được giới hạn.
7. Dân cư, người có mặt, nhu cầu nước/điện và traffic cùng xuất phát từ lịch/quy mô dự án; lượng nước giữ/tái sử dụng có sổ cân bằng để không giảm runoff và nước cấp bằng hai giả định không liên quan.
8. Giữ cùng điều kiện nền trước/sau và giữa các gợi ý. Thay đổi một yếu tố có kiểm soát để phân tích độ nhạy; không cần chạy mọi tổ hợp 3^N ngay.
9. Kiểm tra vật lý/logic và benchmark của solver. Test pass hoặc đường xe chạy đẹp chưa chứng minh chính xác tại Thủ Đức.
10. Báo cáo tác động kèm cơ sở: `synthetic_scenario`, `uncalibrated_estimate` hoặc mức kiểm chứng thực sự đạt; không gán một % confidence tùy ý.

## 7. Tích hợp engine và luồng web

### Kiến trúc đề xuất

`BuildingPlan + BaselineSnapshot + ParameterLibrary + ScenarioConditions`

→ context chung có phiên bản → các engine theo module → kết quả có đơn vị/thời gian/phạm vi/provenance → đánh giá theo tiêu chí → sinh phương án → tính lại các module bị ảnh hưởng.

- GIS cung cấp thay đổi bề mặt/hình khối và dữ liệu cho runoff/nhiệt.
- Lịch người dùng chung cấp cho traffic, điện, nước, nước thải và dịch vụ; cho phép phân bố khác theo nhóm người.
- Nhu cầu nước cấp nối tới nước thải với phần tái sử dụng/tưới; stormwater giữ riêng trừ khi hệ thống cống chung được mô hình hóa.
- Traffic làm thay đổi tiếp cận theo thời gian nếu routing sử dụng travel times từ SUMO; không tự coi đường vắng có tốc độ cao là tiếp cận tốt cho mọi đối tượng.
- SWMM có thể nhận network synthetic. Ngập vùng 2D cần engine/coupling riêng; không tô vùng buffer lịch sử thành output hydraulic.
- AI diễn giải output và tạo hành động trong schema; engine kiểm tra/chạy lại, AI không tự điền số kết quả.

### Giao diện

1. Vẽ/chọn khu đất; hệ thống nạp hiện trạng hoặc preset có nhãn cho vùng thiếu.
2. Nhập công trình và vận hành; chọn mẫu theo công năng để giảm form.
3. Chọn kịch bản thời tiết/giao thông/hạ tầng; xem nguồn và giả định ở phần nâng cao.
4. Bấm dự tính: dashboard đa feature + bản đồ/lịch theo giờ + thay đổi trước/sau + tác động ra lân cận khi model hỗ trợ.
5. Đánh giá từng tiêu chí, phân biệt lợi ích phục vụ và áp lực; không coi mọi tăng nhu cầu là thất bại.
6. Nhập ràng buộc/ngân sách nếu muốn; tìm gợi ý rồi chạy lại. Giữ công năng/quy mô đã khóa.
7. Lưu/xuất input, baseline, tham số, seed, phiên bản engine, kết quả và nguồn.

## 8. Gợi ý cải thiện đa feature

| Hành động | Module phải tính lại |
|---|---|
| Đổi sân cứng sang thấm/xanh, thêm cây | GIS, runoff, nhiệt/bóng đổ; nước tưới khi xét |
| Thêm bể/rãnh/mái xanh, đổi cao độ/điểm xả | Runoff, SWMM/ngập nếu hỗ trợ; chi phí; nước cấp nếu tái sử dụng |
| Đổi cổng/đón trả/lịch hoạt động | Traffic, tiếp cận, lịch điện/nước/nước thải liên quan |
| Đổi hình khối/chiều cao trong cùng quy mô cho phép | GIS, bóng đổ/nhiệt, điện nếu engine hỗ trợ; tránh vô tình giảm diện tích phục vụ |
| Thiết bị tiết kiệm/tái sử dụng nước | Nước, nước thải, điện phụ trợ, giữ nước khi liên kết, chi phí |
| HVAC/thiết bị/lịch sạc tốt hơn | Điện; tiện nghi trong nhà chỉ khi có model; chi phí |

Các gợi ý tiết kiệm không chỉ đổi một tỷ lệ % để đạt mục tiêu. Cần hành động có mô hình hiệu quả/cost và giới hạn tương ứng; nếu hiện chỉ là mục tiêu vận hành, ghi rõ chưa chứng minh giải pháp thực tế.

## 9. Lộ trình triển khai toàn hệ thống

| Giai đoạn | Công việc | Kết quả nghiệm thu |
|---|---|---|
| A. Hợp đồng chung | Chốt schema building/baseline/lịch/provenance; preset nhiều công năng, parameter library; nguồn và synthetic generators | Đầu vào một lần dùng cho mọi module; không ép người dùng nhập hệ số kỹ thuật |
| B. Vòng đa feature cơ bản | GIS xanh/xây dựng; nâng runoff hiện có; điện/nước/nước thải theo lịch; dịch vụ/dân cư; tích hợp dữ liệu thật hiện có | Building → dashboard tác động nhiều feature, units đúng, trước/sau cùng nền |
| C. Các mô hình theo không gian/thời gian | SUMO traffic và SWMM mạng thử nghiệm; bóng đổ, SOLWEIG khi đủ; routing services | Engine được chạy thực với synthetic có nhãn; kiểm tra balance, route, geometry và output |
| D. Gợi ý và AI | Hành động đa feature; tính lại module liên quan, bảng đánh đổi/Pareto; AI giải thích có bằng chứng | Giữ quy mô, báo goals còn thiếu, mọi số AI lấy từ output |
| E. Bàn giao | Local/Docker/API/UI tests, report, commit/push branch và CI; deploy máy 156 | Có thể tái hiện inputs/seed/version; snapshot và rollback; demo nhiều công năng |

Không ưu tiên xong traffic rồi mới nghĩ phần còn lại. Giai đoạn B tạo luồng đa feature trước; SUMO/SWMM/nhiệt là các module mở rộng cùng context.

## 10. Phạm vi cam kết demo

- Bắt buộc: building/green/impervious; runoff; nhu cầu điện/nước/nước thải; dân cư/dịch vụ ở mức dữ liệu hỗ trợ; báo cáo đa tiêu chí, synthetic có nhãn và gợi ý được tính lại.
- Nâng cấp chính: traffic SUMO, drainage SWMM, bóng đổ; chúng có mô hình nền tổng hợp khi thiếu dữ liệu thật.
- Có điều kiện: nhiệt SOLWEIG, ngập 2D, mạng cấp nước EPANET, năng lượng EnergyPlus. Không đổi tên screening thành solver chuyên sâu nếu chưa tích hợp.
- Giá/quy hoạch: giữ bối cảnh thật và coverage; thử tài chính tổng hợp tách riêng, không gán giá/quy hoạch giả cho địa điểm thật.

Trạng thái khi lập kế hoạch ngày 06/10: chỉ có engine công thức. Ngày 07/10 đã triển khai SUMO, SWMM và bóng đổ; SOLWEIG/EPANET/EnergyPlus/2D chưa chạy. Chi tiết implementation thay thế các giả định thiết kế trong tài liệu này nằm ở [hướng dẫn hiện tại](integrated-building-impact.md).

## 11. Nguồn và tài liệu liên quan

- [Tình trạng demo](demo-status-and-feature-roadmap.md); [khảo sát nguồn](data-source-survey-and-demo-inputs.md); [probe dữ liệu cũ](assigned-data-availability.md).
- [EPA SWMM](https://www.epa.gov/water-research/storm-water-management-model-swmm): runoff/drainage/LID và mạng thủy lực.
- [SUMO OSM](https://eclipse.dev/sumo/docs/Networks/Import/OpenStreetMap.html), [demand](https://eclipse.dev/sumo/docs/Demand/Introduction_to_demand_modelling_in_SUMO.html), [sublane](https://eclipse.dev/sumo/docs/Simulation/SublaneModel.html): model giao thông và hành vi lateral khi cần cho hỗn hợp xe.
- [SOLWEIG](https://github.com/UMEP-dev/solweig/blob/main/README.md): đầu vào/đầu ra nhiệt ngoài trời.
- [DOE reference buildings](https://www.energy.gov/cmei/buildings/commercial-reference-buildings): mẫu năng lượng theo công năng; bối cảnh Mỹ cần điều chỉnh.
- [Open Buildings Temporal](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1), [Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1), [Copernicus DEM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM), [WorldPop release](https://data.worldpop.org/repo/prj/Global_2015_2030/R2025A/doc/Global2_Release_Statement_R2025A_v1.pdf): dữ liệu nền được mô hình hóa, cần kiểm tra năm/độ phủ.
- [TomTom Volume coverage](https://docs.tomtom.com/traffic-stats/documentation/api/traffic-volume): chưa có Việt Nam trong danh sách khảo sát; không gộp coverage với Traffic Flow.

Không dùng liên kết Google Sheets trong Word làm bằng chứng dữ liệu: nội dung các sheet chưa được đọc trong lần lập kế hoạch này. Bảng trạng thái dựa vào file/code local và nguồn đã khảo sát, không suy đoán phần việc nhóm chưa bàn giao.

## 12. Đối chiếu toàn bộ 32 trường số ngoài building plan trong UI hiện tại

Các trường dưới đây hiện vẫn nhập tay hoặc được nạp từ ví dụ giả định; kế hoạch đề xuất chuyển chúng sang hệ thống/preset. Không tính diện tích bề mặt, số tầng/người và footprint thuộc thiết kế. Không tính ô nguồn hoặc checkbox.

| Số | Trường hiện tại | Cách xử lý ở demo mới |
|---|---|---|
| 1 | Tổng mưa trận xét, mm | Tự lấy hoặc chọn kịch bản mưa; nâng lên chuỗi mưa nếu SWMM |
| 2–5 | C mái, sân cứng, sân thấm, đất xanh | Hệ thống chọn theo vật liệu, cho override nâng cao |
| 6 | Chuyến/người/giờ | Thư viện công năng/lịch; thay bằng chuỗi trips khi SUMO |
| 7 | Tỷ lệ xe cá nhân | Preset kịch bản; nâng thành cơ cấu từng mode, không tự gọi là số đo |
| 8 | Số người/xe | Thư viện theo từng loại phương tiện |
| 9 | Lít nước/người/ngày | Thư viện công năng/thiết bị, bổ sung lịch |
| 10 | Tỷ lệ nước thải | Thư viện theo hoạt động, tách tưới/tái sử dụng |
| 11 | kW/người | Screening library; nâng sang tải thiết bị/lịch, không dùng để tính năng lượng nếu thiếu thời gian |
| 12 | Chuyến xe/giờ đường còn tiếp nhận | Loại khỏi form cơ bản; SUMO tính theo mạng/nền kịch bản, không đồng nhất với một hằng số capacity |
| 13–15 | Công suất còn dư nước, nước thải, điện | Nền tổng hợp có nhãn hoặc hồ sơ thực; không coi là năng lực thực của địa điểm |
| 16 | Mức tăng runoff cho phép, % | Preset mục tiêu dự án, người dùng chỉnh tùy chọn |
| 17 | Tỷ lệ xanh tối thiểu, % | Như trên; không tự nhận pháp lý |
| 18 | Impervious tối đa, % | Như trên |
| 19 | Sân cứng tối thiểu | Ràng buộc thiết kế: người dùng nhập/chọn mẫu |
| 20–21 | Chuyển sang xanh/thấm tối đa | Ràng buộc thiết kế: người dùng chọn phần được sửa hoặc preset |
| 22 | Giữ nước bổ sung tối đa | Khả năng bố trí của plan/preset; không suy ra từ dữ liệu vệ tinh |
| 23 | Ngân sách | Người dùng nhập tùy chọn; không có thì chỉ so chi phí |
| 24–26 | Đơn giá xanh/thấm/giữ nước | Thư viện chi phí có ngày/nguồn; thiếu thì synthetic |
| 27 | Tỷ lệ xe cá nhân thấp nhất | Giới hạn vận hành tham khảo hoặc người dùng xác nhận; không giảm vô căn cứ |
| 28–29 | Tiết kiệm nước/giảm điện tối đa | Thay bằng lựa chọn giải pháp cụ thể có mô hình hiệu quả; preset giả định khi chưa có |
| 30–32 | Chi phí/điểm % giảm xe, tiết kiệm nước, giảm điện | Thay bằng cost của hành động cụ thể; chưa có báo giá thì báo synthetic, tránh tuyến tính giả tạo |

Checkbox khả thi chuyển phương tiện hiện tại cần đổi thành mô tả hành động và cơ sở (xe đưa đón/lịch/phương tiện tiếp nhận), không chỉ tick để biến mục tiêu thành hiệu quả thực tế. Nguồn của hệ số/chi phí/targets được hệ thống lưu và hiển thị, người dùng bổ sung khi override.
