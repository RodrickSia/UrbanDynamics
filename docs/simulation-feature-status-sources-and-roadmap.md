# Báo cáo simulation hiện tại: feature, nguồn, công thức và kế hoạch

**Ngày kiểm kê:** 09/10/2026. **Code đang đọc:** Git HEAD `7c646f7`, model `integrated-building-1.1`, thư viện `thu-duc-demo-library-1.1`.

**Cập nhật 11/10/2026:** Nội dung kiểm kê bên dưới giữ mốc 09/10. Backend local hiện đã có [tích hợp nền snapshot](simulation-background-integration.md), [nhận building từ map](simulation-map-context-handoff.md), và [chuẩn hóa hệ số/độ nhạy](simulation-demand-coefficients.md) ở model 1.4/library 1.3. Ưu tiên chuẩn hóa hệ số đã có catalog, nguồn số với phạm vi và OAT; hiệu chỉnh địa phương vẫn chưa hoàn tất. Xem các tài liệu mới để biết trạng thái hiện tại.

**Phạm vi:** demo `/simulation/integrated`, các lớp ETL mà nó nạp làm bối cảnh và kế hoạch nâng cấp. Nội dung dựa trên code và file local hiện có; không phải một đợt chạy lại test/solver hoặc fetch dữ liệu mới. Các số liệu trong báo cáo cũ có thể thuộc snapshot khác.

## 1. Tóm tắt

Luồng hiện có:

**Building plan → hiện trạng/kịch bản nền → GIS + nhu cầu theo giờ + bóng đổ + SUMO + SWMM → so trước/sau → đánh giá → yêu cầu gợi ý → chạy lại các phương án → lưu/xuất.**

- Đã có **22 chỉ số so sánh** thuộc các nhóm xây dựng, xanh, nước mưa, giao thông, điện/nước/nước thải, cư dân/dịch vụ, bóng đổ và đường.
- SUMO và SWMM là engine thật. Đầu vào mạng đường, OD, đèn, cống, tải nền và công suất hạ tầng của demo vẫn tổng hợp. Kết quả solver được tính từ kịch bản, không phải số đầu ra điền sẵn.
- GIS/hình học lấy từ building plan người dùng. Preset chung cư là thiết kế minh họa, không phải công trình được khảo sát tại địa chỉ đó.
- Ngập lịch sử, ảnh ngập, mưa và giá đất có dữ liệu nguồn ngoài đã lưu local. Những dữ liệu này chưa thay thế nền tổng hợp của các solver.
- Chưa có dự báo độ sâu ngập bề mặt 2D, nhiệt độ/tiện nghi nhiệt, áp lực nước, power flow, giá thị trường sau xây hoặc AI giải thích.

**Nhãn trong báo cáo:** `thiết kế` = thông tin người dùng/preset; `nguồn ngoài` = dữ liệu thật được lấy từ nguồn, có thể là quan sát hoặc sản phẩm mô hình; `ước lượng` = tính toán/suy luận; `tổng hợp` = giả lập có quy tắc. Nguồn ngoài không mặc định là phép đo thực địa.

## 2. Feature và nguồn hiện tại

