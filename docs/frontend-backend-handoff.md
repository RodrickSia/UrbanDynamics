# UrbanDynamics — bàn giao tích hợp frontend/backend

Tài liệu này ghi lại trạng thái frontend sau đợt cải tiến giao diện bản đồ và hợp đồng dữ liệu mà backend cần cung cấp. Mục tiêu là để backend có thể tích hợp từng nguồn dữ liệu mà không phải suy đoán hành vi của UI.

## 1. Trạng thái hiện tại

Backend hiện chỉ có `GET /health`. Frontend đã hoàn thiện lớp giao diện và tương tác cho:

- bản đồ toàn Việt Nam, mặc định 2D;
- chuyển đổi rõ ràng giữa 2D và 3D;
- phóng to, thu nhỏ, định vị bằng Geolocation API của trình duyệt;
- chuyển nền mặc định/vệ tinh; nền quy hoạch hiện bị khóa vì chưa có nguồn dữ liệu;
- vẽ vùng polygon và chọn đối tượng bản đồ;
- bảng tìm kiếm, lịch sử tìm kiếm cục bộ, thông tin khu vực/thời tiết mẫu;
- bảng lớp dữ liệu đô thị.

Giao diện hiển thị hoàn toàn bằng tiếng Anh. Search và Place details nằm bên trái; Data Layers dùng drawer toàn chiều cao bên phải, còn Polygon drawing là thanh công cụ nhỏ ở giữa cạnh dưới. Marker người dùng chỉ xuất hiện sau khi định vị thành công; marker địa điểm xuất hiện sau khi chọn kết quả hoặc chọn điểm trên bản đồ. Click vùng bản đồ trống lần thứ hai sẽ đóng chi tiết chung; click POI có tên luôn mở hoặc cập nhật Place details.

Nền Satellite dùng style raster-only từ `satellite.goong.io`, không nạp thêm symbol layer của style hybrid để tránh nhãn địa điểm bị lặp trên ảnh vệ tinh. Vì style này không có source `composite / VN_Building`, 3D building sẽ tự giảm cấp trong Satellite; địa hình DEM vẫn có thể hoạt động độc lập.

Các lớp `Dân số`, `Công trình công cộng`, `Giao thông`, `Mưa`, `Ngập`, `Quy hoạch`, `Giá đất`, `Mật độ đường` và `Không gian xanh` đang bị vô hiệu hóa có chủ đích. Frontend không dựng dữ liệu giả khi backend chưa kết nối. Lớp tòa nhà 3D dùng nguồn có sẵn trong style Goong nếu nguồn đó tồn tại.

Thông tin thời tiết hiện vẫn là dữ liệu placeholder cục bộ nhưng không còn hiển thị nhãn kỹ thuật; lịch sử tìm kiếm chỉ nằm trong state của trình duyệt và mất khi tải lại trang.

## 2. Biến môi trường và ranh giới bảo mật

