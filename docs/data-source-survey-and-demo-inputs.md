# Khảo sát dữ liệu bổ sung và đầu vào simulation

**Ngày khảo sát:** 06/10/2026. **Phạm vi:** khu pilot tại Thủ Đức, hỗ trợ nhiều công năng công trình.

**Kế hoạch tiếp theo:** xem [simulation tác động tổng hợp](integrated-building-impact-plan.md). Sau khi người dùng xác nhận ban tổ chức cho phép dữ liệu giả hợp lý, phần dữ liệu không xin được có thể được tạo tổng hợp có nhãn cho demo. Các nhận xét dưới đây về dữ liệu cần xin áp dụng cho độ chính xác thực tế, không ngăn dựng kịch bản tổng hợp.

## 1. Kết luận

Có nguồn bổ sung cho những phần đang thiếu: mạng đường/tốc độ, hiện trạng bề mặt, chiều cao công trình ước lượng, địa hình vùng và nhiệt độ bề mặt. Tuy nhiên, nguồn công khai chưa đủ để dựng mô hình chính xác cho mọi khu đất. Dữ liệu cống, cao độ chi tiết, pha đèn, lưu lượng xe phân loại và tải mạng điện/nước cần được khảo sát hoặc nhận từ đơn vị quản lý.

Trải nghiệm chỉ nhập building plan vẫn khả thi nếu nhóm chuẩn bị dữ liệu nền cho khu pilot và quản lý thư viện tham số. Người dùng nên nhập thông tin thiết kế/vận hành mà hệ thống không thể quan sát từ vệ tinh, thay vì phải chọn hệ số kỹ thuật.

**Mức xác minh:** khảo sát tài liệu và trang chính thức bằng web; đã đọc nội dung báo cáo PDF về ngập. Chưa chạy probe mới, tải/cắt raster, xác minh API có key hoặc kiểm định độ chính xác tại khu đất. Các nguồn không được coi là đã tích hợp chỉ vì có tài liệu. Kết quả probe cũ nằm trong [assigned-data-availability.md](assigned-data-availability.md).

## 2. Giao thông

