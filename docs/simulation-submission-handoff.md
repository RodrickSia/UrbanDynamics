# Bàn giao nâng cấp trước nộp: QCVN và gộp parcel

## Người dùng thao tác

Trong `/simulation/planning`: nạp snapshot → chọn các thửa chung cạnh → bật **Gộp các parcel đang chọn thành một khu dự án** → nhập tổng căn/cư dân/sàn/tầng → bật **Kèm đối chiếu QCVN đô thị 2021** → nạp → preflight → chạy. Hai thửa + 20 căn = một project 20 căn; không phải 40 căn.

Phần gộp là thao tác geometry cho mô phỏng, không hợp thửa pháp lý. Phần đối chiếu QCVN là chỉ tiêu tối thiểu/phạm vi tham chiếu, không xác nhận được phép xây hoặc biến capacity giả lập thành capacity quan trắc.

## API dùng ngay cho frontend nhóm

Các endpoint hiện có trên branch simulation:

| Việc | Endpoint |
|---|---|
| Danh sách snapshot đóng băng đã cài | `GET /api/v1/planning/demo/system/snapshots` |
| Parcel đủ phạm vi demo trong snapshot | `GET /api/v1/planning/demo/system/snapshots/{sha256}/parcels` |
| Catalog QCVN có nguồn/hash | `GET /api/v1/planning/demo/system/vietnam-catalog` |
| Chuẩn bị study từ các nhóm parcel | `POST /api/v1/planning/demo/system/prepare` |
| Preflight | `POST /api/v1/planning/studies/preflight` |
| Lưu study | `POST /api/v1/planning/studies` |
| Tạo job | `POST /api/v1/planning/studies/{study_id}/runs` |
| Poll job / đọc kết quả | `GET /api/v1/planning/jobs/{job_id}` / `GET /api/v1/planning/runs/{result_id}` |

Các endpoint `/demo/system` cần `PLANNING_SYSTEM_DEMO_ENABLED=1`, snapshot đã cài và ID khớp dữ liệu snapshot. Frontend có thể lấy ID được click trên map hiện có, đối chiếu danh sách đủ điều kiện rồi gửi request; không lấy polygon simplify/clip từ vector tile làm geometry tính toán. Chưa có adapter đọc tùy ý mọi parcel live từ warehouse hoặc zoning revision; không coi luồng chuẩn bị snapshot là toàn thành phố live.

### Request chuẩn bị một building trên hai parcel

```json
{
  "snapshot_id": "<SHA-256 của snapshot đã cài>",
  "parcel_ids": ["<parcel-A>", "<parcel-B>"],
  "parcel_groups": [["<parcel-A>", "<parcel-B>"]],
  "mode": "site_selection",
  "housing_units": 20,
  "residents": 60,
  "floors": 4,
  "floor_area_m2": 1600,
  "background_mode": "synthetic_capacity_v1",
  "planning_catalog": "qcvn_urban_2021",
  "traffic_network_mode": "osm_snapshot",
  "sensitivity": false,
  "conditions": {"traffic_hours": [18], "seeds": [2026, 2027, 2028]}
}
```

Placeholder trên phải thay bằng ID thật. `parcel_groups` có thể chứa nhiều nhóm rời nhau **giữa các project** để so vị trí hoặc tính cộng dồn. Mỗi nhóm bên trong phải liên tục, không chồng nguồn với nhóm khác; tối đa sáu thửa nguồn trong study. Nhóm có tổng diện tích/độ phức tạp vượt phạm vi demo có thể bị từ chối. Không tự buffer để lấp khe hoặc bỏ phần rời của MultiPolygon.

Nếu frontend có plan đầy đủ, dùng `group_developments: {"G1": <Design>, "G2": <Design>}`. Design là schema hiện có gồm buildings/footprint/use/floors/height_m/gross_floor_area_m2/units/residents và bề mặt/cây/lưu trữ. Không gửi `programs`, `developments` hoặc `scenario_parcels` theo từng thửa trong grouped mode. Building phải nằm trong ranh union. Form demo dùng chung chương trình cho các nhóm; plan riêng theo nhóm gửi qua API/JSON.