| Nhóm | Đã tính/hiển thị | Nguồn đang dùng | Có giả lập không? | Giới hạn |
|---|---|---|---|---|
| Xây dựng | Mật độ, FAR, diện tích mái/sàn | Polygon, tầng, chiều cao, sàn từ thiết kế | Preset là minh họa; baseline mặc định giả lập | Chưa tự lấy công trình hiện hữu từ OSM/Open Buildings |
| Xanh/bề mặt | Đất xanh %, tán cây hợp nhất m², không thấm % | Diện tích thiết kế; vị trí/bán kính tán cây | Cây/diện tích preset không khảo sát | Đất xanh khác tán cây; chưa có bản đồ vật liệu tự động |
| Mưa–runoff screening | Nước phát sinh, khả năng giữ, nước chưa giữ | Hệ số trong library + mưa kịch bản + dung tích bể | Hệ số/mưa mặc định tổng hợp | Không phải độ sâu ngập; không tính quá trình xả trong trận mưa |
| Thoát nước SWMM | Tràn nút, peak runoff, độ sâu trong nút, thời gian tràn | SWMM + mạng cống/bể tự sinh | Cống/cao độ/đất/mưa tổng hợp | Chỉ mô hình mạng nhỏ; không triều, không flood map 2D |
| Giao thông | Trips; delay; queue; xe chưa hoàn thành/chưa xuất phát | Lịch/số người thiết kế → library → SUMO | Mạng/OD/đèn/hành vi/background tổng hợp | Chưa dùng mạng OSM hoặc counts từ video; chỉ giờ cao điểm được chọn |
| Nước cấp | m³/ngày, peak m³/giờ, profile giờ | Số người/công năng + suất dùng + tưới + tái sử dụng | Hệ số và spare capacity tổng hợp | Chưa mô phỏng áp lực hoặc mạng cấp nước |
| Nước thải | m³/ngày, peak giờ | Nước trong nhà × return fraction − tái sử dụng | Return fraction tổng hợp | Chưa nối vào mô hình thủy lực cống nước thải |
| Điện | kWh/ngày, kW đỉnh, profile giờ, EV/tái sử dụng | Sàn/công năng/lịch + hệ số + thiết bị thiết kế | Hệ số và spare capacity tổng hợp | Chưa EnergyPlus, feeder/transformer hoặc power flow |
| Dân cư/nhà ở | Cư dân thường trú, số căn | Người dùng nhập/preset | Preset tổng hợp | Số căn chưa tự suy ra số cư dân; khách không tính là cư dân |
| Dịch vụ | Công suất bổ sung, nhu cầu chưa đáp ứng, thời gian đi bộ mẫu | Công suất thiết kế + 2 cơ sở giả + hệ số nhu cầu | Nền dân số/cơ sở/capacity đều tổng hợp | Chưa trường/bệnh viện thật; chưa routing citywide hoặc phản hồi travel time SUMO |
| Bóng đổ | Bóng mát trong khu đất, bóng đổ ngoài khu đất, bản đồ 9/12/15h | Footprint/height/cây + vị trí Mặt Trời | Hình học ước lượng từ thiết kế; không đo nhiệt | Mặt đất phẳng, cây là khối kín, chưa công trình lân cận |
| Đường/kết nối | Chiều dài/density kịch bản | Graph 600 m + đường thêm/bớt nhập tay | Tổng hợp | Thêm/bớt chiều dài chưa thay topology SUMO/routing |
| Đánh giá/gợi ý | Tốt/xấu/tăng nhu cầu/lợi ích, targets, ba mẫu cải thiện, Pareto | Chỉ số đã tính + goals/cost library | Mục tiêu và đơn giá tổng hợp | Chưa tối ưu toàn cục hoặc phê duyệt quy hoạch |
| Lớp ngập/giá đất | Snapshot bối cảnh quanh khu đất | GeoJSON local hoặc PostGIS | Không tạo giả dữ liệu nguồn | Chưa là input hiệu chỉnh cống/traffic hoặc dự báo giá sau xây |

## 3. Dữ liệu nguồn ngoài đang có

Số lượng dưới đây là toàn file local, **không phải số feature trong 1 km quanh mỗi khu đất**. Context lọc phạm vi 1 km và giữ tối đa 100 feature/lớp trong snapshot; khi cấu hình warehouse, nó truy vấn PostGIS thay file.

