# Chuẩn hóa hệ số nhu cầu và phân tích độ nhạy

Ngày triển khai: **11/10/2026**. Model `integrated-building-1.4`, library `thu-duc-demo-library-1.3`, catalog `demand-coefficients-1`.

## 1. Đã triển khai

- Catalog 57 hệ số vô hướng: 9 hệ số × 5 công năng và 12 hệ số chung cho nước, nước thải, điện, trips và lưu lượng nền.
- Mỗi hệ số có giá trị, đơn vị, mẫu số, phạm vi, năm dữ liệu, nguồn số áp dụng hoặc nhãn giả định, và yêu cầu hiệu chỉnh địa phương.
- Một hệ số áp dụng số liệu nghiên cứu địa phương: điện văn phòng TP.HCM. 56 hệ số còn lại chưa có nguồn số trực tiếp phù hợp được xác minh; lưu lượng nền có thể được ước lượng theo dân số từ snapshot, vẫn chưa được hiệu chỉnh bằng counts.
- Phân biệt **số thực sự áp dụng** (`numeric_source`) với **số tham chiếu để so sánh** (`reference_anchors`). Trích được một quy chuẩn không có nghĩa hệ số demo là quan sát thực tế.
- Lưu catalog cùng context, hash và kết quả. Phân tích trên run đã lưu giữ nguyên building plan, snapshot, nền, lịch, capacity và seed.
- Có phân tích từng hệ số một (OAT), kiểm tra hướng tăng/giảm nhu cầu và việc vượt ngưỡng công suất giả định; tùy chọn chạy lại SUMO để kiểm tra delay/queue.

Đây là hoàn thành chức năng chuẩn hóa và kiểm tra độ nhạy. **Chưa hoàn thành hiệu chỉnh tất cả hệ số bằng dữ liệu địa phương**. Hourly profiles, spare capacity điện/nước/nước thải, cống, và các giả định vận hành vẫn cần dữ liệu hoặc kịch bản có nhãn.

## 2. Nguồn số đã kiểm tra

