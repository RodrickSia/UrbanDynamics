# Báo cáo kiểm thử local phần Khôi

Đợt rà soát trước khi push bắt đầu **04/10/2026 23:14:37 (UTC+7)**. Kết quả tổng hợp **PASS**. Kết quả và thời gian từng bước nằm trong `test-results/khoi-local-report.json`. Đây chưa phải nghiệm thu đủ mọi tính năng MVP trong `plan.md`.

## Môi trường

- Windows, Python 3.13.15 trong `.venv`; Python và Docker đã thêm vào User PATH.
- Docker Desktop 4.93.0, Docker CLI 29.8.1, Compose 5.5.1; engine WSL2 đã chạy được container.
- Stack riêng `khoi-local`: PostGIS 16/3.5 tại `127.0.0.1:55432`, FastAPI tại `127.0.0.1:8001`.
- Backend được build lại từ mã hiện tại. ETL chạy Python local và ghi vào PostGIS thật; kiểm tra HTTP gọi backend trong Docker.

## Kết quả

**36 tests passed trên Windows/Python 3.13 và 36 tests passed trên Linux/Python 3.12**, đều dùng PostGIS thật, không bỏ qua test database. Windows có 7 cảnh báo, Linux có 2 cảnh báo từ thư viện phụ thuộc. `git diff --check` không phát hiện lỗi whitespace.

Test bao gồm đổi CRS, lọc bằng geometry, ngày ISO, dữ liệu độ sâu sai, ID trùng của nguồn, ngưỡng mưa, lịch sử sau thời điểm dự báo, khoảng giờ thiếu, cửa sổ 24 giờ, hết hạn dự báo, bán kính theo mét, mask/nodata raster, đổi đơn vị giá đất và yêu cầu duyệt, tách hàng theo grid scan, tiếp nối trang, giá trọn đường, truy vấn API, database mất kết nối, snapshot giá đất hỏng, giới hạn kết quả, kịch bản mưa, rollback PostGIS và hai lớp ghi đồng thời.

Các pipeline ngập lịch sử, nguy cơ và bảng giá đất đã chạy với nguồn thật. Bộ test Linux chạy trong Docker riêng để kiểm tra môi trường sạch tương ứng Python của CI. JUnit riêng cho hai môi trường được lưu trong `test-results/`.

Đã build thành công image backend, ETL, frontend và image kiểm thử. Parser đã đọc PDF thật trong Linux, cũng tạo 195 hàng và 1 feature demo; kết quả giống Windows. Build frontend chỉ kiểm tra đóng gói scaffold hiện tại, chưa nghiệm thu giao diện bản đồ. Lần xác nhận cuối dùng cache nguồn, không tải lại ảnh vệ tinh hoặc mưa.

Cả 9 lượt smoke test HTTP ở đợt kiểm tra dữ liệu thật đều trả **200**: health, ready, danh mục lớp, ngập lịch sử, nguy cơ, giá đất, hàng giá đất, vệ tinh và POST kịch bản mưa 60 mm/3 giờ. Đây không phải benchmark tải đồng thời.

| Dữ liệu thật | Kết quả xử lý | Giới hạn |
|---|---|---|
| DataSuds ngập TP.HCM | 425 quan sát nguồn; **131** nằm trong ranh giới demo Thủ Đức | Độ chính xác vị trí theo nguồn; không suy ra mọi nơi chưa có điểm là an toàn. |
| Open-Meteo | Lịch sử 2016–2025 gồm **87.672** giờ; dự báo mẫu tại một điểm lưới | Chưa có lưới đầy đủ từ pipeline của Duy. |
| Nguy cơ ngập | **131** vùng lân cận và bộ căn cứ | Cảnh báo theo quy tắc; không dự đoán độ sâu hoặc xác suất đã hiệu chỉnh. |
| GFM ảnh 01/10/2026 | Raster thật xử lý thành công; **0** pixel ngập dương tính trong vùng cắt | Không có exclusion mask riêng trong item; số pixel có thể đánh giá là unknown. Không kết luận cả vùng khô. Lần harness cuối dùng lại snapshot này. |
| Phụ lục giá đất 2026 | **195** hàng ứng viên trích từ phần An Khánh; 7 mục bị từ chối/cần xem lại | Đã sửa ghép hàng và bổ sung giá trọn đường. Một số chữ bị watermark/OCR sai vẫn cần duyệt. Không phải 195 hàng đã xác minh. |
| Đường OpenStreetMap | **9.083** ways; **118** ứng viên ghép hàng giá đất | Các ứng viên chưa tự động được duyệt đúng hai đầu đoạn. |
| Lớp giá đất công bố | **1 feature** Trần Não, hai phần hình học carriageway đã đối chiếu bên trong khoảng giá | Có cờ `partial_published_segment`; chưa phủ toàn khoảng giá và chưa đạt mục tiêu 25 đoạn demo. |

## Các lỗi đã sửa qua kiểm thử

