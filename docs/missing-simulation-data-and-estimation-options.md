# Bù dữ liệu thiếu cho simulation tác động công trình

**Khảo sát:** 09/10/2026. **Pilot:** chung cư tại Thủ Đức. Ba nhóm khảo sát: giao thông; ngập/thoát nước; hạ tầng/dịch vụ/vi khí hậu.

## 1. Kết luận và mức xác minh

Có phương án cho phần lớn dữ liệu thiếu: lấy hình học thật từ nguồn mở, ước lượng nhu cầu bằng dân số/công năng/lịch và sinh mạng hoặc tham số tổng hợp có quy tắc. Chưa xác minh được bộ dữ liệu công khai hiện thời cung cấp đầy đủ lưu lượng xe, OD, tín hiệu, cống và công suất còn dư điện/nước tại khu demo.

Khảo sát đã đọc tài liệu, trang dữ liệu, repository và một số PDF nghiên cứu chính thức. **Chưa tải và nghiệm thu các bộ mới tại khu pilot, chưa chạy SWMManywhere/EPANET/SOLWEIG, chưa bổ sung ETL hoặc thay code simulation.** Link download/API là đầu mối truy cập, không phải bằng chứng đã fetch thành công. Không commit/push trong lần khảo sát này.

Kết quả bổ sung cho [kế hoạch tích hợp](integrated-building-impact-plan.md) và [khảo sát trước](data-source-survey-and-demo-inputs.md). Cho phép dữ liệu giả hợp lý giúp demo khả thi, nhưng không biến dữ liệu tổng hợp thành hiện trạng thực tế.

## 2. Bảng quyết định

| Khoảng trống | Nguồn hoặc thuật toán | Mức khả thi cho demo | Giới hạn chính |
|---|---|---|---|
| Mạng đường và thuộc tính thiếu | OSM → SUMO netconvert; defaults theo loại đường có nhãn | Cao | Thiếu làn/hướng rẽ cần kiểm tra; không lấy tuyến API làm toàn bộ graph |
| Lưu lượng xe theo đường | Video liên tục được phép sử dụng → detector/tracker → counts; chưa có video thì assignment từ OD tổng hợp | Trung bình | Không suy số xe/giờ duy nhất từ tốc độ hoặc ảnh đơn |
| OD và nguồn/đích chuyến đi | Dân số + công năng/POI + lịch → trip generation → Gravity/Radiation → assignment | Cao cho kịch bản | Quy mô tổng chuyến và mode share vẫn cần prior/khảo sát |
| Hướng rẽ/tuyến | SUMO routeSampler fit counts/turns khi có số đo | Có điều kiện | Nghiệm không duy nhất, phải giữ dữ liệu kiểm chứng độc lập |
| Tín hiệu giao thông | OSM vị trí → netconvert → Webster/cycle adaptation, offset coordination | Cao cho tín hiệu tổng hợp | Không tái tạo chương trình đèn thực tế |
| Hành vi xe máy/queue | Nghiên cứu TP.HCM làm prior; sublane; hiệu chỉnh nhiều metric khi có video | Trung bình | Default hoặc nghiên cứu nước ngoài chưa phải calibration địa phương |
| Mạng cống, hố ga, diameter/invert | SWMManywhere từ đường + DEM + footprints; ensemble mạng | Cao cho mô hình sơ bộ | Mạng synthetic, không phải hồ sơ hoàn công |
| Địa hình mặt đất | FABDEM; kiểm tra DeltaDTM vùng thấp; Copernicus DEM làm bối cảnh | Trung bình | 30 m không đủ bó vỉa, cao độ sân/cửa thu; không tăng độ chính xác bằng resampling |
| Thấm đất | SoilGrids + pedotransfer → Green–Ampt priors | Trung bình | Đất đô thị san lấp/nén có thể khác lớp đất vùng |
| Biên triều/cửa xả | UHSLC Vũng Tàu, FES2022 cho biên ngoài biển; truyền triều cần mô hình riêng | Thấp cho cửa xả thực | Không thay trực tiếp mực nước Thủ Đức; thiếu datum/bathymetry/river flow |
| Bơm/tắc/van | Kịch bản có quy tắc và phân tích độ nhạy | Cao cho demo | Không quan sát đáng tin bằng vệ tinh |
| Dân số nền/tuổi | WorldPop Global2 2025 + điều tra dân số; phân bổ về buildings | Cao | Dữ liệu modeled, không đếm người từng nhà |
| Nhu cầu điện/nước/nước thải | Thư viện hệ số theo công năng + lịch; EnergyPlus khi đủ input | Cao | Hệ số cần nguồn/phạm vi; không suy công suất dư |
| Năng lực mạng điện/nước | Scenario low/base/high; benchmark SimBench/WNTR; EPANET/power flow khi đủ mạng | Cao cho scenario | Không xác nhận đấu nối, áp lực hoặc công suất dư địa phương |
| Sức chứa trường/bệnh viện | Danh sách cơ sở + báo cáo từng cơ sở; synthetic capacity nếu thiếu | Trung bình | POI không cho occupancy/chỗ trống |
| Tiếp cận dịch vụ | Routing theo mạng; capacity allocation/2SFCA khi có capacity | Cao | Nếu thiếu capacity chỉ báo accessibility và nhu cầu |
| Chiều cao/cây/vật liệu | Open Buildings, tree typology, vật liệu tham khảo → bóng đổ/SOLWEIG | Cao cho bóng đổ; có điều kiện cho nhiệt | Tmrt/LST không phải nhiệt độ không khí |

