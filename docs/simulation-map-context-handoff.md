# Nối building hiện trạng từ map vào simulation

## Phạm vi bàn giao

Backend `integrated-building-1.4` nhận building đang có trên map qua `map_context` trong request hiện có. Không thêm màn hình hoặc sửa frontend. Đây là dữ liệu nguồn do client gửi, **chưa được backend xác minh với Goong**; không coi một tile tải được là khảo sát đầy đủ. Bản này bổ sung [catalog hệ số nhu cầu và API độ nhạy](simulation-demand-coefficients.md).

Luồng tích hợp:

1. Người dùng chọn polygon khu đất và tạo building plan.
2. Frontend lấy building từ source của map trong khu đất và vùng lân cận tối đa 300 m. Gửi geometry và thuộc tính nguồn; nếu tile chưa tải đủ, hiển thị cảnh báo.
3. Gửi `POST /api/v1/scenarios/integrated/context` để xem nền và độ đầy đủ. Endpoint này không chạy SUMO/SWMM.
4. Gửi cùng payload đến `POST /api/v1/scenarios/integrated/predict`. Khi preflight có `data_inventory.snapshot_id`, gửi lại ID đó và `data_mode: "snapshot_required"` để giữ đúng snapshot. Giữ nguyên `map_context` đã dùng ở preflight.
5. Dùng API đọc, recommendations và artifacts hiện có. Gợi ý giữ nguyên context của lần predict, không lấy lại building từ map.

Frontend hiện có layer `urban-buildings-3d`, source `composite`, source-layer `VN_Building`. Đọc source feature sau khi tile tải; strip các trường MapLibre như `layer`, `source`, `state` và chỉ gửi DTO dưới đây. Không gửi API key hay URL tile.

## DTO

`map_context` là trường tùy chọn; client cũ tiếp tục chạy được.

```json
{
  "provider": "goong",
  "source_layer": "VN_Building",
  "dataset_version": null,
  "captured_at": "2026-10-11T08:00:00+07:00",
  "bbox": [106.75, 10.81, 106.77, 10.83],
  "coverage": "loaded_tiles",
  "buildings": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "id": "source-building-id",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[106.7601,10.8201],[106.7604,10.8201],[106.7604,10.8204],[106.7601,10.8204],[106.7601,10.8201]]]
      },
      "properties": {"height": 18, "building:levels": 6, "building": "apartments"},
      "height_kind": "source_attribute"
    }]
  }
}
```

Đặt DTO vào payload chứa `site`, `development`, `conditions`; không gửi DTO này một mình. [Payload chạy được](samples/simulation-map-context.json) dùng **fixture giả lập**, không phải dữ liệu Goong đã tải thật.

| Trường | Quy tắc |
|---|---|
| `provider` | `goong`, `team_warehouse`, `osm`, `other`; chỉ nhãn nguồn, không tự gọi provider |
| `captured_at` | Thời điểm lấy dữ liệu có timezone |
| `bbox` | Bốn số WGS84 west/south/east/north, phải phủ toàn bộ `site`; chỉ mô tả phạm vi client đã lấy |
| `coverage` | `loaded_tiles` hoặc `provided_extract`; cả hai không tự chứng minh coverage đầy đủ |
| Geometry | Polygon hoặc MultiPolygon hợp lệ; giữ holes. Cùng ID ghép các mảnh, không bỏ mảnh tile còn lại |
| `id` | Dùng ID ổn định của nguồn nếu có. Không tự tạo mỗi mảnh một ID ngẫu nhiên |
| `properties` | Tối đa 64 thuộc tính scalar/feature; chọn thuộc tính cần thiết từ nguồn |
| `height_kind` | `source_attribute` mặc định, hoặc `visual_fallback`, `unknown` |

Giới hạn: 200 features, 20.000 vertices tổng, 2.000 vertices/feature, 500 vertices/polygon, 20 parts/MultiPolygon. Site tối đa 100.000 m²; baseline tối đa 20 building parts. Nếu nhiều hơn, thu nhỏ khu thử nghiệm. `synthetic` không nhận `map_context`; dùng `auto` hoặc `snapshot_required`.

### Chiều cao và công năng

