# Nền, capacity và độ nhạy của demo

## Cách dùng

1. Mở `/simulation/planning`, nạp snapshot và chọn parcel trên bản đồ.
2. Nhập building plan: số căn, cư dân, tầng, diện tích sàn. Chọn so vị trí hoặc cộng dồn.
3. Chọn **Nguồn thật** để giữ occupancy/capacity chưa biết; hoặc **Minh họa capacity v1** để thử một hiện trạng vận hành giả lập trên geometry thật.
4. Bấm **Nạp plan và dữ liệu nền**, rồi **Kiểm tra đầu vào**. Xem số lần SUMO/SWMM dự kiến trước khi chạy.
5. Chạy **Screening** trước để xem tải, capacity, chỗ học, runoff và bóng. Chọn native để chạy SUMO/SWMM; chọn Độ nhạy để chạy bộ giả định đã nạp. Các job cũ giữ nguyên dữ liệu, cần tạo job mới để dùng gói này.
6. Xem phương án riêng, cộng dồn, giai đoạn, bảng capacity, Pareto và độ ổn định. Capacity thiếu không được coi là còn dư. Không xếp hạng từ một chỉ số hoặc một seed.

## Gói giả lập v1

| Dữ liệu | Giá trị / cách tạo | Phạm vi |
|---|---|---|
| Geometry, bề mặt nền | Giữ parcel, footprint OSM và bề mặt WorldCover/default đã nạp | Có nguồn nhưng kiểm kê chưa đầy đủ |
| Occupancy nền | Giả định footprint là nhà ở; floor(sàn/35) người; ceil(người/3) căn | Giả lập; không có footprint không chứng minh đất trống |
| Dân số ngoài parcel | 1.200 người; tổng bao gồm phần parcel, trừ đúng contribution có hash | Giả lập, thay WorldPop **cho tính nhu cầu**; WorldPop giữ làm context |
| Tải điện ngoài parcel | 80 kW mỗi giờ | Giả lập, chưa có đường cong phụ tải khảo sát |
| Tải nước / nước thải ngoài parcel | 140 / 112 m³/ngày | Giả lập |
| Capacity dùng chung | 95 kW; 160 m³ nước/ngày; 128 m³ nước thải/ngày | Cố định, không suy từ building plan; không có mạng dịch vụ khảo sát |
| Trường học | Giữ vị trí OSM; nếu không có, đặt một điểm trong vùng; 240 chỗ/trường | Capacity và điểm fallback giả lập |
| Học sinh nền | 216 = 1.200 × 18%; đặt tại trường đầu, 0 reserved ngoài vùng | Giả lập; chưa có phân bố học sinh thực |
| Lưu lượng | Dùng counting đã cài khi có, hoặc OD khai báo | Tham chiếu chuyển vùng; chưa hiệu chỉnh OD |
| Cống / tín hiệu / OD / kết nối | Giữ giả định hiện có | Không được biến thành số liệu quan trắc bằng việc chọn gói capacity |

Tải điện/nước/nước thải, traffic và học sinh ngoài parcel đã loại các parcel đăng ký; bộ máy thêm tải parcel đúng một lần. Chỉ snapshot dân số là tổng inclusive với contribution và hash để kiểm tra phép trừ. Capacity và hiện trạng không thay theo quy mô phương án.

## Bộ độ nhạy

Reference và sáu ca (nếu OD nền bằng 0 thì bỏ hai ca traffic): hệ số nhu cầu low/high; capacity hạ tầng và trường ×0,8; mưa ×1,2 (tối đa 300 mm); OD ×0,5 / ×1,25 (tối đa 6.000/h). Mỗi lần chỉ thay nhóm được ghi trong ca; plan, geometry và reserved places giữ nguyên. Đây là kiểm tra độ nhạy từng nhóm, chưa phải phân bố xác suất hay kiểm tra mọi tổ hợp bất lợi.

Screening nhanh **không chạy SUMO/SWMM**; thay OD không sinh delay trong chế độ này. Native dùng seed 2026, 2027, 2028; UI hiển thị dải kết quả và mức ổn định từ các mẫu, không gọi đó là khoảng tin cậy. Native có thể chạy lâu khi nhiều parcel, giờ và ca; preflight cho biết khối lượng, job có thể hủy/chạy tiếp.

## Giới hạn

Gói này giúp kiểm thử vượt ngưỡng và đánh đổi, không hiệu chỉnh tính đúng ngoài thực địa. Không xác nhận đất trống, pháp lý, capacity mạng điện/nước/cống, hay nhu cầu thực. School walking vẫn dùng OSM và giữ cặp không nối được là unavailable. Học sinh nền đặt tập trung có thể làm kết quả trường quá thuận lợi; cần phân bố dân cư và capacity thực để thay thế.
