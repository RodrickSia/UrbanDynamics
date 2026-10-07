# Báo cáo kiểm thử integrated simulation và ETL

Ngày **07/10/2026**. Phạm vi bàn giao: simulation nhiều tác động, các module building hiện có và ETL TP.HCM mở rộng. Người dùng chọn **chung cư tại Thủ Đức**, hoãn AI giải thích và yêu cầu gộp simulation với ETL trên branch `feat/khoi-flood-land-price`.

## Kết quả bản code cuối

| Kiểm tra | Kết quả | Bằng chứng local |
|---|---|---|
| Toàn bộ pytest trên Windows, Python 3.13.15 | **115/115 đạt**, 137,80 giây | `test-results/integrated-windows-tests.log`, `integrated-windows.xml` |
| Toàn bộ pytest trong Docker Linux, Python 3.12 | **115/115 đạt**, 91,03 giây | `test-results/integrated-linux-tests.log`, `khoi-linux.xml` |
| Build Docker backend/ETL và image kiểm thử | **Đạt** | `test-results/integrated-local-report.json` và build logs |
| API Docker với SUMO/SWMM thực | **Đạt** | `test-results/integrated-demo.json` |
| Lưu/mở lại snapshot từ PostGIS, context trước/sau/gợi ý giống nhau | **Đạt** | `storage_roundtrip=true`, `context_frozen=true` trong local report |
| ZIP input/output native và snapshot | **Đạt**, 474.844 bytes trong lượt smoke | `test-results/integrated-demo.zip` |
| Giao diện Edge headless, API Docker thực | **9/9 nhóm đạt** | `test-results/integrated-ui-report.json` |
| Desktop/mobile | Đã xem ảnh; mobile 390 px không tràn ngang | `test-results/integrated-desktop.png`, `integrated-mobile.png` |
| Whitespace Git | `git diff --check` đạt | Không có lỗi; có thông báo LF/CRLF của Git Windows |

Lệnh chạy lại, từ root repo sau khi cài dependency và cấu hình mật khẩu local:

```powershell
& .venv/Scripts/python.exe scripts/test-integrated-local.py --linux-checks
$env:INTEGRATED_API_URL = 'http://127.0.0.1:8001'
node scripts/test-integrated-ui.cjs
```

Script browser cần Playwright Core tại `.runtime/ui-check/node_modules/playwright-core` và Microsoft Edge. JUnit/log/cache/runtime chứa bằng chứng local, bị gitignore. Hai lượt pytest có warning dependency (24 Windows, 2 Linux), không có test thất bại.

### Nội dung kiểm tra

- Hình học hợp lệ, diện tích bề mặt cân bằng, không đếm trùng tán cây; tách cư dân khỏi nhân viên/khách/người dùng dịch vụ.
- Bảo toàn tổng lịch ngày, ledger nước tái dùng/nước thải, điện kWh và tải kW; kiểm tra tải tăng tại cùng giờ.
- SUMO chạy binary thật, kiểm tra số xe xuất phát/hoàn thành; cùng seed tái hiện, khác seed thay route. SWMM chạy worker riêng, kiểm tra continuity và lưu input/output.
- Gợi ý giữ nguyên building và công suất, chạy lại module trên context đóng băng; tuân thủ ngân sách/khóa thiết kế, báo phương án chưa đạt khi cần. Screening runoff giảm không tự làm mục tiêu tràn nút SWMM đạt.
- Snapshot append-only, mở lại/ZIP, lỗi native trả 503; không tạo kết quả thay thế giả khi solver lỗi. Đọc cache ETL và hash từ cùng một bộ bytes khi ETL cập nhật đồng thời.
- API/ETL giá đất, mưa lưới, ngập và persistence trong bộ regression chung. Chi tiết khảo sát dữ liệu thật: [báo cáo ETL](khoi-citywide-test-report.md).
- Browser: preset, dự tính 22 chỉ số, gợi ý/đổi phương án, mở lại/ZIP, sửa plan ẩn kết quả cũ, JSON lỗi, vẽ footprint/cân bằng diện tích, phân tách dân cư, mobile và không có lỗi JavaScript.

## Ví dụ kết quả mô phỏng

Khu đất **12.095,93 m²**; 200 căn, 600 cư dân, 12 tầng, cao 36 m; base rain **60 mm/1 giờ**. Library `thu-duc-demo-library-1.1`, model `integrated-building-1.1`. Hiện trạng mặc định là khu đất trống tổng hợp.

| Chỉ số | Building plan đề xuất | Ứng viên combined |
|---|---:|---:|
| Căn hộ / cư dân | 200 / 600 | 200 / 600 |
| Xanh mặt đất | 20,00% | 26,20% |
| Bề mặt không thấm | 70,00% | 57,60% |
| Nước cấp | 78,52 m³/ngày | 61,60 m³/ngày |
| Nước thải | 58,94 m³/ngày | 44,21 m³/ngày |
| Điện năng | 2.890,66 kWh/ngày | 2.379,73 kWh/ngày |
| Cao điểm điện | 328,97 kW | 195,97 kW |
| Runoff chưa giữ lại, screening | 492,06 m³/trận | 240,31 m³/trận |
| Tràn nút SWMM, tích phân mẫu 5 phút | 110,46 m³ | 0,00 m³ |
| Chậm trễ SUMO của chuyến hoàn thành | 15,90 giây | 15,90 giây |
| Hàng chờ tối đa | 23,62 m | 23,62 m |
| Xe chưa hoàn thành / chưa xuất phát | 0 / 0 | 0 / 0 |

Combined chuyển 1.500 m² sân cứng thành xanh/thấm, thêm bể 200 m³, áp dụng thiết bị tiết kiệm và đổi lịch vận hành/sạc EV. Chi phí tổng hợp khoảng **4,77 tỷ đồng**, đạt 8/8 mục tiêu của kịch bản này. **Giao thông không cải thiện trong ví dụ** dù lịch vận hành được giãn. Landscape riêng giảm tràn nhưng tăng nước tưới: nước cấp từ 78,52 lên 80,02 m³/ngày. Đây là đánh đổi hệ thống phải hiển thị.

Các số trên từ API smoke với preset có diện tích chính xác; lượt browser có thể chênh nhẹ do form làm tròn diện tích tới 0,01 m².

## Giới hạn và bàn giao

SUMO/SWMM thực đang chạy trên mạng đường/cống, nhu cầu, năng lực, chi phí và mục tiêu **tổng hợp**. Kiểm thử phần mềm đạt không chứng minh độ chính xác ngập/giao thông tại Thủ Đức. Tràn nút SWMM không phải độ sâu ngập 2D; bóng đổ không phải nhiệt độ; giá đường gần không tự áp dụng cho khu đất.

AI giải thích hoãn theo người dùng. SOLWEIG/EPANET/EnergyPlus/flood 2D và mô hình parking/network layout chuyên sâu chưa triển khai. Xem [hướng dẫn và giới hạn](integrated-building-impact.md).

Deploy 156 đã có [workflow/hướng dẫn](integrated-deployment.md), **chưa deploy** vì chưa có runner và `.env`. Kết quả ở bảng trên là local; trạng thái GitHub Actions được báo riêng sau khi push, không suy ra từ test Linux local.