- Lấy số dương ≤400 m đầu tiên theo thứ tự `max_height`, `height`, `render_height`, `building:height`. Boolean, số âm/0, ngoài giới hạn hoặc chuỗi không đọc được không dùng.
- **Giá trị 12 m frontend dùng khi thiếu dữ liệu chỉ để vẽ.** Nên gửi raw properties không có height; nếu gửi chiều cao đã tính từ fallback thì bắt buộc `height_kind: "visual_fallback"`. Backend không thể biết số 12 là dữ liệu nguồn hay fallback nếu client đánh dấu sai.
- Thiếu chiều cao: số tầng nguồn hợp lệ ×3 m; thiếu cả hai: 1 tầng, 3 m. Nhãn `inferred_from_source_floors_3m` / `synthetic_default`, không phải chiều cao thật.
- Số tầng: `building:levels`, `levels`, `floors`, phải là số nguyên 1–100. Thiếu tầng nhưng có height: suy ra round(height/3), giới hạn 1–100, có nhãn giả định 3 m/tầng.
- Công năng nhận từ `use` / `building` / `amenity`; nhận diện residential (apartments/house/detached), school, office, hospital; còn lại `other`.
- Không suy ra dân số hiện trạng của building từ tile hoặc dân số bbox. Residents/staff/visitors/units chưa biết mặc định 0 và có nhãn `unknown_assumed_zero`. Nhu cầu điện theo diện tích sàn vẫn dùng thư viện ước tính hiện có.
- Trùng geometry chỉ giữ một footprint; cùng ID có height/tầng nguồn mâu thuẫn hoặc geometry trùng có height nguồn mâu thuẫn trả 422. Baseline loại diện tích chồng nhau: map ưu tiên trước OSM, cùng nguồn xét footprint lớn trước. Đây là mô hình footprint đơn giản, chưa mô hình khối đế và tháp chồng lớp khác chiều cao.

## Nền, phương án và công trình lân cận

Thứ tự chọn nền trong khu đất:

1. `baseline.design` + `baseline.source` do người dùng cung cấp.
2. Building từ map, bổ sung phần OSM chưa bị footprint map phủ; greens/WorldCover từ snapshot nếu có.
3. Các bề mặt chưa phân loại dùng 50% paved, 10% permeable, 40% green với nhãn synthetic. Nếu không có map/snapshot/khảo sát, nền demo cũ 15/15/70 vẫn hoạt động.

Không thấy building trên map không có nghĩa là đất trống. Các chỉ số cần occupancy hiện trạng vẫn là so sánh kịch bản trên nền chưa đủ dữ liệu.

`development` mô tả **toàn bộ phương án sau khi thay đổi trong khu đất**. Công trình baseline trong site được thay bằng phương án này. Nếu muốn giữ một công trình hiện hữu, phải đưa nó vào `development.buildings`; hiện chưa có trường `retained_building_ids`.

Phần footprint ngoài site, trong buffer 300 m, được giữ cố định ở `context.surrounding_buildings` và dùng trong cả baseline, development, recommendations. Building cắt qua ranh site được chia phần trong/ngoài. Map ưu tiên OSM để không tính hai lần cùng diện tích. Không tự chọn toàn thành phố, không biết các tile chưa tải.

Bóng đổ dùng `solar-geometry-2`: quét bóng theo vị trí mặt trời, height và footprint, sample 08–17 giờ UTC+7, polygon lúc 09/12/15. Trừ footprint building khỏi phần bóng trên mặt đất. `neighbour_shadow_m2` bao gồm bóng từ context cố định ngoài site, không phải riêng tác động building mới; xem delta khi so sánh. Mô hình nền phẳng, khối đặc từ mặt đất, bỏ qua min_height/ground elevation; chưa có nhiệt độ, radiation hoặc Tmrt.

## Trường response để frontend dùng

| Response | Nội dung |
|---|---|
| Preflight `baseline`, `baseline_provenance` | Nền chuẩn hóa và nguồn/giả định từng building |
| Preflight `surrounding_buildings` | GeoJSON phần building ngoài site, `height_m`, provenance |
| `data_inventory.map_context` | Nguồn, bbox, thời điểm, input/normalized count, số building có height nguồn hoặc giả định |
| `data_inventory.coverage.building_footprints` | `client_map_incomplete` hoặc `client_map_and_osm_incomplete` |
| `variants.*.buildings_map` | Công trình trong site, nhãn baseline/design và provenance |
| `variants.*.shadow.surrounding_buildings` | Context chung; có thể dùng dựng công trình quanh site |
| `variants.*.shadow.hourly`, `.map` | Bóng đổ trên nền có công trình lân cận |
| `assessment.rows` | Chênh lệch và đánh giá hiện có; không tự coi là dự báo đã hiệu chỉnh |

Input đầy đủ và context được lưu trong run; hash thay đổi khi chiều cao, geometry, nguồn hoặc thời điểm map thay đổi. Preflight không khóa dữ liệu warehouse đang thay đổi; dùng snapshot ID khi cần lặp lại cùng nền. Run đã lưu/recommendations dùng context đóng băng.

## Test local

Swagger: `http://127.0.0.1:8003/api/v1/docs`. Có thể paste payload mẫu vào hai endpoint context/predict. Sample có building cũ trong khu đất và building 60 m bên phía đông để nhìn thấy tác động bóng đổ.

```powershell
$payload = Get-Content docs/samples/simulation-map-context.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8003/api/v1/scenarios/integrated/context -ContentType application/json -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
```

Không có `map_context` từ frontend thật thì backend không tự lấy building Goong. Việc gửi DTO khi bấm simulation là phần tích hợp frontend còn lại.