Frontend dùng:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_GOONG_MAPTILES_KEY=<public browser map tiles key>
```

`VITE_GOONG_MAPTILES_KEY` được nhúng vào bundle và vì vậy phải được xem là khóa công khai phía trình duyệt, có giới hạn origin tại nhà cung cấp. Không đưa Goong REST API key, khóa dịch vụ thời tiết hoặc khóa nguồn dữ liệu vào biến bắt đầu bằng `VITE_`.

Backend chịu trách nhiệm giữ bí mật và proxy các dịch vụ tìm kiếm/geocoding/thời tiết. Frontend không gửi tọa độ định vị đi đâu cho tới khi người dùng chủ động dùng một tính năng cần dữ liệu theo vị trí.

## 3. Quy ước chung cho API

- Base path: `/api/v1`.
- Tọa độ và GeoJSON: WGS84/EPSG:4326, thứ tự luôn là `[longitude, latitude]`.
- Thời gian: ISO 8601 UTC, ví dụ `2026-09-30T06:30:00Z`.
- JSON response thành công nên có `data`; metadata đặt trong `meta`.
- Danh sách phải có giới hạn hoặc phân trang. Không trả toàn bộ dữ liệu toàn quốc trong một response.
- Backend nên trả `Cache-Control`/`ETag` phù hợp cho dữ liệu ít thay đổi.

Lỗi thống nhất:

```json
{
  "error": {
    "code": "INVALID_BBOX",
    "message": "bbox không hợp lệ",
    "details": {},
    "requestId": "req_01K..."
  }
}
```

Mã HTTP mong đợi: `400` cho tham số sai, `401/403` khi cần quyền, `404` khi không có thực thể, `429` khi quá giới hạn và `5xx` cho lỗi dịch vụ. Không trả HTTP 200 kèm lỗi nghiệp vụ.

## 4. API ưu tiên P0

### 4.1 Tự động hoàn thành địa điểm

`GET /api/v1/maps/autocomplete?q={query}&limit=5&country=VN`

Yêu cầu:

- `q`: chuỗi đã trim, 2–120 ký tự;
- `limit`: 1–10;
- ưu tiên kết quả tại Việt Nam;
- backend rate-limit và hủy/cache request theo nhu cầu, không lộ khóa nhà cung cấp.

Response:

```json
{
  "data": [
    {
      "id": "place_hanoi",
      "label": "Hà Nội, Việt Nam",
      "primaryText": "Hà Nội",
      "secondaryText": "Việt Nam",
      "center": [105.8342, 21.0278],
      "bbox": [105.28, 20.56, 106.02, 21.39],
      "type": "city"
    }
  ]
}
```

### 4.2 Geocode và reverse geocode

- `GET /api/v1/maps/geocode?placeId={id}`
- `GET /api/v1/maps/reverse-geocode?lng={lng}&lat={lat}`

Response geocode:

```json
{
  "data": {
    "id": "place_hanoi",
    "displayName": "Hà Nội, Việt Nam",
    "center": [105.8342, 21.0278],
    "bbox": [105.28, 20.56, 106.02, 21.39]
  }
}
```

Response reverse geocode:

```json
{
  "data": {
    "displayName": "Ba Đình, Hà Nội",
    "ward": null,
    "district": "Ba Đình",
    "province": "Hà Nội",
    "countryCode": "VN",
    "center": [105.8142, 21.0338]
  }
}
```

Backend phải kiểm tra `lng` trong `[-180, 180]`, `lat` trong `[-90, 90]`.

### 4.3 Thời tiết hiện tại

`GET /api/v1/weather/current?lng={lng}&lat={lat}`

```json
{
  "data": {
    "temperatureC": 28.4,
    "weatherCode": "partly_cloudy",
    "label": "Có mây",
    "observedAt": "2026-09-30T06:30:00Z",
    "source": "provider-name"
  }
}
```

Khi endpoint này hoạt động, frontend sẽ thay thẻ dữ liệu mẫu bằng dữ liệu theo tâm bản đồ hoặc địa điểm đang chọn. Backend nên cache theo ô tọa độ và thời gian để tránh gọi nhà cung cấp quá mức.

## 5. API lớp dữ liệu đô thị

Các endpoint frontend đã dành sẵn:

| Layer ID phía frontend | Endpoint | Kiểu dữ liệu gợi ý |
| --- | --- | --- |
| `population` | `/api/v1/urban/population` | polygon/grid, `population`, `densityPerKm2` |
| `public-facilities` | `/api/v1/urban/facilities` | point/polygon, `facilityType`, `name` |
| `traffic` | `/api/v1/urban/traffic` | line, `speedKph`, `congestionLevel` |
| `rain` | `/api/v1/urban/rain` | grid/polygon, `rainfallMm` |
| `flood` | `/api/v1/urban/flood` | polygon, `depthM`, `riskLevel` |
| `planning` | `/api/v1/urban/planning` | polygon, `landUseCode`, `planName` |
| `land-price` | `/api/v1/urban/land-price` | polygon/point, `priceVndPerM2` |
| `road-density` | `/api/v1/urban/road-density` | polygon/grid, `kmPerKm2` |
| `green-area` | `/api/v1/urban/green-area` | polygon, `areaM2`, `category` |

Query chung cho bản MVP:

`GET /api/v1/urban/{dataset}?bbox={minLng},{minLat},{maxLng},{maxLat}&zoom={zoom}&from={iso}&to={iso}&limit={n}`

- `bbox` bắt buộc và phải có giới hạn diện tích theo mức zoom;
- `zoom` cho phép backend chọn độ chi tiết;
- `from`/`to` chỉ áp dụng cho dữ liệu có thời gian;
- `limit` có giới hạn cứng và response phải báo khi dữ liệu bị cắt.

Response GeoJSON:

```json
{
  "data": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "id": "feature-123",
        "geometry": {
          "type": "Point",
          "coordinates": [105.8342, 21.0278]
        },
        "properties": {
          "name": "Ví dụ",
          "value": 42
        }
      }
    ]
  },
  "meta": {
    "layerId": "public-facilities",
    "generatedAt": "2026-09-30T06:30:00Z",
    "source": "source-name",
    "crs": "EPSG:4326",
    "truncated": false
  }
}
```

Với dữ liệu lớn, nên bổ sung vector tiles thay vì gửi GeoJSON lớn:

`GET /api/v1/urban/{dataset}/tiles/{z}/{x}/{y}.pbf?from={iso}&to={iso}`

Backend cần công bố tên source-layer và schema `properties` ổn định cho từng dataset trước khi frontend bật layer tương ứng.

## 6. Khoảng thời gian frontend gửi

Các giá trị UI hiện dùng:

| Giá trị | Ý nghĩa |
| --- | --- |
| `30m` | 30 phút gần nhất |
| `1h` | 1 giờ gần nhất |
| `1d` | 1 ngày gần nhất |
| `1w` | 1 tuần gần nhất |
| `1mo` | 1 tháng gần nhất |
| `3mo` | 3 tháng gần nhất |
| `6mo` | 6 tháng gần nhất |
| `1y` | 1 năm gần nhất |

Frontend có thể chuyển các giá trị này thành `from`/`to` ISO 8601; backend không nên phụ thuộc vào múi giờ của trình duyệt. Nếu backend muốn nhận trực tiếp `range`, cần thống nhất lại trước khi triển khai.

## 7. CORS, xác thực và vận hành

- Cho phép đúng origin của frontend trong môi trường local/staging/production; không dùng `*` khi gửi credential.
- Validate toàn bộ query và GeoJSON ở biên API; giới hạn số đỉnh polygon, độ dài chuỗi và kích thước payload.
- Áp rate limit riêng cho autocomplete, geocoding và dịch vụ bên thứ ba.
- Không ghi log khóa API, cookie, authorization header hoặc tọa độ định vị chính xác nếu không cần thiết.
- Trả `requestId` để frontend có thể hiển thị mã hỗ trợ khi lỗi.
- Nếu cần đăng nhập, ưu tiên cookie `HttpOnly`, `Secure`, `SameSite` phù hợp; frontend hiện chưa có luồng xác thực.

## 8. Thứ tự tích hợp đề xuất

1. Hoàn thiện autocomplete + geocode + reverse geocode để thay lịch sử mẫu và điều khiển camera.
2. Kết nối weather current để thay thế giá trị placeholder cục bộ.
3. Chọn một dataset nhỏ (khuyến nghị `public-facilities`) làm đường tích hợp mẫu end-to-end.
4. Chốt schema và vector-tile strategy cho traffic, rain, flood, population và land price.
5. Cung cấp planning basemap/layer rồi mới mở lựa chọn `Quy hoạch`.

Khi tích hợp, frontend cần thêm trạng thái loading/empty/error, hủy request cũ khi bản đồ di chuyển nhanh, debounce tìm kiếm và xác thực response trước khi đưa dữ liệu vào MapLibre.

## 9. Điểm kiểm tra để backend tự xác nhận

- `GET /health` vẫn trả `{"status":"ok"}`.
- Mỗi endpoint có OpenAPI schema và ví dụ response.
- Autocomplete không trả quá 10 mục và không lộ khóa nhà cung cấp.
- Layer endpoint bắt buộc `bbox`, có giới hạn kích thước, và không trả payload toàn quốc không giới hạn.
- GeoJSON dùng đúng `[longitude, latitude]` và `EPSG:4326`.
- CORS cho phép frontend local tại URL cấu hình thực tế.
- Lỗi có cùng envelope và `requestId`.

## 10. Tệp frontend liên quan

- `frontend/src/services/api.ts`: base URL và danh sách endpoint đã dành sẵn.
- `frontend/src/features/map/layers/layerRegistry.ts`: ID, trạng thái và thứ tự các layer.
- `frontend/src/features/map/components/SearchBox.tsx`: shell tìm kiếm/lịch sử cục bộ.
- `frontend/src/features/map/components/AreaWeatherCard.tsx`: thẻ khu vực/thời tiết mẫu.
- `frontend/src/features/map/components/PlaceDetailsPanel.tsx`: drawer chi tiết địa điểm bên trái.
- `frontend/src/features/map/components/LayerPanel.tsx`: bật/tắt/độ mờ của layer.
- `frontend/src/features/map/components/UrbanMap.tsx`: ranh giới tích hợp nguồn/layer MapLibre.
- `frontend/src/features/map/config/maplibreWorker.ts`: URL worker do Vite đóng gói, không phụ thuộc đường dẫn worker mặc định.
- `frontend/src/features/map/hooks/useMapWorkspace.ts`: state điều phối search, selection, drawer, time range và 2D/3D.
- `frontend/src/features/map/motion.ts`: đăng ký GSAP React và chính sách reduced motion.

Sau khi backend triển khai một endpoint, chỉ bật control tương ứng khi frontend đã xử lý đủ loading, empty, error và cleanup source/layer.
