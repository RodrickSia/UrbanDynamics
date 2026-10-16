# Goong cho preview 8192

Web demo sử dụng hai credential riêng:

- `VITE_GOONG_MAPTILES_KEY`: key nền bản đồ, đưa vào frontend build.
- `GOONG_REST_API_KEY`: key Places, chỉ đưa vào backend qua file env riêng;
  không đưa vào frontend bundle hoặc worker.

Cấu hình workstation ở `.env.development-goong.local`, đã được Git ignore.
Helper deploy ưu tiên file này thay cho map key trước đó. Không ghi giá trị key
vào tài liệu, commit hoặc log. Target vẫn là preview cổng server 51875, tunnel
local 8192; web chính 51873 không được thay đổi.

## Search places

Ô tìm kiếm được nối với dữ liệu Goong thật thay cho chỉ tìm ba thành phố mẫu:

1. Nhập tối thiểu 3 ký tự; debounce 350 ms và hủy truy vấn cũ khi thay chữ.
2. Backend gọi Autocomplete, trả tối đa 5 gợi ý.
3. Chọn gợi ý (hoặc Enter sau khi gợi ý tải xong) để lấy Place Detail.
4. Bản đồ chuyển tới tọa độ nguồn; địa điểm vào recent list tối đa 5 mục.

Endpoints ứng dụng: `GET /api/v1/places/search?q=...` và
`GET /api/v1/places/detail?place_id=...`.
Adapter hiện sử dụng Goong `/v2/place/autocomplete` và `/v2/place/detail`,
giữ địa chỉ mới và địa chỉ cũ do provider trả về. Đã bổ sung
[Distance Matrix/Directions V2 và giới hạn mode](agent-query-routing-upgrade.md).
Có cache trong process 5 phút, giới hạn 128 request keys. Timeout/lỗi provider
hiển thị rõ, không thay bằng tọa độ đoán. Places không cung cấp thời tiết;
địa điểm mới hiển thị thời tiết chưa biết.

## AI agent

Tool `area_select` có thêm `source=goong_place` để tra địa điểm bằng Goong.
Nếu nhiều kết quả, agent nhận danh sách và hỏi người dùng chọn trước khi đổi
phạm vi. Khi đã chọn, khu phân tích là **buffer 1.000 m quanh tọa độ địa điểm**,
có nhãn rõ; không phải ranh giới quận hay thửa đất. Một câu trả lời chọn kết quả
được đối chiếu truy vấn Goong đang chờ, không tự dùng lại vị trí cũ.

`source=street` vẫn tìm đường/hẻm từ mạng đường OSM của nhóm trước.
`source=place` vẫn dùng Nominatim cho bbox địa danh; khi cần toàn quận phải dùng
phạm vi phù hợp, không dùng buffer quanh một điểm Goong để đại diện toàn quận.
Distance Matrix và routing được bổ sung trong bản nâng cấp tiếp theo cùng ngày;
Speed Limit chưa được thêm.