| Nguồn | Giá trị trích | Phạm vi/mẫu số | Cách dùng |
|---|---|---|---|
| [Hoang et al., điện văn phòng Việt Nam](https://publications.evolvingcities.org/proc-icec/article/view/19), DOI `10.55066/proc-icec.2021.19` | TP.HCM: **116,4 kWh/m² sàn/năm** | Mẫu văn phòng thương mại và cơ quan; khảo sát 2015, xuất bản 2022 | Áp dụng cho văn phòng bằng `116.4 / 365 ≈ 0.318904 kWh/m²/ngày lịch`; benchmark lịch sử, chưa hiệu chỉnh công trình/giờ đỉnh |
| [QCVN 01:2021/BXD, Công báo](https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/5/33751/35832-1-2021599-60001-2021-tt-bxd.pdf), mục 2.10.2, 2.11.1; PDF trang 39, 41 | Sinh hoạt tối thiểu 80 L/người/ngày; trường học 15 L/học sinh/ngày; mầm non 75 L/trẻ/ngày; công cộng/dịch vụ khác 2 L/m² sàn/ngày; chỉ tiêu nước thải sinh hoạt ≥80% chỉ tiêu cấp nước | Chỉ tiêu quy hoạch Việt Nam, không phải mức tiêu thụ trung bình của một tòa nhà | Lưu tham chiếu; không gán mức tối thiểu thành nhu cầu điển hình hay coi 0,8 là tỷ lệ hồi lưu đã đo |
| [PUB, chiến dịch tiết kiệm nước 2026](https://www.pub.gov.sg/Resources/News-Room/PressReleases/2026/03/Its-Everyones-Business-to-Make-Every-Drop-Count), đoạn 6 | **141 L/người/ngày**, năm 2025 | Trung bình nước hộ gia đình Singapore; công bố 17/03/2026 | So sánh tham khảo; không áp dụng tự động cho chung cư TP.HCM |
| [JICA, phụ lục khảo sát giao thông](https://openjicareport.jica.go.jp/pdf/12305009_02.pdf), Appendix 1-5, PDF trang 7, bảng 1.1.5 và đoạn giải thích | Gross trips: **2,5/người/ngày** (2002); **3,2/người/ngày** (2013) | Chuyến đi của người trên toàn vùng nghiên cứu, kể cả người không đi và chuyến không gắn với nhà | Không thay trực tiếp trips qua cổng hoặc vehicles/hour. Demo 2 trips/cư dân/ngày vẫn là giả định một đi/một về |

QCVN 01:2021 được gắn mốc cần review sau 31/12/2026 theo [thông báo của Bộ Xây dựng về QCVN 01:2026/BXD](https://moc.gov.vn/en/news/95350/thong-tu-ban-hanh-quy-chuan-ky-thuat-quoc-gia-ve-quy-hoach-do-thi-va-nong-thon.aspx), hiệu lực 01/01/2027. Catalog tính `review_due` theo ngày chạy. Không dùng catalog này để xác nhận tuân thủ pháp lý.

## 3. Profile và giá trị mặc định

`conditions.coefficient_profile` mặc định `reviewed`. Người dùng vẫn chỉ nhập building plan; ứng dụng chọn profile, không bắt nhập các hệ số kỹ thuật.

- `reviewed`: điện văn phòng lấy benchmark 116,4/365. Các giả định khác giữ nguyên và có nhãn.
- `demo`: giữ điện văn phòng 0,14 kWh/m²/ngày như demo trước. Không gán nguồn nghiên cứu cho giá trị này.
- Run cũ: dùng giá trị đã lưu, không nâng cấp hệ số sang bản mới khi phân tích độ nhạy.

Các giả định nổi bật ở mức `base`:

| Hệ số | Mặc định | Trạng thái |
|---|---:|---|
| Nước cư dân chung cư | 120 L/người/ngày | Giả định; tham chiếu quy hoạch 80 và PUB 141 không phải nguồn trực tiếp |
| Điện chung cư | 0,11 kWh/m² sàn/ngày | Giả định; không áp dụng nghiên cứu văn phòng sang nhà ở |
| Hồi lưu nước thải | 0,8 lượng nước trong nhà | Giả định; tưới cây không tính vào nước thải |
| Trips cư dân/khách/nhân viên | 2/người/ngày | Đi/về theo kịch bản; không phải số đếm qua cổng |
| Tỷ lệ person trips ô tô/xe máy | 0,25 / 0,55 | Giả định; phần còn lại chưa đưa vào SUMO |
| Occupancy ô tô/xe máy | 1,6 / 1,2 người/xe | Giả định |
| Tưới cây | 2 L/m² xanh/ngày | Giả định |
| Sạc EV | 7 kW/trụ, 4 giờ/ngày | Giả định; không phải cấu hình thiết bị đã khảo sát |
| Điện xử lý tái sử dụng nước | 0,6 kWh/m³ | Giả định; cần kiểm tra công nghệ xử lý |

Hai hệ số trước đây nằm trực tiếp trong công thức (`staff_trips_day = 2`, `reuse_treatment_kwh_m3 = 0.6`) đã đưa vào library/catalog để có thể audit và phân tích.

## 4. Công thức và phạm vi

Với từng block và profile giờ đã chuẩn hóa tổng bằng 1:

```text
Nước trong nhà (m³/ngày)
  = fixture_factor × (residents × resident_rate
    + staff × staff_rate + visitors × visitor_rate + daily_users × user_rate) / 1000
Nước tưới = green_m² × irrigation_rate / 1000
Nước thải trước tái sử dụng = nước trong nhà × return_fraction
Reuse = min(reuse thiết kế, nước thải trước reuse, tổng nước trước reuse)
Nước cấp mới = tổng nước trước reuse − reuse
Nước thải xả = nước thải trước reuse − reuse

Điện (kWh/ngày) = Σ(sàn block × EUI × equipment_factor)
  + EV_chargers × ev_kW × ev_hours + reuse × reuse_treatment_kWh_m³
Trips người/ngày = Σ(residents × resident_trip_rate + staff × staff_trip_rate
  + visitors × visitor_trip_rate + daily_users × user_trip_rate) × scenario_load_factor
Trips ô tô = trips người × car_share / car_occupancy
Trips xe máy = trips người × motorcycle_share / motorcycle_occupancy
```

Profile giờ dùng cho điện, nước và trips; EV/tưới/reuse có giờ riêng. `power_peak_kw` là cực đại profile điện theo các bin một giờ, chưa dự báo peak tức thời thực địa. `vehicle_peak_hour` là nhu cầu cực đại theo giờ của công trình; SUMO sensitivity giữ **giờ so sánh chung** của run gốc, không đổi sang giờ peak riêng cho mỗi case.

Capacity screening dùng cùng hàm với đánh giá chính:

- Nước/nước thải sau xây ≤ trước xây + spare capacity giả định.
- Điện: `max_h(after_h − before_h) ≤ power_spare_kw`. Không lấy hiệu của hai peak tại hai giờ khác nhau.
- Vượt/không vượt capacity trong kết quả chỉ là kết luận theo kịch bản; chưa có mạng ống, máy biến áp hoặc capacity xác minh.

## 5. API cho frontend

### Catalog và preflight

`GET /api/v1/scenarios/integrated/parameters?profile=reviewed` trả catalog mức `base` để xem cấu trúc. **Giá trị thực của run** nằm trong `context.demand_parameter_catalog`, vì `level`, population-derived background và snapshot có thể khác.

`POST /api/v1/scenarios/integrated/context` và response của `/predict` đều có `demand_parameter_catalog`.

Đọc `parameters[parameter_id].numeric_source`, `reference_anchors`, `needs_local_calibration`, `value_status`; không suy ra “đã xác minh” chỉ từ sự có mặt của URL nguồn.

### Độ nhạy nhu cầu nhanh

`POST /api/v1/scenarios/integrated/{run_id}/sensitivity`:

```json
{
  "mode": "demand",
  "parameter_ids": [
    "uses.residential.water_l_person_day",
    "return_fraction",
    "uses.residential.energy_kwh_m2_day"
  ],
  "low_multiplier": 0.7,
  "high_multiplier": 1.3
}
```

Chạy 6 case: mỗi hệ số thấp/cao riêng, giữ các hệ số khác cố định. Trả 8 chỉ số nhu cầu và 3 capacity screens; **không tính lại delay/queue**. Bỏ `parameter_ids` sẽ kiểm tra mọi hệ số nhu cầu cho công năng có trong baseline/development; hệ số không hoạt động trong thiết kế có thể cho độ nhạy bằng 0. Danh sách tường minh tối đa 12 hệ số.

### Chạy lại giao thông

```json
{
  "mode": "native_traffic",
  "parameter_ids": ["uses.residential.resident_trips_day"],
  "low_multiplier": 0.7,
  "high_multiplier": 1.3
}
```

Yêu cầu 1–3 hệ số nhóm traffic/background. Với một hệ số: 2 case × baseline/development = **4 lần SUMO thật**. Có thể thay `car_person_share`, `car_occupancy`, `motorcycle_person_share`, `motorcycle_occupancy`, hoặc `background_vehicles_hour`. Không chạy lại SWMM/bóng đổ/recommendations vì không thuộc phạm vi này.

Giữ nguyên topology, lịch, seed, giờ so sánh và background trừ khi chính `background_vehicles_hour` được chọn. Số liệu dân số không tự chuyển thành background mới khi thay trips công trình. Tỷ lệ mode được giới hạn để tổng car + motorcycle ≤1; `ev_hours` và background làm tròn số nguyên; response ghi rõ khi bị giới hạn/làm tròn.

### Lưu và đọc kết quả

Response 201 tạo **run con** có `parent_id`, `analysis_kind = parameter_sensitivity` và `sensitivity`. Run gốc không thay đổi. Có thể GET run con và tải `/artifacts`; ZIP native có input/output SUMO của các case.

Để hiển thị phân tích mới, đọc **`sensitivity.reference`, `sensitivity.cases`, `sensitivity.stability`, `sensitivity.target_stability`, `sensitivity.ranked_parameters`**. Các `variants`, `assessment`, `recommendations` ở cấp ngoài vẫn là kết quả gốc; không dùng chúng như kết quả đã cập nhật theo case.

`stability.verdict_stable` kiểm tra hướng tăng/giảm; `target_stability.stable` kiểm tra ngưỡng bị đổi kết luận hay không. Nhu cầu có thể luôn tăng nhưng một case vượt capacity và case khác không vượt. Rank ưu tiên số lần đổi kết luận ngưỡng rồi biên độ tương đối; metric nhỏ được chuẩn hóa với mẫu số tối thiểu 1 đơn vị.

Khoảng ±30% mặc định là **kịch bản thử độ nhạy**, không phải khoảng tin cậy thống kê. OAT không mô tả trường hợp tất cả hệ số cùng thay đổi hoặc xác suất kết quả.

## 6. Tương thích và kiểm tra

- Sửa SUMO synthetic không ghi `properties.simulated` vào `context.roads`, tránh thay đổi context sau khi hash/lưu.
- Với run cũ model 1.1–1.3 bị lỗi này, chỉ phục hồi bản sao để phân tích nếu bỏ đúng trường đầu ra đó làm hash khớp hash gốc. Không bỏ qua kiểm tra integrity và không sửa run cha.
- Recommendation yêu cầu model hiện tại; run phiên bản cũ cần predict mới để tạo recommendation.
- Script kiểm tra API: `scripts/test-simulation-parameters-local.py`. Kết quả thực chạy nằm trong [báo cáo test](simulation-demand-coefficients-test-report.md).

## 7. Việc còn cần dữ liệu

Ưu tiên tiếp theo là hiệu chỉnh trips, mode share và hourly profiles bằng counts/khảo sát; thu thập điện/nước theo công năng, occupancy và điều kiện vận hành địa phương; đo/thu thập capacity hạ tầng. Có thể dùng kịch bản giả lập hợp lý trong cuộc thi, nhưng phải giữ nhãn và trình bày các kết luận nhạy với giả định. Chuẩn hóa hệ số chưa tạo ra xác thực ngoài thực địa cho mô hình.