- ID `Obs_239` lặp ở nguồn nhưng là hai quan sát khác nhau: giữ cả hai bằng ID có hậu tố và lưu ID nguồn.
- Ghi hai lớp PostGIS đồng thời gây deadlock khi tạo schema: tách transaction bootstrap, khóa schema riêng rồi khóa theo lớp khi ghi. Test chạy với database thật.
- Item GFM thiếu exclusion mask: dùng ensemble đã được nhà cung cấp xử lý, giữ unknown cho vùng không đánh giá được; không chuyển vùng thiếu dữ liệu thành khô.
- Ngưỡng mưa được tính lặp theo từng điểm: cache theo station/tháng trong mỗi lượt đánh giá, đồng thời giới hạn 24 giờ tới và thêm metadata hết hạn.
- Lỗi dấu ngoặc trong script kiểm thử: đã sửa và chạy lại thành công toàn bộ harness.
- Parser phụ lục: thay đoán hàng theo tâm giá bằng đường kẻ raster, xử lý tiếp nối qua trang và giá “trọn đường”. Các hàng chưa kiểm chứng vẫn giữ cờ review.
- Linux `python:3.12-slim` thiếu `libexpat.so.1` khiến Rasterio không import được: bổ sung `libexpat1` trong Dockerfile ETL và image test, sau đó test Linux đạt 36/36.
- Workflow build trên checkout sạch: tạo `.env` từ `.env.example` trước khi chạy Compose. Chưa chạy workflow trên GitHub thực tế.
- API trả 503 khi database hoặc snapshot lỗi; không trả chi tiết chuỗi kết nối.
- Khi dùng tệp nguồn trong cache, vẫn ghi checksum vào metadata để truy vết.

## Phần còn lại để nghiệm thu demo

1. Tiếp tục đối chiếu PDF và duyệt ít nhất 25 đoạn đường giá đất; sửa chữ bị OCR sai. Demo hiện chỉ có một feature có độ bao phủ một phần, chưa phải heatmap giá đất đầy đủ.
2. Nhận lưới mưa và lịch sử tương ứng từ Duy; cập nhật dự báo mới trước khi trình diễn. API hiện giữ snapshot và đánh dấu hết hạn.
3. Frontend thêm các lớp bản đồ, popup nguồn, bộ lọc thời gian và nhãn kịch bản. Tích hợp AI Club qua backend để giải thích các bằng chứng; chưa có mô hình AI trong phần Khôi này.
4. Ghép scheduler và cấu hình deploy máy 156. Workflow mới chỉ kiểm thử CI; chưa chạy trên GitHub và chưa deploy máy 156.

## Xem lại kết quả

- Swagger đang chạy: `http://127.0.0.1:8001/docs`.
- Kết quả máy đọc: `test-results/khoi-local-report.json`.
- JUnit: `test-results/khoi-local.xml`, `test-results/khoi-linux.xml`; log: `test-results/pytest.log`, `test-results/linux-pytest.log` và log từng pipeline.
- Hướng dẫn chạy lại, nguồn và hợp đồng bàn giao: [khoi-implementation.md](khoi-implementation.md).

Dữ liệu gốc, geometry OSM lớn và snapshot nằm trong `data/`; `.env`, `.venv`, `test-results` cũng được Git bỏ qua. Mẫu geometry đã duyệt nhỏ trong `docs/samples/land-price-tran-nao-reviewed.geojson` được đưa vào repo cùng attribution để nhóm tái tạo demo.

## Đưa lên GitHub

Branch bàn giao: `feat/khoi-flood-land-price`. Đã ghép cập nhật `origin/main` về các service ETL dân số/mưa và cấu hình uv; thêm dependencies Khôi vào `pyproject.toml`/`uv.lock`, giữ `requirements.txt` cho Docker và bộ test pip. Các thay đổi dùng chung cần review: `compose.yaml`, Dockerfile backend/ETL, requirements và `.github/workflows/ci.yaml`. Không có bước deploy tự động được thêm vào workflow mới. Kiểm thử trong báo cáo là kiểm thử local; chưa deploy máy 156.

## Sửa cấu hình password — 05/10/2026

- Bỏ password mặc định trong script local; thiếu `POSTGRES_PASSWORD` thì dừng trước khi gọi Docker.
- CI sinh password ngẫu nhiên bằng OpenSSL, che trong log và dùng cùng giá trị cho PostGIS/chuỗi kết nối; container được dọn sau test.
- Đã chạy chính shell khởi động database của workflow trên máy và đạt 36/36 test với database tạm. Đây là kiểm thử local, không phải kết quả GitHub Actions.
- Đã đổi password của database test local, lưu riêng trong `.runtime/khoi-local.env` được Git bỏ qua; harness và cả 9 lượt kiểm tra API đều đạt với password mới.
- Commit cũ vẫn có giá trị test trước đây trong lịch sử; không force-push hoặc sửa lịch sử branch nhóm. Cảnh báo GitGuardian ở commit cũ cần được người có quyền xử lý riêng.