## 3. Giao thông: nguồn mới và pipeline

### 3.1 Nguồn tham khảo có căn cứ địa phương

- [JICA Southern Roads and Bridges 2016](https://openjicareport.jica.go.jp/pdf/12305017_01.pdf): có mô tả khảo sát counts và phỏng vấn OD. Báo cáo dẫn Appendix-2; chưa nghiệm thu bảng phụ lục hoặc xác nhận trạm tại đường cạnh pilot. Không dùng số liệu 2016 làm counts năm 2026.
- [JICA SAPI Metro Line 1](https://openjicareport.jica.go.jp/pdf/12176475.pdf): khảo sát và mô hình hành lang Bến Thành–Suối Tiên; đầu mối prior về phân vùng/OD, chưa trích xuất bảng cụ thể cho pilot.
- [Luận án Huỳnh Đức Nguyễn, TU Darmstadt](https://tuprints.ulb.tu-darmstadt.de/server/api/core/bitstreams/4f012cc2-25f6-4408-986f-4ac3440501b0/content): mô hình năng lực nút giao có quan trắc TP.HCM, xét dòng xe máy, bề rộng và hướng rẽ. Dùng prior/benchmark discharge; không phải bộ tham số SUMO sẵn có hay counts hiện tại.
- [HCMUT-UAV](https://github.com/nhoanhsdh21-stack/HCMUT-UAV-dataset): README mô tả 4.811 ảnh và nhãn detection. License đang để trống; chưa tải bộ dữ liệu. Chỉ hai lớp motorbike/car, trong đó car gộp cả một số phương tiện lớn. **Chưa chọn làm dữ liệu tích hợp** trước khi rõ quyền sử dụng. Ảnh rời rạc không thay chuỗi video counts.
- [pNEUMA, EPFL](https://open-traffic.epfl.ch/): trajectory mở để phát triển thuật toán tracking/hành vi; dữ liệu Athens, không calibration Thủ Đức.

### 3.2 Phương án thuật toán

1. Nạp mạng OSM thật, gồm đường xuyên vùng và nguồn/đích ngoài biên. Không coi mọi xe là cư dân của khu pilot.
2. Chia traffic zones; dùng dân số để tạo trips phát sinh, công năng/POI/sàn sử dụng để tạo trips thu hút; tách đi làm, đi học, khách và dịch vụ.
3. Dùng Gravity/Radiation để phân bố OD, với tổng trips và lịch có căn cứ. [Radiation, bài gốc](https://arxiv.org/abs/1111.0586). Chưa cần DeepGravity nếu không có nhãn OD để huấn luyện.
4. Gán routes lên mạng. Khi có counts/turns, dùng [SUMO routeSampler](https://eclipse.dev/sumo/docs/Demand/Routes_from_Observation_Points.html) để fit. Counts không xác định duy nhất mọi OD/tuyến.
5. Sinh tín hiệu bằng netconvert, dùng [tlsCycleAdaptation/tlsCoordinator](https://eclipse.dev/sumo/docs/Tools/tls.html) khi phù hợp. Đây là thiết kế tổng hợp; giữ cùng signal trước/sau trừ khi thử can thiệp tín hiệu.
6. Chọn phân bố hành vi xe theo loại, dùng sublane; kiểm tra travel time, discharge flow, throughput, queue và trips chưa hoàn thành.
7. Thêm trips/cổng/đón trả của building rồi so với baseline cùng cấu hình và seed.

**Quan trắc nhỏ có giá trị:** nếu nhóm quay được video được phép sử dụng, thu counts theo hướng/loại xe, nhiều chu kỳ đèn, discharge và queue. Detector + tracker đếm qua vạch, aggregate 5–15 phút. Kiểm tra thủ công một mẫu và giữ một khung giờ/ngày riêng để validation. Ảnh camera đơn chỉ hỗ trợ xe hiện diện, không trực tiếp counts theo giờ; homography/điểm tỷ lệ cần cho queue theo mét.

## 4. Ngập: SWMManywhere và cách xử lý dữ liệu thiếu

### 4.1 Công cụ đáng thử

[SWMManywhere](https://github.com/ImperialCollegeLondon/SWMManywhere) là công cụ nghiên cứu sinh mô hình thoát nước tổng hợp từ mạng đường, DEM và công trình. Có thể xuất SWMM `.inp` cùng nodes/edges/subcatchments GeoJSON. [Paper 2025](https://doi.org/10.1016/j.envsoft.2025.106358), [quickstart](https://imperialcollegelondon.github.io/SWMManywhere/quickstart/).

Phù hợp để nâng mạng toy hiện tại thành mạng synthetic phụ thuộc vị trí. Chưa có bằng chứng công cụ đã hiệu chỉnh tại Thủ Đức. Vùng bằng phẳng và chịu triều cần review cửa xả, invert/slope, bơm và kết nối; không tự tin DEM 30 m xác định được cống thật. Cửa xả tự sinh/dummy phải được liệt kê.

### 4.2 Nguồn bổ sung

- [FABDEM V1-2](https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/): địa hình khoảng 30 m giảm ảnh hưởng cây/công trình. CC BY-NC-SA; kiểm tra giấy phép nếu chuyển sang thương mại.
- [DeltaDTM](https://www.nature.com/articles/s41597-024-03091-9), [archive](https://doi.org/10.4121/21997565): địa hình vùng thấp ven biển, cần kiểm tra mask/coverage. Không mặc định phù hợp để trích mạng cống.
- [SoilGrids raster](https://files.isric.org/soilgrids/latest/data/), [API docs](https://rest.isric.org/soilgrids/v2.0/docs): texture/bulk density → pedotransfer → tham số thấm ước lượng. Không coi Ksat suy luận là đo địa chất tại khu đất; trạng thái API cần probe.
- [UHSLC](https://uhslc.soest.hawaii.edu/data/), [Vũng Tàu II](https://psmsl.org/data/obtaining/stations/2268.php): đầu mối hourly/daily. PSMSL monthly không đủ cho trận ngập vài giờ.
- [FES2022](https://www.aviso.altimetry.fr/en/data/products/auxiliary-products/global-tide-fes/release-fes22.html): mô hình triều cần đăng ký. UHSLC/FES là bối cảnh ngoài biển; muốn dùng tại cửa xả nội đô phải mô hình hóa truyền triều và đồng nhất mốc cao độ. Chưa xác minh chuỗi công khai đủ dùng tại Phú An/Nhà Bè.
- [Bộ dữ liệu ngập TP.HCM của IRD](https://dataverse.ird.fr/dataset.xhtml?persistentId=doi:10.23708/8Y16HU): đối chiếu sự kiện/vị trí và trường độ sâu khi có. Kiểm tra phiên bản, thời gian, nguyên nhân và độ chính xác; dữ liệu báo chí có selection bias, không đủ hiệu chỉnh toàn bộ cống.

### 4.3 Pipeline và đầu ra hợp lý

AOI theo lưu vực/cửa xả → đường + DTM + footprints + land cover → mạng SWMManywhere → nhiều cấu hình capacity/invert/outfall/blockage/boundary → baseline và building trên từng cấu hình giống nhau.

Nếu xét backwater/triều, dùng SWMM Dynamic Wave với biên phù hợp; EPA mô tả hỗ trợ backwater, dòng ngược và dòng có áp. [SWMM manual](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT).

Báo chênh lệch runoff, peak discharge, overflow volume, thời gian quá tải và khoảng nhạy theo giả định. Kiểm tra continuity error/topology/cửa xả trước khi so với quan trắc. **Bản đồ độ sâu cần mô hình bề mặt 2D/coupling và địa hình phù hợp**; không tô buffer nút cống hoặc resample 30 m thành 1 m rồi gọi là độ sâu chính xác.

## 5. Dân số, hạ tầng, dịch vụ và nhiệt

### 5.1 Dân số và chức năng công trình

[WorldPop Global2](https://hub.worldpop.org/project/categories?id=3) có sản phẩm dân số và cơ cấu tuổi/giới; [Việt Nam age-sex 2025](https://hub.worldpop.org/geodata/summary?id=83167). [API v2](https://api.worldpop.org/v2/) mô tả tổng hợp polygon; chưa thử request khu pilot. Dữ liệu là modeled/projection, không phải đếm người từng nhà. [Điều tra dân số giữa kỳ 2024](https://www.gso.gov.vn/wp-content/uploads/2024/12/Dieu-tra-Dan-so-giua-ky-2024-31.12-2.pdf) bổ sung bối cảnh quy mô hộ.

Join công trình với OSM landuse/building/amenity và danh sách cơ sở để suy công năng có nhãn. Phân bổ dân số ô lưới bằng trọng số diện tích sàn ở, chuẩn hóa để bảo toàn tổng dân số; không cộng dân số WorldPop và dân số phân bổ thêm lần nữa. Công trình mới lấy số người từ số căn/quy mô và mẫu vận hành người dùng xác nhận.

### 5.2 Nhu cầu tính được, công suất dư chưa biết

- Nước: số người/hoạt động × suất dùng + tưới/rửa → profile giờ.
- Nước thải: phần nước đi vào cống theo hoạt động và cân bằng tái sử dụng; không coi nước tưới đều thành nước thải.
- Điện: thiết bị/công năng/diện tích/người × lịch dùng → kW đỉnh và kWh. Tránh áp hệ số đồng thời hai lần.

Hệ số quy hoạch/thiết kế có thể tham khảo tài liệu QCVN và công trình tương đồng; cần rà phiên bản, định nghĩa và phạm vi trước khi đưa vào thư viện. Chưa audit quy định hiện hành nên không đưa số cụ thể hoặc kết luận tuân thủ trong khảo sát này.

[EnergyPlus](https://energyplus.net/) và [URBANopt](https://research-hub.nrel.gov/en/publications/urbanopt-an-open-source-software-development-kit-for-community-an/) tạo tải giờ theo archetype khi đủ envelope/HVAC/weather/lịch. Mẫu nước ngoài phải điều chỉnh bối cảnh Việt Nam.

Chưa có mạng/đấu nối/tải nền thì chỉ kết luận nhu cầu tăng thêm. Demo có thể so với capacity low/base/high, gắn nhãn synthetic. Nếu thử solver mạng: [EPANET](https://www.epa.gov/water-research/epanet) / [WNTR example libraries](https://usepa.github.io/WNTR/libraries.html) cho nước; [SimBench](https://simbench.de/en/download/) cho benchmark lưới điện. Các mạng mẫu kiểm tra thuật toán, không đại diện feeder/DMA Thủ Đức.

### 5.3 Dịch vụ

[Danh mục dữ liệu mở TP.HCM 2024](https://dost.hochiminhcity.gov.vn/documents/2121/Danh_muc_DL_mo-tbdg_signed_1.pdf) mô tả danh sách trường. Có danh sách không đồng nghĩa đã tải được capacity/occupancy/chỗ trống. Khảo sát chưa tìm được bộ citywide cập nhật đủ các trường này.

Làm accessibility theo mạng và nhóm tuổi trước. Khi có capacity, dùng phân bổ có ràng buộc sức chứa, 2SFCA hoặc min-cost flow. Khi thiếu capacity, báo nhu cầu/tiếp cận; synthetic capacity chỉ dùng scenario. Không biến diện tích trường hoặc POI thành số chỗ trống thực tế.

### 5.4 Nhiệt và bóng đổ

Hình học footprint/height + vị trí Mặt Trời cho bóng đổ. [SOLWEIG/UMEP](https://umep-docs.readthedocs.io/en/latest/OtherManuals/SOLWEIG.html) dùng DSM/cây/khí tượng để tính môi trường bức xạ và tiện nghi nhiệt. Cây thiếu thuộc tính có thể dùng typology theo khoảng chiều cao/tán. Tmrt hoặc nhiệt độ bề mặt không phải mức thay đổi nhiệt độ không khí; SOLWEIG không tự thay mô hình gió/CFD.

## 6. Ưu tiên triển khai đề xuất

1. **Baseline phụ thuộc vị trí:** OSM thật, WorldPop, footprints/height và land cover. Lưu snapshot/coverage/thời điểm/giấy phép. Pilot mạng giao thông và lưu vực có biên hợp lý, không cố full-city ngay.
2. **Giao thông:** trip generation → Gravity/Radiation → SUMO trên mạng thật; low/base/high khi chưa có counts. Quay/nhận video hợp lệ để hiệu chỉnh và kiểm chứng nếu khả thi.
3. **Ngập:** thử SWMManywhere, review topology/outfalls; ensemble synthetic; kiểm tra quan trắc IRD. Trước mắt báo runoff/overflow; chưa ưu tiên depth map 2D khi địa hình thiếu.
4. **Hạ tầng/dịch vụ:** nhu cầu điện/nước/nước thải theo profile giờ và accessibility; scenario capacity rõ nhãn. Chỉ nâng EPANET/power flow khi có mạng hoặc muốn demo mạng tổng hợp riêng.
5. **Nhiệt:** hiện trạng hình học → bóng đổ → SOLWEIG khi đã có input phù hợp.
6. **Đánh giá và gợi ý:** giữ quy mô/công năng người dùng khóa; đánh giá phương án gốc trước, sinh cải thiện và chạy lại engine. Báo phương án có giữ lợi ích trong nhiều cấu hình nền hay không; không gán confidence phần trăm tùy ý.

Không cần ML cho mọi khoảng trống. Mô hình vật lý, phân bổ và tối ưu ràng buộc phù hợp khi nhãn địa phương còn thiếu. ML có thể hỗ trợ CV đếm xe, phân loại công năng hoặc surrogate sau khi có dữ liệu; không dùng nó để giả vờ khôi phục mạng cống/điện/nước thật.

## 7. Hợp đồng dữ liệu và kiểm chứng

- Mỗi trường có source URL, đơn vị, thời điểm, phạm vi, phương pháp, version/seed và nhãn `observed`, `historical`, `estimated`, `reference`, `synthetic`, `user_design`.
- Low/base/high là cấu hình thử nghiệm, không mặc định các phân vị/xác suất của thực tế.
- So before/after trên cùng baseline, seed và điều kiện; khoảng kết quả do giả định không phải sai số thống kê đã hiệu chỉnh.
- Kiểm tra bảo toàn dân số, trips, diện tích, cân bằng nước, kết nối mạng và tải không âm.
- Có quan trắc thì tách calibration/validation. Test phần mềm hoặc benchmark solver chỉ chứng minh tính đúng của luồng tính, không chứng minh dự báo đúng tại Thủ Đức.
- Người dùng nhập building plan đủ mô tả hình học, công năng/quy mô, lịch, cổng/đón trả, bề mặt/cây và hệ thống thiết kế đặc thù. Hệ thống chọn hệ số và nguồn nền; không bắt người dùng đoán lưu lượng nền hoặc công suất dư.

## 8. Probe camera công khai ngày 09/10/2026

Đã thử kiểm tra endpoint được liệt kê trong [mã nguồn danh mục camera WazeVN](https://greasyfork.org/en/scripts/497466-wme-wazevn-traffic-cams-list/code), chưa chạy hoặc cài userscript:

- Camera Phạm Văn Đồng – Kha Vạn Cân 1: `https://giaothong.hochiminhcity.gov.vn:8007/Render/CameraHandler.ashx?id=6623f3436f998a001b252863`. Một lần probe trả HTTP 403 `text/html`; lần sau timeout kết nối 10 giây. Chưa xác định nguyên nhân 403 và chưa có payload ảnh/video.
- `https://giaothong.hochiminhcity.gov.vn/Map.aspx`: HTTP client timeout kết nối; công cụ web đọc được trang tối giản, không cung cấp request động.
- Host có `www`: Python báo certificate hostname mismatch. Không tắt kiểm tra TLS hoặc vượt cảnh báo chứng chỉ.
- Browser automation không có browser được kết nối (`browsers: []`), nên chưa quan sát DevTools/Network khi bấm camera.

**Kết luận:** tìm được đầu mối endpoint, chưa chứng minh stream hoạt động hoặc response là JPEG/video. Chưa fetch ảnh, quay video, tạo chuỗi counts hoặc tích hợp ETL. Không suy kiểu nội dung từ đuôi `.ashx`.

Bước tiếp theo cần một phiên trình duyệt mở được trang: DevTools → Network → chọn camera → xác định Content-Type, cadence và request HLS/MJPEG/WebRTC nếu có. Có thể cung cấp HAR sanitized không kèm cookie/token hoặc tên request + Content-Type để tiếp tục phân tích. Nếu gặp kiểm soát truy cập, cần quyền phù hợp từ đơn vị cung cấp.