| Lớp | Snapshot local | Nguồn | Được dùng như thế nào? |
|---|---|---|---|
| `flood_history` | **425 quan sát**, ingest 07/10/2026 | [IRD/DataSuds HCMC flood dataset](https://dataverse.ird.fr/dataset.xhtml?persistentId=doi:10.23708/8Y16HU), CC BY-NC 4.0 | Nạp bối cảnh và vẽ điểm lịch sử trên map integrated. Không tự suy mạng cống/depth tương lai |
| `flood_risk` | **425 feature vùng tìm kiếm**, snapshot 07/10 | Ngập lịch sử + [Open-Meteo forecast](https://api.open-meteo.com/v1/forecast) và archive | Cảnh báo theo ngưỡng mưa P90; nạp context, chưa render trực tiếp trong map integrated |
| `flood_satellite` | **11.055 feature**, metadata 82 item raster, ingest 07/10 | [GFM STAC/EODC](https://stac.eodc.eu/api/v1/collections/GFM/items) | Raster và exclusion mask đã xử lý theo metadata; nạp context. Không dự báo sau xây |
| `land_price` | **1.848 feature** từ **9.502 hàng nguồn**, 7.654 pending theo metadata cấp lớp | [PDF bảng giá đất 2026](https://xdcs.cdnchinhphu.vn/446259493575335936/2026/1/12/87-2025-nq-bang-gia-dat-nam-2026-phat-hanh-signed-1768193916980186481882.pdf) + OSM | Giá tham chiếu chính thức ghép geometry, nạp context; chưa heatmap giá thị trường/dự báo uplift |
| `rainwater` | **117 điểm lấy mẫu**, 98 source cells khác nhau theo metadata | Open-Meteo forecast/archive | Có ETL mưa vùng; integrated chưa dùng lớp này làm trận mưa SWMM |

**Những điểm phải đọc cùng số lượng:**

- Mưa/risk có `expires_at = 2026-10-07T08:48:34.840733+00:00`: **đã hết hạn vào ngày kiểm kê 09/10**. Không báo đây là forecast hiện thời.
- Integrated chỉ lưu timestamp/hash của `data/inputs/rainwater_forecast.json` làm bối cảnh, với trạng thái `cached_not_used_for_design_event`. Mưa simulation là do người dùng chọn hoặc từ library.
- 117 điểm mưa là điểm lấy mẫu từ mô hình, không phải 117 trạm đo độc lập.
- GFM đã có flood features trong snapshot mở rộng; thông tin cũ “0 pixel ngập” thuộc snapshot khác. Excluded/no-data không được coi là khô. Số feature cũng không phải số sự kiện ngập độc lập.
- Giá đất có nhiều hàng ghép tự động chưa review. Metadata ghép không gian lồng bên trong còn ghi 1.847 match, khác tổng lớp 1.848 do lớp công bố có phần bổ sung. Không gọi toàn bộ là đã duyệt, không coi đường gần nhất là giá áp dụng cho thửa đất.
- Map integrated hiện vẽ site, building, graph SUMO, điểm dịch vụ, nút SWMM, lịch sử ngập và bóng đổ. Risk/satellite/land price có trong context nhưng chưa có overlay tương ứng trên trang này.

## 4. Công thức đang dùng

### 4.1 Hình học, xanh và bề mặt

Ký hiệu: `A` diện tích khu đất; `R` tổng diện tích footprint; `P` sân cứng; `M` sân thấm; `G` đất xanh; `F` tổng diện tích sàn. Diện tích polygon WGS84 được tính bằng hàm diện tích của hệ thống; overlay dùng hệ tọa độ mét cục bộ.

```text
R + P + M + G = A
F_i = sàn người dùng khai báo; nếu thiếu: footprint_i × số tầng_i
Mật độ xây dựng (%) = 100 × R / A
FAR = ΣF_i / A
Đất xanh (%) = 100 × G / A
Bề mặt không thấm (%) = 100 × (R + P) / A
Tán cây (m²) = diện tích union các vòng tròn tán, cắt trong khu đất
```

Tán cây chồng nhau chỉ tính một lần. Tán cây có thể chồng trên sân, không cộng vào tổng diện tích bề mặt. `impervious_percent` không tính phần không thấm 30% của sân thấm trong SWMM: đây là hai cách biểu diễn khác nhau, phải giữ tên/ý nghĩa riêng.

### 4.2 Runoff screening bằng hệ số

```text
V_gross = H_mm / 1000 × (0,90R + 0,85P + 0,35M + 0,20G)
S_empty = storage_m3 − storage_initial_m3
V_retained_potential = min(V_gross, S_empty)
V_unretained = max(0, V_gross − S_empty)
```

Đơn vị m³/trận mưa. Hệ số là library synthetic, chưa được hiệu chỉnh địa phương. Screening độc lập với SWMM; không gọi `V_unretained` là lượng ngập mặt đường hay lượng SWMM tràn nút.

### 4.3 SWMM: mô hình thủy văn/thủy lực

Engine dùng Horton infiltration và Dynamic Wave. Không có một công thức tuyến tính thay toàn bộ solver. Các quan hệ nền gồm:

```text
Horton: f(t) = f_min + (f_max − f_min) × exp(−k t)
Manning: Q = (1/n) × A_flow × R_hydraulic^(2/3) × sqrt(S_energy)
Orifice: Q ≈ C_d × A_orifice × sqrt(2g × Δh)
Cân bằng thể tích: dV/dt = Qin − Qout − losses
```

Đây là dạng quan hệ nền để giải thích engine; SWMM áp dụng xử lý trạng thái, routing và điều kiện dòng chảy đầy đủ. **Code không tính tràn chỉ bằng Manning rồi trừ mưa.**

Đầu vào hiện tại:

- Mưa đều một giờ, sau đó 2 giờ không mưa; tổng run 3 giờ. Mặc định base 60 mm, low 42 mm, high 78 mm; người dùng có thể override tổng mưa.
- Mái/sân cứng 100% không thấm, sân thấm 30%, xanh 0%; slope mặt 1%, width dòng chảy `sqrt(diện tích m²)`.
- Horton `f_max=60`, `f_min=6` mm/giờ, decay 4/giờ; các tham số đều synthetic.
- Một nút `J1`, một outfall `O1`, cống dài 200 m, diameter 0,30 m, Manning n=0,013; invert 10 m và 8 m theo mốc giả định. Outfall **FREE**, không có triều/bơm.
- Có bể thì thêm `S1`, area `max(10, storage/2)`, max depth `storage/area`, nối orifice tới J1; discharge coefficient 0,65, đường kính xả từ thiết kế.

Đọc kết quả mỗi 5 phút:

```text
Tràn nút m³ ≈ Σ_nút Σ_mẫu q_flooding(m³/s) × 300 s
Thời gian tràn phút ≈ số mẫu q_flooding > 10⁻⁸ × 5 phút
Độ sâu nút tối đa = max(depth trong nút/bể ở các mẫu)
Peak runoff = max(Σ runoff của các subcatchments tại mỗi mẫu)
```

Tích phân lấy mẫu là xấp xỉ. `peak_depth_m` là độ sâu **trong nút/bể**, không phải flood depth bề mặt. Continuity errors phải có và từng trị tuyệt đối ≤5% để `balance_passed`.

### 4.4 Trips và giao thông SUMO

Với building `i`: `N_i` cư dân, `S_i` nhân viên, `V_i` khách/ngày, `U_i` daily users. `p_r(h)` lịch cư dân; `p_i(h)` lịch hoạt động, mỗi lịch chuẩn hóa tổng bằng 1.

```text
T_person(h) = load_factor × Σ_i[
  N_i × resident_trips_day_i × p_r(h)
  + (2S_i + V_i × visitor_trips_day_i + U_i × user_trips_day_i) × p_i(h)
]
Cars(h) = T_person(h) × 0,25 / 1,6
Motorcycles(h) = T_person(h) × 0,55 / 1,2
Giờ chọn = argmax_h [Cars(h) + Motorcycles(h)]
Xe kế hoạch = background + round(Cars(giờ chọn)) + round(Motorcycles(giờ chọn))
```

20% person trips còn lại không được đưa vào hai loại xe trên; chưa mô phỏng riêng walking/transit. Profile được làm trơn theo `stagger_hours` bằng trung bình trượt vòng 24 giờ, bảo toàn tổng ngày. `load_factor` low/base/high = 0,7/1/1,3, áp lên trips.

SUMO hiện dùng:

- 4 nút, 3 đoạn hai chiều = 6 directed edges; đường chính 2 làn, nhánh cổng theo `gate_lanes`.
- Tốc độ đặt 13,89 m/s đường chính, 8,33 m/s nhánh cổng; đèn do netconvert sinh.
- Background 280/400/520 xe/giờ low/base/high, **toàn bộ là car**; đây là lượng nền toàn graph, không phải số đo từng đường.
- Xe background chia hai tuyến xuyên vùng; xe building chia luân phiên vào/ra cổng, chưa OD địa phương.
- Gate stop mặc định 8 giây trên lane 0; tăng số làn cổng chưa tăng số điểm phục vụ song song.
- Sublane resolution 0,8 m; chạy 3.600 giây phát xe + 600 giây chờ hoàn tất; queue output lấy mẫu 60 giây.

```text
Delay trung bình = Σ timeLoss của chuyến hoàn thành / số chuyến hoàn thành
Queue tối đa = max(queueing_length của các làn ở các mẫu 60 giây)
Xe chưa hoàn thành = số đã chèn vào mạng − số hoàn thành
Xe chưa xuất phát = max(0, xe kế hoạch − số đã chèn)
```

Nếu không có chuyến hoàn thành, code dùng mẫu số tối thiểu 1, nên giá trị 0 không được hiểu là không ùn tắc. Kiểm tra riêng hai nhóm incomplete. Delay không bao gồm chuyến chưa hoàn thành; queue lấy mẫu có thể bỏ lỡ đỉnh.

Hiện mỗi design tự chọn giờ peak của nó, chưa khóa một giờ đồng hồ chung cho toàn bộ phương án. Đây là điểm cần nâng cấp khi so traffic cùng khung giờ hoặc chạy cả ngày.

### 4.5 Nước cấp, tái sử dụng và nước thải

`a_w = 0,75` khi bật thiết bị tiết kiệm, nếu không bằng 1. Các suất `q` lấy theo công năng trong library.

```text
W_indoor(h) = a_w / 1000 × Σ_i[
  N_i × q_resident_i × p_r(h)
  + (S_i × q_staff_i + V_i × q_visitor_i + U_i × q_user_i) × p_i(h)
]
Tưới = G × 2 / 1000 m³/ngày, cộng ở 05h
Waste_before_reuse(h) = 0,8 × W_indoor(h)
Reuse = min(reuse_m3_day thiết kế, ΣWaste_before_reuse, ΣWater_before_reuse)
Freshwater_day = ΣWater_before_reuse − Reuse
Wastewater_day = ΣWaste_before_reuse − Reuse
Peak giờ = max(profile giờ sau phân bổ giảm do reuse)
```

Tái sử dụng được giảm theo tỷ lệ trên profile nước/nước thải. Nước tưới không đi vào sanitary wastewater. Reuse là giả định nguồn nước thải đã xử lý hằng ngày; chưa mô phỏng bể xử lý/lịch trữ hoặc lấy trực tiếp nước mưa SWMM để trừ nước cấp.

### 4.6 Điện

`e_i` là kWh/m²/ngày theo công năng; `a_e = 0,8` nếu bật thiết bị tiết kiệm, nếu không bằng 1.

```text
P_building(h) = Σ_i F_i × e_i × p_i(h) × a_e
P_EV(h) = số charger × 7 kW, trong 4 giờ liên tục kể từ giờ bắt đầu
P_treatment(05h) = Reuse × 0,6 kWh/m³ / 1 giờ
P_total(h) = P_building(h) + P_EV(h) + P_treatment(h)
Energy_day = Σ_h P_total(h) × 1 giờ
Power_peak = max_h P_total(h)
```

Profile đã thể hiện đồng thời; không thêm diversity factor lần nữa. Chưa kiểm tra năng lực transformer, điện áp hoặc công suất đấu nối. Mô hình tải theo sàn/lịch chưa phải mô hình HVAC nhiệt.

### 4.7 Cư dân, nhà ở, dịch vụ và đường

```text
Residents = Σ residents_i
Housing units = Σ units_i
Service added capacity = Σ service_capacity_i
Service demand = 1.200 + 0,25 × Residents
Service available = 1.500 + Service added capacity
Unserved = max(0, Service demand − Service available)
Walking time = min(network_distance của 2 điểm synthetic) / 80 m/phút
Road length = 600 + added_road_m − removed_road_m
Road density (km/km²) = road_length_m × 1.000 / area(site buffer 1 km)_m²
```

Hai service points có khoảng cách graph 250 và 300 m, nên thời gian gần nhất mặc định **3,125 phút**. Chưa có phân loại nhu cầu học/y tế theo tuổi hoặc capacity từng cơ sở thật; không gọi chỉ số unserved là số học sinh/bệnh nhân thiếu chỗ thực tế.

Đường thêm/bớt chỉ là screening chiều dài; connectivity và graph solver vẫn cố định.

### 4.8 Bóng đổ

Code xấp xỉ vị trí Mặt Trời theo ngày, tọa độ và giờ UTC+7. Với vector Mặt Trời `(east,north,up)` và chiều cao `H`:

```text
dx = −H × east / up
dy = −H × north / up
Độ dài bóng tương đương trên đất phẳng = H / tan(góc cao Mặt Trời)
Bóng = union footprint quét theo (dx,dy), bỏ mái công trình
Shade%(h) = 100 × area(bóng ∩ phần ngoài nhà trong site) / area(phần ngoài nhà)
Mean shade% = trung bình 10 mẫu giờ 08–17
Neighbour shadow = trung bình area(bóng ngoài site) tại các mẫu giờ
```

Bóng bị cắt theo vùng buffer 300 m quanh khu đất. Cây mô hình hóa bằng khối tán kín có chiều cao. Chưa có DSM/terrain/công trình bên ngoài; bóng ngoài site không tự đồng nghĩa tác động xấu lên nhà hàng xóm, vì chưa biết receiver/chức năng đó.

### 4.9 Risk layer theo mưa: chức năng riêng

ETL risk, cũng được dùng cho kịch bản `POST /api/v1/scenarios/rain`, có logic:

```text
Rain_3h = max(tổng mưa 3 giờ liên tục trong 24h forecast)
Threshold = P90 của các cửa sổ lịch sử cùng tháng Việt Nam có mưa ≥1 mm
Nếu đủ ≥30 cửa sổ và Rain_3h ≥ Threshold: rain_alert_near_historical_flood
Nếu chưa đủ history: insufficient_history
Vùng hiển thị = buffer 250 m quanh điểm từng ngập
```

Trạm lấy mẫu gần điểm ngập nhất được chọn. Đây là heuristic mưa gần lịch sử ngập, chưa calibrated probability; buffer không phải flood extent. Building plan chưa tác động tới lớp này. Không trộn nó với simulation SWMM.

## 5. Các hệ số và hiện trạng giả lập quan trọng

### 5.1 Library nhu cầu theo công năng

**Toàn bộ số dưới đây là synthetic trong code, không được gắn nhãn tiêu chuẩn Việt Nam.**

| Công năng | Nước cư dân L/người/ngày | Nhân viên L/ngày | Khách L/lượt | Daily user L/lượt | Điện kWh/m²/ngày | Trips cư dân/ngày | Trips khách/lượt | Trips daily user/lượt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chung cư | 120 | 40 | 15 | 40 | 0,11 | 2 | 2 | 2 |
| Trường | 100 | 40 | 25 | 25 | 0,07 | 2 | 2 | 2 |
| Văn phòng | 100 | 45 | 15 | 45 | 0,14 | 2 | 2 | 2 |
| Bệnh viện | 180 | 60 | 40 | 180 | 0,22 | 1 | 2 | 1 |
| Khác | 120 | 40 | 20 | 40 | 0,10 | 2 | 2 | 2 |

Nhân viên dùng 2 trips/ngày. Profile mặc định của residential/hospital là mẫu residential; các công năng còn lại mẫu day. Đây là lựa chọn tổng hợp, chưa lịch vận hành địa phương.

### 5.2 Baseline và ngưỡng

- Không truyền baseline: khu đất trống với **15% sân cứng, 15% sân thấm, 70% xanh**, không building/cư dân/cây.
- Có baseline người dùng: dùng design và mô tả nguồn họ cung cấp; hệ thống chưa xác minh mô tả đó là khảo sát thực.
- Spare capacity: nước 60 m³/ngày; nước thải 45 m³/ngày; điện 200 kW. Không phải dữ liệu SAWACO/EVNHCMC.
- Targets: xanh ≥20%; impervious ≤70%; runoff screening tăng ≤10%; overflow SWMM ≤110% baseline; không có xe chưa xuất phát/chưa hoàn thành.
- Target điện: `max_h(P_after(h) − P_before(h)) ≤200 kW`, so cùng giờ, không lấy hiệu hai đỉnh ngày.
- Targets/chi phí là mục tiêu minh họa dự án, không kết luận tuân thủ quy hoạch/quy chuẩn.

## 6. Đánh giá và gợi ý hiện tại

### 6.1 So sánh

```text
Delta = after − before
Không đổi nếu |Delta| < max(10⁻⁵, 0,001 × |before|)
```

Nhóm giảm tốt: runoff, tràn nút, delay, queue, incomplete, service unserved. Nhóm tăng tốt: xanh, tán cây, bóng mát. Cư dân/số căn/công suất phục vụ là lợi ích tăng thêm. Điện/nước tăng được gọi tăng nhu cầu, chưa mặc định công trình xấu. Mật độ/FAR/bóng ngoài site/đường là thay đổi bối cảnh.

Kết luận chung `mixed/benefits/pressures/unchanged` dựa trên sự có mặt của lợi ích và áp lực; **chưa có điểm trọng số tổng hợp hoặc kết luận phê duyệt**.

### 6.2 Tạo phương án sau khi dự tính

Ba template: landscape/drainage; operations/utilities; combined.

- Chuyển sân cứng sang xanh và thấm, mỗi phần 50% diện tích chuyển.
- Thêm bể giữ nước với cửa xả thiết kế.
- Bật hệ số thiết bị tiết kiệm nước/điện; giãn lịch tối đa 3 giờ; chuyển sạc EV sang 01h.
- Giữ nguyên danh sách buildings: footprint, sàn/tầng/height, quy mô cư dân/số căn/công suất phục vụ.
- Chạy lại GIS/demand/shadow/SUMO/SWMM, không viết sẵn số cải thiện.

```text
Cost ≈ 150.000 × xanh thêm m² + 200.000 × sân thấm thêm m²
     + 3.000.000 × bể thêm m³
     + 600.000 × tổng người khi thêm thiết bị nước tiết kiệm
     + 150.000 × tổng sàn m² khi thêm thiết bị điện tiết kiệm
     + 5.000.000 nếu thêm can thiệp lịch
```

Đơn giá synthetic, không báo giá thi công. Pareto chỉ xét các ứng viên đã sinh và chi phí, chưa tìm tối ưu toàn bộ thiết kế. Kết quả có thể `partial` hoặc `no_feasible_candidate`; solver invalid không được xếp là đạt mục tiêu.

## 7. Trường có trên schema nhưng chưa mô phỏng đầy đủ

| Trường/chức năng | Tình trạng |
|---|---|
| `parking_spaces` | Được lưu/input nhưng chưa sử dụng để giới hạn xe, mô hình bãi đỗ hoặc parking search |
| `added_road_m` / `removed_road_m` | Thay đổi chiều dài screening, chưa sửa SUMO network/topology |
| `gate_lanes` | Thay làn approach; gate stop vẫn lane 0, chưa service stations song song |
| Tree `stage` | Được lưu; bóng sử dụng height/radius khai báo, chưa growth model theo tuổi |
| Forecast/risk/giá đất | Có context nhưng chưa thay hệ số/dữ liệu nền của các engine |
| Service `network_distance_m` | Khoảng cách tổng hợp đặt sẵn, chưa shortest path từ OSM thật |

## 8. Feature chưa có và kế hoạch thêm

Đây là đề xuất triển khai, chưa phải tính năng đã tích hợp. Ưu tiên cải thiện nền và kiểm chứng trước khi tăng số feature.

| Ưu tiên | Nâng cấp/feature | Dữ liệu/thuật toán | Kết quả cần đạt |
|---|---|---|---|
| P0 | Tự lấy hiện trạng theo vị trí | OSM, Open Buildings, Dynamic World, WorldPop | Công trình/bề mặt/dân số có nguồn; vùng thiếu có nhãn, không tự nhận là quan sát |
| P0 | Catalog chất lượng và freshness | Snapshot/version/coverage/expiry/provenance | Cảnh báo mưa hết hạn, dữ liệu chưa review, synthetic và uncertainty rõ ràng |
| P0 | Map overlay chung | Risk/satellite/giá đất, popup nguồn, thời gian và phạm vi | Lớp context xem được; giá đất không bị hiểu là transaction hoặc parcel valuation |
| P1 | Traffic trên mạng thật và OD có căn cứ | OSM → trips theo dân số/công năng → Gravity/Radiation → SUMO; routeSampler khi có counts | Thay graph 4 nút và background cố định; boundary flows; so cùng giờ/nhiều giờ |
| P1 | Video counts và calibration | Video liên tục hợp lệ → detection/tracking; [UIT-ADrone](https://uit-together.github.io/datasets/UIT-ADrone/) để thử phương pháp | Counts theo hướng/loại; validation riêng. Dataset nghiên cứu chưa phải lưu lượng 2026 tại chung cư |
| P1 | Bãi xe/đón trả/cổng | Parking capacity, occupancy, dwell time; SUMO facilities/logic vận hành | `parking_spaces` có tác động; mô phỏng spillback và phục vụ cổng phù hợp |
| P1 | Mạng cống tổng hợp theo địa điểm | [SWMManywhere](https://github.com/ImperialCollegeLondon/SWMManywhere), DTM, đường/buildings; ensemble và review outfall | Mạng synthetic phụ thuộc lưu vực; overflow nhạy theo cống/biên có khoảng thử |
| P1 | Mưa theo thời gian và biên triều | Mưa sự kiện/hyetograph; mực nước local nếu có, scenario nếu thiếu | Không chỉ mưa đều 1 giờ; triều/backwater có nguồn/nhãn, không dùng thẳng Vũng Tàu thay cửa xả |
| P1 | Dịch vụ và cư dân thực hơn | WorldPop age-sex, cơ sở thật, routing OSM; capacity từ báo cáo hoặc scenario | Tiếp cận trường/y tế theo nhóm dân số; chưa có capacity thì không báo chỗ trống thực |
| P1 | Nhu cầu điện/nước theo archetype | Thư viện hệ số có nguồn, thiết bị/lịch/occupancy; sensitivity | Giảm phụ thuộc synthetic rates và tách demand khỏi khả năng mạng |
| P1 | Nền bóng đổ khu vực | Chiều cao công trình lân cận, cây/DSM khi có | Bóng đổ lên đối tượng thật, kiểm tra hình học; còn sai số height phải báo |
| P2 | Tiện nghi nhiệt ngoài trời | [SOLWEIG](https://umep-docs.readthedocs.io/en/latest/OtherManuals/SOLWEIG.html), DSM/cây/khí tượng/vật liệu | Tmrt/chỉ số phù hợp; không biến LST/Tmrt thành air temperature |
| P2 | Flood map độ sâu 2D | Mô hình 2D/coupling + địa hình/cống/mưa/biên đủ tốt | Depth/extent/duration bề mặt được kiểm chứng; terrain 30 m chưa đủ đánh giá chính xác từng building |
| P2 | Áp lực cấp nước | EPANET/WNTR + pipe/pump/tank/demand; benchmark synthetic nếu thiếu mạng local | Pressure/flow được tính cho mạng xác định; không gọi mạng mẫu là SAWACO |
| P2 | Điện và năng lực mạng | EnergyPlus/URBANopt cho loads; power flow với feeder/transformer; SimBench làm benchmark | Tải giờ/overload/voltage khi đủ input, phân biệt kWh với kW |
| P2 | Thủy lực nước thải | Sanitary/combined network + tải nền + SWMM | Nước thải building nối vào mạng đúng loại, không chỉ return fraction |
| P2 | Tiếng ồn/phát thải/carbon/rác | Traffic emissions, dispersion/noise, vật liệu/BOQ/LCA và suất rác có nguồn | Chỉ thêm khi có phương pháp và dữ liệu, chưa đưa vào điểm demo hiện tại |
| P2 | Giá thị trường/tác động lên giá | Transactions/đặc điểm tài sản/thời gian, mô hình kiểm chứng | Chưa đủ dữ liệu; listing không coi là giá giao dịch, bảng giá không tự đổi do building |
| Hoãn | AI giải thích | Adapter model đọc output có bằng chứng | Theo yêu cầu trước: chưa làm ở stage này; AI không thay solver hoặc tự sinh số tác động |

### Lộ trình thực tế đề xuất

1. Chốt pilot chung cư và AOI mạng/lưu vực; nạp baseline có nguồn, inventory/expiry và overlay.
2. Nâng traffic OSM/OD/parking, cùng thu dữ liệu calibration nếu có video; giữ phương án synthetic khi chưa có nguồn.
3. Thử SWMManywhere, kiểm tra topo/outfall và chạy nhiều cấu hình; nâng mưa/biên rồi đối chiếu ngập lịch sử.
4. Nâng nhu cầu/dịch vụ, bối cảnh bóng đổ và sensitivity đa feature. Gợi ý phải giữ quy mô và chạy lại engine.
5. Chỉ thêm nhiệt/2D/EPANET/power flow khi chuẩn bị được input và tiêu chí kiểm chứng. Nguồn mới được khảo sát không mặc định đã tích hợp.

Chi tiết nguồn thay thế, thuật toán, giấy phép và giới hạn: [khảo sát bù dữ liệu thiếu](missing-simulation-data-and-estimation-options.md).

## 9. Ví dụ kiểm tra công thức (không phải run solver mới)

Ví dụ riêng để giải thích: A=12.000 m²; mái 2.000; sân cứng 3.000; sân thấm 3.000; xanh 4.000; chung cư 12 tầng, sàn 24.000; 200 căn/600 cư dân/12 nhân viên/80 khách; không daily users, không reuse, không tiết kiệm, 12 chargers; mưa base 60 mm, không bể.

| Chỉ số | Kết quả theo công thức |
|---|---:|
| Mật độ | 16,67% |
| FAR | 2,00 |
| Xanh | 33,33% |
| Không thấm screening | 41,67% |
| Gross/unretained runoff | 372 m³/trận |
| Nước trong nhà | 73,68 m³/ngày |
| Tưới | 8 m³/ngày |
| Nước cấp tổng | 81,68 m³/ngày |
| Nước thải | 58,944 m³/ngày |
| Person trips base | 1.384 trips/ngày |
| Car trips ước lượng | 216,25 trips/ngày |
| Motorcycle trips ước lượng | 634,33 trips/ngày |
| Điện building | 2.640 kWh/ngày |
| Điện EV | 336 kWh/ngày |
| Điện tổng | 2.976 kWh/ngày |

Không suy delay/queue/tràn nút SWMM hoặc kW peak chỉ từ bảng này: phải có profile và chạy engine tương ứng. Đây không phải kết quả preset UI (polygon/diện tích preset khác).

## 10. Lưu trữ, API và chứng cứ code

- Scenario lưu input/context/library/seed/version/hash/outputs theo UUID; recommendations lưu bản mới có `parent_id`.
- Có database cấu hình: bảng `building_scenario_runs` trong PostgreSQL/PostGIS. Không có: atomic JSON ở `SCENARIO_DATA_DIR` hoặc `data/scenarios`. Lỗi database không tự âm thầm chuyển kho.
- Artifacts SUMO/SWMM ở `SIMULATION_WORK_DIR` hoặc thư mục tạm; ZIP có input/output/manifest. Scenario JSON và artifacts là hai kho riêng.
- API predict: `POST /api/v1/scenarios/integrated/predict`; gợi ý: `POST /api/v1/scenarios/integrated/{UUID}/recommendations`; GET mở run và GET artifacts.
- Giới hạn hiện tại: khu đất ≤100.000 m², tối đa 20 blocks, 8.000 xe giờ mô phỏng, hai requests solver đồng thời; chưa job queue nền/persistent hoặc authentication sản phẩm.

| Nội dung | Code |
|---|---|
| Input và giới hạn | [models.py](../backend/app/services/simulation/integrated/models.py) |
| Hệ số synthetic và lịch | [library.py](../backend/app/services/simulation/integrated/library.py) |
| Snapshot context, baseline, lớp nguồn | [context.py](../backend/app/services/simulation/integrated/context.py) |
| Diện tích/bóng đổ | [geometry.py](../backend/app/services/simulation/integrated/geometry.py) |
| Điện/nước/trips theo giờ | [demand.py](../backend/app/services/simulation/integrated/demand.py) |
| Graph SUMO và SWMM input | [solvers.py](../backend/app/services/simulation/integrated/solvers.py) |
| Đọc SWMM outputs | [swmm_worker.py](../backend/app/services/simulation/integrated/swmm_worker.py) |
| 22 metrics, đánh giá/gợi ý | [engine.py](../backend/app/services/simulation/integrated/engine.py) |
| Preset, API và export | [integrated_scenarios.py](../backend/app/routers/integrated_scenarios.py) |
| UI/map hiện vẽ gì | [integrated.js](../backend/app/static/integrated.js) |
| Risk P90 | [risk_assessment.py](../etl/src/pipelines/flood_risk/risk_assessment.py) |
| JSON/PostGIS | [store.py](../backend/app/services/simulation/store.py) |

**Kết luận:** demo đã chứng minh luồng dự tính tác động đa feature và chạy lại gợi ý. Việc ưu tiên tiếp theo là nâng nền thực, tham số có nguồn và kiểm chứng; chưa nên trình bày các số trên mạng synthetic là dự báo chính xác cho địa phương.