| Nguồn | Dữ liệu hỗ trợ | Cách tiếp cận và giới hạn | Quyết định đề xuất |
|---|---|---|---|
| [OpenStreetMap → SUMO](https://eclipse.dev/sumo/docs/Networks/Import/OpenStreetMap.html) | Mạng đường, hướng đi và các thuộc tính được khai báo | Nhập mạng vào SUMO; kiểm tra làn, kết nối, hạn chế rẽ và thuộc tính bị suy đoán. Chưa chứng minh đầy đủ quanh khu pilot | Dùng làm nền, review tại hiện trường |
| [TomTom Traffic coverage](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/product-information/market-coverage) và [Flow Segment Data](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data) | Có Việt Nam trong danh mục phủ; tốc độ, thời gian di chuyển, đóng đường, chỉ số chất lượng | Cần tài khoản/key và kiểm tra phạm vi từng đường, điều kiện lưu trữ/sử dụng. Response Flow Segment được mô tả không cung cấp số xe/giờ hoặc OD | Probe khu pilot trước; dùng kiểm tra tốc độ/thời gian |
| [Cổng giao thông TP.HCM](https://www.giaothong.hochiminhcity.gov.vn/) | Có mục camera và thông tin giao thông | Trang khảo sát có mục đang cập nhật và timestamp không đồng nhất; chưa xác minh stream video, chuỗi lịch sử hoặc API tải dữ liệu | Đầu mối kiểm tra/xin chia sẻ; chưa dựa vào để cam kết có video đếm xe |
| [JICA HOUTRANS](https://openjicareport.jica.go.jp/710/710/710_123_11764610.html) và [khảo sát đường/cầu phía Nam](https://openjicareport.jica.go.jp/pdf/12305017_02.pdf) | Báo cáo khảo sát/nhu cầu giao thông, nền phương pháp và dữ liệu lịch sử | Dữ liệu cũ; không dùng làm lưu lượng hiện tại của nút giao | Tham khảo phương pháp; chọn số liệu có địa điểm/thời điểm rõ |
| [ITE Trip Generation](https://www.ite.org/technical-resources/topics/trip-and-parking-generation-v2/trip-parking-generation-ites-flagship-resources/) và [phụ lục](https://www.ite.org/tripgenappendices/) | Suất phát sinh chuyến, phân bố theo thời gian/công năng | Bộ chính cần quyền truy cập; một số phụ lục công khai. Tập dữ liệu chủ yếu phục vụ bối cảnh Bắc Mỹ; cần kiểm tra khả năng chuyển sang TP.HCM | Thư viện tham khảo, ưu tiên khảo sát công trình tương đồng tại địa phương |

**Chưa được giải quyết:** dòng xe máy/ô tô/buýt/tải theo thời gian, hướng rẽ, OD/tuyến, pha đèn thực tế, hành vi đón trả và hàng chờ. Có thể dùng khảo sát hoặc video được cấp quyền; CV đếm xe cần kiểm tra sai số theo loại xe, che khuất và ánh sáng. Một camera không xác định đủ OD toàn mạng.

[SUMO routeSampler](https://eclipse.dev/sumo/docs/Demand/Routes_from_Observation_Points.html) hỗ trợ dựng nhu cầu từ số đếm/hướng rẽ/OD, nhưng nhiều phân bố tuyến có thể phù hợp cùng số đếm. Cần kiểm chứng độc lập trước khi dự báo tác động sau xây.

## 3. Địa hình, mưa, cống và ngập

| Nguồn | Dữ liệu hỗ trợ | Giới hạn và cách dùng |
|---|---|---|
| [Copernicus DEM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) | DSM toàn cầu 30/90 m, có tải/API theo điều kiện truy cập | DSM gồm công trình/cây, không phải cao độ đất trần. Phù hợp bối cảnh vùng; chưa đủ mô tả bó vỉa/cổng/rãnh để dự báo ngập đường nhỏ |
| [FABDEM V1-2](https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/) | Địa hình khoảng 30 m đã giảm ảnh hưởng cây/công trình | Vẫn thô; không thay khảo sát. CC BY-NC-SA 4.0; sử dụng thương mại cần trao đổi với nhà cung cấp |
| [Báo cáo khảo sát thiệt hại ngập của TP.HCM](https://ttqlhtkt.hochiminhcity.gov.vn/documents/20197/31303/1.%2BBCTongHop_KSatvaDanhGiaThietHaiNgapLut.pdf/b72d3dc7-101c-461b-a888-cfc7ba42427c) | Báo cáo nhắc LiDAR 5×5 m bay năm 2012 và dữ liệu mạng thoát nước phục vụ mô hình | Trang PDF 77–78 mô tả LiDAR; trang 175 dẫn báo cáo chuyên đề mạng thoát nước. Đây là bằng chứng dữ liệu từng được sử dụng, chưa phải file raster/vector/mô hình tải được. Cần xin dữ liệu cập nhật và xác minh độ phủ khu pilot |
| [Cổng cảnh báo ngập TP.HCM](https://chongngap.hochiminhcity.gov.vn/baongap/) | Đầu mối quan trắc ngập/mưa/triều | UI tham khảo; chưa xác minh API xuất chuỗi quan trắc có quyền sử dụng. Không dùng tổng mưa thay cho chuỗi mưa theo thời gian |
| [NASA IMERG](https://gpm.nasa.gov/data/imerg), [tài liệu V07](https://gpm.nasa.gov/resources/documents/imerg-v07-technical-documentation) | Mưa nửa giờ trên lưới 0,1° | Bổ sung lịch sử/sự kiện; lưới thô so với đường phố. Chọn đúng Early/Late/Final và đối chiếu trạm |
| [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api) | Khí tượng/mưa theo tọa độ | Dữ liệu tái phân tích hoặc mô hình; phải giữ nguồn, độ phân giải, thời gian và phân biệt mưa dự báo với trận mưa thiết kế |
| [JICA drainage/sewerage report](https://openjicareport.jica.go.jp/618/618/618_123_11551777.html) | Báo cáo quy hoạch/thiết kế thoát nước lịch sử | Có thể đối chiếu sơ đồ và đầu mối dự án; không coi mạng thiết kế cũ là hiện trạng hoàn công |

**Đầu mối cần dữ liệu:** [Trung tâm quản lý hạ tầng kỹ thuật TP.HCM](https://ttqlhtkt.hochiminhcity.gov.vn/thoat-nuoc-do-thi), đơn vị quản lý dữ liệu GIS và hồ sơ khảo sát/hoàn công của dự án. Chỉ cần gói cho lưu vực pilot trước.

Gói cần: cao độ đất/đường và mốc cao độ; cửa thu/hố ga/cống với cao độ đáy, kích thước, kết nối, nhám, cửa xả; trạm bơm và lịch vận hành; chuỗi mưa/mực nước cùng thời gian; sự kiện ngập để kiểm chứng. Cao độ và mực nước phải quy về cùng hệ quy chiếu. Nếu thiếu, chỉ công bố dòng chảy/đánh giá nguy cơ sơ bộ, chưa độ sâu ngập chính xác.

## 4. Hiện trạng, chiều cao và nhiệt

| Nguồn | Dữ liệu hỗ trợ | Giới hạn và quyết định |
|---|---|---|
| [Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1) | Lớp phủ đất 10 m, xác suất phân loại, chuỗi ảnh | Ước lượng hiện trạng rộng hơn khu đất; cần xử lý mây và thời điểm. Không tự phân biệt đủ các loại vật liệu sân thấm |
| [Open Buildings Temporal V1](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1) | Hiện diện/mật độ/chiều cao công trình ước lượng; vùng Đông Nam Á | Có thể bổ sung bối cảnh bóng đổ. Raster ước lượng không phải BIM hay footprint/cao độ khảo sát; cần kiểm tra năm, sai số và cập nhật cục bộ |
| [Landsat Collection 2 Surface Temperature](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature) | Nhiệt độ bề mặt lịch sử; tải sản phẩm Level-2 | Là nhiệt độ bề mặt tại thời điểm ảnh, không phải nhiệt độ không khí/tiện nghi người đi bộ. Dùng nền nhiệt vùng, không suy ra hiệu quả công trình tương lai trực tiếp |
| [SOLWEIG inputs](https://github.com/UMEP-dev/solweig/blob/main/README.md) | Mô hình bóng đổ/Tmrt và chỉ số tiện nghi theo cấu hình | Cần DSM, vị trí, khí tượng; cây và vật liệu bổ sung chất lượng. Repo chưa có gói bối cảnh đã kiểm chứng cho khu pilot |

Ưu tiên bóng đổ hình học trước; tiếp theo tiện nghi nhiệt khi có hình học cây/công trình và khí tượng phù hợp. Nếu chỉ có land-cover và chiều cao ước lượng, báo đó là mô hình sơ bộ.

## 5. Cấp nước, nước thải và điện

| Nguồn/đầu mối | Có thể hỗ trợ | Phần còn phải xin/khảo sát |
|---|---|---|
| [SAWACO: DMA/GIS/mô hình thủy lực](https://sawaco.com.vn/post-detail/cong-ty-co-phan-cap-nuoc-gia-dinh-quyet-tam-keo-giam-ty-le-that-thoat-nuoc-xuong-duoi-10-trong-nam-2026-260508090456) | Bằng chứng đơn vị cấp nước có dữ liệu mạng và lưu lượng/áp lực; không chứng minh dữ liệu Thủ Đức đã có quyền truy cập | Mạng đúng khu pilot, điểm đấu nối, bơm/van, áp lực/lưu lượng và tải theo thời gian; liên hệ đơn vị phục vụ đúng địa chỉ |
| [EVNHCMC GIS phục vụ thiết kế đấu nối](https://www.evn.com.vn/d6/news/EVNHCMC-khao-sat-thiet-ke-cong-trinh-tren-nen-ung-dung-Ban-do-thong-tin-dia-ly-GIS-0-12-25199.aspx) | Có dữ liệu lưới và quy trình xác định phương án đấu nối | Trạm/lộ phục vụ khu đất, thông số, tải đồng thời và giới hạn vận hành. Không suy ra công suất còn dư từ trạm gần nhất |
| [JICA water-environment project](https://www.jica.go.jp/english/information/press/2021/20211228_10e.html) | Đầu mối công trình xử lý và mạng thu gom theo dự án | Phạm vi phục vụ hiện tại, kết nối cống, tải hiện hữu và công suất khả dụng; công suất nhà máy toàn thành phố không phải năng lực còn dư tại khu đất |
| [DOE reference buildings](https://www.energy.gov/cmei/buildings/commercial-reference-buildings) | Mô hình EnergyPlus theo công năng làm nền xây thư viện nhu cầu điện | Mô hình bối cảnh Mỹ; cần điều chỉnh khí hậu, vật liệu, thiết bị và lịch tại Việt Nam; không đại diện lưới điện địa phương |
| [QCVN 07-2023 trên website Bộ Xây dựng](https://moc.gov.vn/Images/editor/files/Quy%20Chu%E1%BA%A9n/QCVN%2007-2023.pdf) | Tài liệu kỹ thuật để nhóm xem xét khi chuẩn hóa tham số/tiêu chí | Không phải dữ liệu đo hoặc chứng minh công suất dư. Cần review chuyên môn và xác minh phiên bản áp dụng trước khi dùng cho đánh giá tuân thủ |

[Cổng dữ liệu TP.HCM](https://data.hochiminhcity.gov.vn/) là đầu mối hỏi bộ dữ liệu có thể chia sẻ; khảo sát này chưa xác minh được dataset/API công khai cung cấp toàn bộ tải mạng điện/nước/cống cho khu pilot.

Nhu cầu có thể ước tính trước; kiểm tra áp lực cấp nước cần mạng và mô hình như [EPANET 2.2](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10113EM.TXT). Dữ liệu mạng thiếu không thể được thay thế bằng việc hỏi người dùng một con số công suất.

## 6. Giá đất và chi phí cải thiện

- Giá đất chính thức: tiếp tục mở rộng/duyệt dữ liệu đã có, xem [assigned-data-availability.md](assigned-data-availability.md). Giá này không phải giá giao dịch.
- Giá thị trường/tác động building lên giá: cần dữ liệu giao dịch hoặc dữ liệu được cấp quyền, vị trí/thời gian/đặc điểm tài sản và mô hình kiểm chứng. Tin đăng không tự trở thành giá giao dịch; chưa đủ dữ liệu để dự báo mức tăng giá do công trình.
- Chi phí gợi ý: dùng báo giá/BOQ hoặc thư viện chi phí theo địa phương, thời điểm, vật liệu và quy mô. Chưa có thư viện được duyệt trong repo; không gán mức tiết kiệm chỉ bằng một tỷ lệ người dùng chọn.

## 7. Người dùng nên nhập gì?

### 7.1 Thông tin thiết kế/vận hành cần thiết

| Nhóm | Đầu vào đề xuất | Tác dụng |
|---|---|---|
| Hình học | Khu đất; footprint; chiều cao, số tầng, tổng diện tích sàn/hướng; phần công trình hiện hữu giữ/phá | Phân biệt xây mới với thay thế; nền bóng đổ và nhu cầu |
| Công năng/quy mô | Diện tích từng công năng; số căn/học sinh/nhân viên/giường bệnh; người tối đa và mức sử dụng dự kiến | Chọn đúng mô hình thay vì chỉ một trường users cho mọi nhu cầu |
| Lịch hoạt động | Giờ mở cửa, ca học/làm, phân bố đến/rời, ngày làm việc | Xác định đồng thời và giờ cao điểm; cùng số người có thể tạo áp lực khác nhau |
| Giao thông trong dự án | Cổng vào/ra, hướng và bề rộng; bãi xe theo loại; đón trả, xe dịch vụ/giao hàng, vị trí chờ | Đánh giá nút thắt do thiết kế thực tế |
| Bề mặt/cây | Polygon hoặc diện tích các vật liệu; cây giữ/chặt/trồng, chiều cao/tán dự kiến | Dòng chảy, bóng mát và nhiệt sau xây |
| Thoát nước thiết kế | Cao độ nền/đường nội bộ, điểm xả; bể giữ nước và quy tắc xả; mái xanh/sân thấm | Đánh giá hướng thoát/giữ nước, không chỉ dung tích danh nghĩa |
| Điện/nước trong công trình | HVAC, thiết bị lớn/EV charging, lịch dùng; thiết bị nước, tưới, tái sử dụng và tải đặc thù | Tăng chất lượng nhu cầu so với hệ số/người |

Đầu vào chuyên sâu chỉ mở khi module tương ứng chạy. Có thể nhập qua bản vẽ/BIM rồi yêu cầu xác nhận thông tin trích xuất; chưa cam kết parser hiện có. Phần chưa thiết kế có thể dùng lựa chọn mẫu có nhãn và phân tích độ nhạy.

### 7.2 Thông tin tùy chọn nâng độ chính xác

- Tỷ lệ phương tiện và phân bố nguồn/đích có khảo sát hoặc kế hoạch vận hành có căn cứ; mặc định hệ thống chọn từ thư viện đã hiệu chỉnh, không buộc người dùng đoán.
- Hồ sơ địa hình/địa chất, thử thấm và hồ sơ đấu nối được xác nhận; lưu đơn vị, hệ cao độ, ngày đo và nguồn.
- Chi phí/báo giá, ngân sách và phần thiết kế không được thay đổi để lọc gợi ý khả thi.

### 7.3 Những dữ liệu hệ thống/nhóm phải chuẩn bị

Mưa/triều; hiện trạng khu vực; mạng và lưu lượng giao thông nền/pha đèn; tham số theo công năng/vật liệu; mạng cống và cấp nước/điện; dữ liệu kiểm chứng. Không chuyển gánh nặng này thành form bắt người dùng nhập công suất dư hoặc hệ số thủy lực.

Chọn ngày/khung giờ/kịch bản thời tiết có sẵn trong demo. So sánh trước/sau phải dùng cùng điều kiện ngoại cảnh; dự báo mưa vài ngày tới và trận mưa thiết kế phục vụ đánh giá dài hạn là hai mục đích khác nhau.

## 8. Kế hoạch kiểm chứng nguồn và demo

1. Chốt khu pilot và các chỉ số cần công bố; chọn vùng mạng/lưu vực theo ảnh hưởng, không chỉ một buffer tùy ý.
2. Probe OSM/TomTom, raster chiều cao/bề mặt/địa hình; ghi key/điều kiện truy cập, bbox, năm, tỷ lệ thiếu và giấy phép trong catalog. Không lưu key vào Git.
3. Xin gói LiDAR/cống/mưa/triều và dữ liệu đấu nối từ đúng đơn vị; chưa có quyền thì giữ trạng thái pending.
4. Khảo sát lưu lượng/hướng rẽ/pha đèn và công trình tương đồng, ưu tiên đúng giờ cao điểm; kiểm tra độ đại diện và sai số.
5. Chuẩn hóa building plan; tự chọn tham số có nguồn. Tách quan trắc, ước lượng và mẫu tham khảo trong dữ liệu/kết quả.
6. Hiệu chỉnh baseline rồi kiểm chứng bằng dữ liệu khác khi có thể; sau đó chạy trước/sau với cùng điều kiện, thử độ nhạy/seed cho mô hình phù hợp.
7. Chỉ hiển thị những đại lượng đủ đầu vào: nhu cầu vẫn có thể tính khi năng lực đáp ứng chưa đủ dữ liệu. Báo unavailable thay vì mặc định hạ tầng an toàn.

**Ưu tiên:** tự lấy hiện trạng + mưa, chuẩn hóa công năng/lịch/cổng và vật liệu; triển khai traffic pilot có số đo. Ngập thủy lực và kiểm tra năng lực mạng chỉ nâng cấp sau khi nhận và kiểm chứng dữ liệu nền.