Response chứa `study.projects` và `study.system_parcel_groups`, ví dụ `{"P1": ["A", "B"]}`. `system_parcel_bindings` dành cho chế độ một parcel/project cũ sẽ rỗng. Baseline được cắt một lần trên union từ cùng snapshot; geometry và member ID được kiểm tra lại khi lưu/chạy. Phân bố dân số và tải vẫn theo ledger; không cộng tải từng thửa rồi cộng thêm tổng nhóm lần nữa.

### Kết quả frontend cần hiển thị

- Kết quả model cũ giữ nguyên: metrics/comparison/traffic/drainage/utility_zones/school_services.
- Mỗi state có thêm `vietnam_planning_requirements` khi chọn catalog; baseline và option/phase đều có để đối chiếu.
- `context.vietnam_planning_catalog` chứa số phiên bản, hash, nguồn và phạm vi; `system_background.parcel_groups` / `selected_parcels` giữ member geometry và `planning_review.source_parcel_reviews` giữ cảnh báo từng thửa.
- `water_domestic_minimum_m3_day`: dân số mô phỏng đủ căn cứ × 80 L/người/ngày / 1000. Đây chỉ là sinh hoạt nội thị, chưa phải tổng mọi thành phần nước đô thị hoặc consumption forecast. Nước vận hành vẫn dùng hệ số của mô hình, không bị âm thầm thay xuống mức tối thiểu.
- `school_provision`: chỗ mầm non/tiểu học/THCS theo 50/65/55 chỗ trên 1.000 dân; đất tối thiểu 12/10/10 m²/chỗ. Là mức bố trí tối thiểu, không phải số học sinh thực tế. Trường chung chung không được tự phân loại cấp học; tổng capacity khai báo theo cấp không tự trở thành kết luận đủ chỗ trong phạm vi đi bộ.
- `school_radius_checks`: 500 m theo profile đô thị này, khoảng thẳng tâm khu đất → điểm trường có cấp xác định. Giới hạn walk-network và phân bổ chỗ hiện có là output khác; không đổi thành 500 m mà gọi đó là kiểm tra pháp lý. Ngoại lệ 1.000 m không mặc định cho THCS.
- `density_checks`: nhóm chung cư cùng chiều cao, nội suy bảng 2.9 theo diện tích và chiều cao; hơn 46 m xét thêm FAR 13. Kiểu hỗn hợp chiều cao/công năng hoặc đế-tháp cần đánh giá riêng. `within_reference_limit` không có nghĩa được phép xây; chỉ tiêu địa phương/chỉ giới/giấy phép chưa xác minh.

## Nguồn và phần chưa làm

Catalog máy đọc: [vietnam_catalog.json](../backend/app/services/simulation/planning/vietnam_catalog.json). Nguồn: [QCVN 01:2021/BXD trên cổng tài liệu xây dựng](https://tailieuxaydung.quangngai.gov.vn/vi/phap-luat/thong-tu/01-2021-tt-bxd), mục 2.10.2, 2.3.3/bảng 2.4, bảng 2.9 và chú thích nội suy. [TCVN 13606:2023](https://tieuchuan.vsqi.gov.vn/tieuchuan/view?sohieu=TCVN+13606%3A2023) được ghi là tham chiếu thiết kế mạng nước; chưa đưa số chưa kiểm chứng của tiêu chuẩn này vào model.

Chưa tính tổng GPMB: snapshot demo hiện thiếu giá áp dụng đủ căn cứ và đơn giá tài sản/phá dỡ; không tự dựng tổng tiền. Phần chi phí giữ sau khi có dữ liệu phù hợp. Không có DEM ponding hoặc sửa SUMO để ép kết quả tăng đơn điệu trong lần này.

Model mới là `planning-studies-0.19`: kết quả job cũ vẫn đọc được, nhưng cần study/revision mới để chạy bằng catalog/group mới. Không sửa đầu vào hoặc kết quả job cũ.
