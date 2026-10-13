# Thử nghiệm đếm xe trên server 152

Ngày kiểm tra: 11/10/2026. Thư mục độc lập:

```text
/GuestShare_NAS/WorkingSpace/Personal/nguyenmv/MLAI/traffic-counting-test
```

## Kết luận

**Dùng pretrained được và là phương án hiện đã chạy thành công.** Không cần
train thêm để trình diễn pipeline phát hiện → tracking → đếm qua vạch → CSV.
Checkpoint YOLOv8m đã huấn luyện trên VisDrone nhận diện xe máy trong các mẫu
drone tốt hơn YOLO11m phổ thông trong lần thử này.

UIT-ADrone phù hợp để trình diễn các mẫu có xe máy, ô tô, xe buýt và xe tải tại
TP.HCM. Tuy nhiên, cần sửa lỗi đếm trùng và kiểm chứng counting trước khi dùng
counts làm đầu vào hiệu chỉnh SUMO. Các lượt dưới đây là **kết quả model**, chưa
phải số xe thực đã được xác nhận đầy đủ.

## 1. Dữ liệu đã tải và phạm vi

Nguồn chính thức: [UIT-ADrone](https://uit-together.github.io/datasets/UIT-ADrone/),
công bố năm 2023. Bộ đầy đủ được giới thiệu gồm 51 video, khoảng 6,5 giờ, tại hai
vòng xoay trong ĐHQG TP.HCM và một vòng xoay công cộng.

Đã tải ba snippet `50m_90d_morning_congkhuA_{16,22,31}_3_0.mp4`:

| Mẫu | Dung lượng thực | Kích thước | FPS | Thời gian |
|---|---:|---|---:|---:|
| `16_3` | 103.169.298 byte | 1920 × 1080 | 30 | 16,667 giây |
| `22_3` | 75.717.220 byte | 1920 × 1080 | 30 | 16,667 giây |
| `31_3` | 70.777.957 byte | 1920 × 1080 | 30 | 16,667 giây |

Mỗi snippet có 500 frame. Đây là ba recording/góc nhìn của cảnh cổng khu A;
không phải dữ liệu của ba tuyến đường độc lập và không phủ toàn thành phố.
Chưa xác nhận thời điểm quay cụ thể hoặc road/edge OSM. Dữ liệu lịch sử này
không đại diện lưu lượng hiện tại quanh building plan của người dùng.

Ngoài ra đã tải `train.json`, `test.json`, hai video `DJI_0065.MP4`,
`DJI_0148.MP4` và một JPEG gốc để khảo sát nhãn/fine-tune tùy chọn. Không tải
toàn bộ 51 video. Các file và SHA256 được ghi trong manifest ở `inputs/`.

### Nhãn

- Train: 59.186 ảnh, 495.992 annotations.
- Test: 84.265 ảnh, 1.075.777 annotations.
- Tám nhóm: bus, car, bike, ped, motorbike, truck, tricycle, van.
- Không có track ID để xác định counting ground truth trực tiếp.
- File tải về có image ID bắt đầu từ 0, nhưng annotation image ID bắt đầu từ 1.
  Offset `-1` loại bỏ các tham chiếu ngoài phạm vi và được đối chiếu trực quan
  trên một số frame gốc. File nguồn không bị sửa; script evaluation nhận offset
  rõ ràng. Chưa kiểm tra trực quan mọi nhãn trong dataset.

## 2. Model và pipeline thực tế

Model dùng cho demo:
[dronefreak/visdrone-yolov8m](https://huggingface.co/dronefreak/visdrone-yolov8m).

```text
revision: 4f6719c7f097afd19419b19eb6f8f79151b77884
SHA256: dcee38b5e609df15c1e4e7bfda19cf5b84009bbcb4011b598d3d87ea38cf1730
checkpoint: 52.106.834 byte
```

Không train thêm checkpoint này. Model class `motor` được chuẩn hóa thành
`motorcycle`; không tính người ngồi trên xe thành một phương tiện khác.

Pipeline: YOLO → BoT-SORT (có GMC) → tâm bounding box qua đoạn vạch hữu hạn →
đếm theo hướng/loại → tổng hợp thời gian. Vạch và ROI cấu hình riêng theo góc
camera. Cơ chế deadband và chống đếm lặp theo ID/hướng có sẵn, nhưng không
giải quyết mọi trường hợp cùng một xe được gán nhiều ID.

Môi trường: RTX 3090 Ti, PyTorch 2.8.0 CUDA 12.6, Ultralytics 8.3.221;
chi tiết tại `outputs/environment.json`. Tốc độ xử lý cả tracking/ghi video
khoảng 7,8–9,4 frame/giây, **chưa đạt realtime 30 FPS** ở cấu hình thử này.

Thử YOLO11m phổ thông trước đó nhận diện xe máy kém. Một lần thử fine-tune
YOLO11s bị dừng bởi `Illegal instruction` ở runtime Polars trên CPU cũ, trước
khi có checkpoint thành công. Đã cài runtime tương thích vào venv; không chạy
lại training vì checkpoint drone có sẵn đã chạy được. Không có kết quả
fine-tune nào được dùng cho các số liệu dưới đây.

## 3. Kết quả ba clip

| Mẫu | Xe máy | Ô tô | Xe buýt | Xe tải | Tổng lượt model đếm |
|---|---:|---:|---:|---:|---:|
| `16_3` | 15 | 2 | 1 | 0 | 18 |
| `22_3` | 13 | 1 | 1 | 0 | 15 |
| `31_3` | 7 | 1 | 0 | 1 | 9 |

Đây là lượt qua vạch trong 16,667 giây, không phải tổng số xe trong toàn cảnh.
CSV có hướng đi và thời điểm của từng sự kiện. Trường vehicles/hour chỉ là
ngoại suy từ cửa sổ ngắn, được gắn nhãn rõ; không phải quan sát cả giờ.

### Đối chiếu nhãn detection

So sánh bounding box tracking với nhãn tải về, matching cùng nhóm xe tại
IoU ≥ 0,5, chỉ tính box nằm trọn ROI:

| Mẫu | Frame có nhãn đối chiếu | Precision xe máy | Recall xe máy |
|---|---:|---:|---:|
| `16_3` | 100 | 87,7% | 88,3% |
| `22_3` | 0 trong file test đã đối chiếu | Chưa tính | Chưa tính |
| `31_3` | 80 | 78,9% | 96,1% |

Các frame liên tiếp có tương quan. Đây không phải mAP chính thức, không phải
độ chính xác counting, không phải phép đánh giá độc lập trên toàn dataset.
Không lấy số lượng frame video làm số lượng frame có nhãn. Chi tiết TP/FP/FN
theo loại xe và hai ngưỡng IoU ở `visdrone-pretrained/detection-check.json`.

### Kiểm tra hình gốc

Trong `22_3`, có thể đối chiếu các sự kiện rõ để trình diễn:

- Xe máy qua vạch khoảng 0,67 giây.
- Xe buýt qua vạch khoảng 4,53 giây.
- Ô tô đỏ qua vạch khoảng 11,34 giây.

Đây là kiểm tra một số sự kiện nhìn thấy trên filmstrip gốc, chưa phải
annotation đầy đủ mọi xe. Trong `16_3`, một ô tô đen xuất hiện thành hai
sự kiện ID 8/11 tại khoảng 1,83 giây. **Có đếm trùng**, nên tổng 18 lượt không
được công bố như ground truth. Cần kiểm tra các sự kiện bỏ sót/đếm nhầm khác.

## 4. Kiểm thử và sản phẩm bàn giao

- Logic đếm: **4/4 test đạt trên Windows**, **4/4 trên server Linux**.
  Kiểm tra vạch hữu hạn, hướng, deadband, chống lặp ID, mất tracking,
  tổng hợp bin và thời gian của bin cuối.
- Ba clip đã chạy đủ 500 frame bằng GPU và tạo artifact.
- `verify_outputs.py` kiểm tra số events = tổng bins = tổng summary,
  thời điểm nằm trong cửa sổ quan sát, số frame tracks/video/summary bằng nhau,
  video demo có codec H.264. Test này không đo độ chính xác nhận diện.

Trong thư mục server:

```text
scripts/                         scripts chạy lại và README
configs/                         ROI, vạch, model, tracker
inputs/                          video, nhãn và source manifests
models/                          checkpoint tải sẵn và manifest revision
outputs/index.html               trang xem ba clip và tải CSV
outputs/visdrone-pretrained/      ba kết quả + detection-check.json
outputs/core-tests.xml           kết quả test logic
outputs/dataset-index-audit.json  bằng chứng offset nhãn
logs/                            log inference, evaluation, training thử
training-subset/                  dữ liệu chuẩn bị tùy chọn, không dùng demo
```

Hướng dẫn chạy lại: [README](../scripts/traffic-counting/README.md).
Chọn `--run-name` mới để giữ nguyên kết quả cũ. Không commit/push trong lần này.

## 5. Bước tiếp theo

1. Giữ pretrained cho demo, xử lý box trùng/ID trùng và chọn vạch trên lòng
   đường; cần ổn định ảnh hoặc dùng camera cố định để tránh xe đứng yên bị
   tính qua vạch do drone dịch chuyển. GMC của tracker không tự ổn định vạch.
2. Gán nhãn counting thủ công một tập clip có đủ hai hướng, kiểm tra missed
   crossings và false crossings riêng. Chỉ công bố sai số sau bước này.
3. Thử camera cố định có góc nhìn phù hợp ở nơi triển khai. Chỉ fine-tune khi
   sai số detection trên dữ liệu mục tiêu vẫn lớn sau khi chỉnh pipeline.
4. Muốn hiệu chỉnh SUMO: bổ sung road/edge mapping, thời điểm quay, cửa sổ
   quan sát đủ dài, thành phần xe và kiểm chứng counts. `simulation_ready`
   hiện vẫn false, không tự biến clip lịch sử thành lưu lượng nền của dự án.

Model card nêu giới hạn phi thương mại của dữ liệu VisDrone; quyền phân phối/
sử dụng thương mại UIT-ADrone chưa được xác nhận. Demo kỹ thuật này không
xác lập quyền đóng gói các nguồn đó trong sản phẩm thương mại.
