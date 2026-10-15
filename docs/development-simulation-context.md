# Development simulation: nền dữ liệu, OSM cục bộ và Before/After

Branch: `feat/development-simulation-context`, tách từ main `fe69437`.

## Xem bản web riêng

- Trên máy đang chạy tunnel: **http://127.0.0.1:8192**.
- Dịch vụ web trên server 156: loopback **51875**; API riêng **8022**.
- Nếu tunnel bị ngắt: `node scripts/start-development-tunnel.cjs`.
- Mở **Plans** → **Simulation context demo · Thu Duc parcel 1937203** → **Development** → chọn **Apartment proposal · 4 floors**.
- Simulation nằm trong Development. Chọn **Quick estimate** hoặc **Detailed · SUMO + SWMM**, rồi **Run simulation**.
- Để xem case native đã chạy sẵn, chọn **View last completed run**. Không cần chạy lại solver; nút này chỉ mở lịch sử cùng revision và scope. Kết quả dùng các giả định đã lưu của lần chạy, không áp các thay đổi control chưa chạy.
- Bản main và bản agent preview cũ chạy riêng, không bị thay thế.

## 1. Hiện trạng bề mặt và phạm vi cải tạo

Trước đây hiện trạng được gán 0% cây xanh, nhưng phương án mặc định thêm 30% xanh. Vì vậy ngay cả khi không sửa tòa nhà, kết quả vẫn có thể cho lợi ích về runoff và tăng nước tưới.

Bây giờ mặc định **Keep existing landscape outside buildings**:

1. Tìm snapshot đã cài phủ toàn phạm vi đánh giá.
2. Nếu có: lấy vùng xanh OSM và lớp phủ ESA WorldCover 2021; trừ footprint mái nhà trước khi tính diện tích mặt đất.
3. Pixel built-up chỉ là proxy cho phần lát, không được coi là đo đạc độ không thấm.
4. Phần chưa phân loại dùng một giả định được ghi nhãn: **40% xanh / 50% lát / 10% thấm**.
5. Tính mặt đất theo footprint của từng trạng thái nhưng dùng cùng nguồn và quy tắc. Không đổi footprint thì không tự đổi cảnh quan.

Muốn cải tạo cảnh quan, mở **Assumptions** → **Landscape** → **Redesign all open ground in this scope**, rồi nhập tỷ lệ xanh. Với **Whole scenario**, việc cải tạo này áp dụng cho đất trống của toàn vùng nghiên cứu, không chỉ chân tòa nhà.

Inventory vẫn lấy generated buildings và Goong map context mà main cung cấp. Chiều cao, số tầng và cư dân có thể là ước tính; thiếu footprint không chứng minh đất trống. Thiết kế đề xuất vẫn là danh sách công trình cuối cùng của scope theo quy ước Development hiện có.

## 2. Mạng OSM quanh vị trí được chọn

Khi chạy Detailed:

1. Lấy study area và nới ranh giới **750 m** mặc định; có thể chọn 500–1.500 m trong Assumptions.
2. Tìm cache theo bounding box.
3. Nếu chưa có cache, ưu tiên truy vấn phần mạng trong kho nhóm `transport.sumo_edge`/`sumo_junction` bằng chỉ mục không gian. Đây là mạng dẫn xuất từ OSM đã được nhóm nhập vào kho.
4. Tái dựng graph cục bộ từ hướng cạnh, junction chung, hình học, làn phù hợp ô tô/xe máy và tốc độ. **Không bảo toàn đầy đủ hướng rẽ hạn chế và pha đèn của network gốc**; nguồn này được ghi rõ là local reconstruction.
5. Nếu kho không phủ vùng đó: dùng OSM extract đã cài phủ phạm vi; tiếp theo mới tải mạng đường từ Overpass.
6. Lưu snapshot bất biến, kiểm tra SHA-256, dùng chung cho API và worker; tạo network SUMO cục bộ.
7. Nếu không lấy được mạng hoặc không tạo được kết nối hợp lệ, báo lỗi. Không tự thay bằng mạng giả.

Giới hạn để tránh chạy toàn TP: phạm vi tối đa 25 km²; dữ liệu mạng bị giới hạn số way/node và network nhập tối đa 4.000 cạnh có thể lái. Một số vị trí ngoài vùng dữ liệu, thiếu đường OSM hoặc không có access kết nối sẽ chưa chạy được. Đường công cộng từ OSM không xác nhận lối vào hợp pháp của công trình.

### Lưu lượng nền là gì?

- Có reference counting đã cài: dùng profile car/motorcycle của reference ấy. Bản preview dùng chính sách counting demo đã có; không gọi là lưu lượng thực đo tại parcel.
- Chưa có reference: dùng **400 xe/giờ**, gồm 100 ô tô và 300 xe máy, đều các giờ; nhãn **synthetic**.
- Không nhân tổng lưu lượng nền với số đường nội bộ.
- Before và After dùng **cùng network, giờ, seed, lưu lượng và cách chia OD nền**. Chuyến của chương trình công trình được tính riêng rồi cộng vào nền.
- Connector công trình và các pha đèn sinh ra vẫn là giả định. Đây là mô phỏng theo kịch bản, chưa phải dự báo đã hiệu chỉnh cho vị trí thực tế.

Quick estimate không tải network mới qua Internet. Nó tính nhu cầu và tác động sơ bộ; network cục bộ được chuẩn bị khi chạy Detailed. Nếu trước đó chưa có nguồn mặt đất tại vị trí mới, nguồn bổ sung giữa hai lần chạy có thể khác; hãy đọc Data sources của từng kết quả.

## 3. Kết quả trên web

- Bảng **Before / After / Change** hiển thị trực tiếp.
- Khi hiện trạng không đủ để so sánh, Before hoặc Change là **Unknown**, còn nhu cầu phương án vẫn hiện nếu tính được.
- Kết quả native hiển thị delay mọi chuyến hoàn thành, delay xe nền, queue tối đa, số xe hoàn thành/chưa hoàn thành/chưa xuất phát, theo giờ và seed.
- Khi baseline occupancy chưa biết, các giá trị mô hình thay thế chỉ hiện với nhãn **Assumption-based comparison**.
- Nếu xe chưa hoàn thành, không trình bày chênh lệch completed-trip delay thành một cải thiện; ghi **Not comparable**. Vẫn hiện số xe tồn để đánh giá độ lệch mẫu.
- **Data sources and assumptions** hiện nguồn inventory, lớp phủ đất, diện tích chưa phân loại, loại mạng, thời điểm snapshot, lưu lượng nền và phần capacity thiếu.
- Capacity vẫn **Unknown** nếu chưa có dữ liệu; nhu cầu tăng không tự chứng minh hạ tầng quá tải.

## Cách ly triển khai

- Compose project: `urbandynamics-development-preview`.
- Folder server: `/GuestShare_NAS/WorkingSpace/Personal/nguyenmv/MLAI/UrbanDynamics/development-preview`.
- Volume riêng: `development-preview-runtime` trong project, chứa plans SQLite, studies SQLite, OSM context và solver artifacts.
- `ZONING_STORAGE=sqlite` và `PLANNING_SQLITE_PATH` ép ghi vào volume riêng.
- Warehouse dùng `PGOPTIONS=-c default_transaction_read_only=on`; chỉ đọc dữ liệu của nhóm.
- Network preview riêng, không thêm service `backend` vào network production.
- Không dùng API key OpenAI, không gọi AI trả phí cho luồng này.
- `scripts/deploy-development-preview.py` chỉ đóng gói source cần thiết và cài bản preview vào folder nói trên. File môi trường giữ trên server, không commit.

## Chạy local

1. Cần Docker và runtime image `urbandynamics-agent-preview-backend:local` có dependency phù hợp với backend main. Nếu chưa có, build từ `backend/Dockerfile`, đặt `DEV_BACKEND_BASE_IMAGE` về image vừa build.
2. Tạo `.env.development.local`; đặt `VITE_GOONG_MAPTILES_KEY` nếu cần nền Goong. Có thể chỉ định `DEV_SNAPSHOT_DIR`, `DEV_COUNTING_DIR`, `DEV_DATA_DIR`.
3. Chạy `docker compose --env-file .env.development.local -f compose.development-preview.yaml up --build -d`.
4. Web local là **8092**, API **8022**. Nếu không cấu hình warehouse, vẫn có thể thử vùng zoning vẽ tay; dữ liệu nền thiếu được ghi nhãn giả định.

## Kiểm thử và bằng chứng

- Backend: `backend/tests/test_development_simulation_context.py`, cùng regression zoning/native/background/provenance.
- Frontend: `DevelopmentSimulation.test.tsx` và `usePlanSimulation.test.ts`.
- Browser fixture dùng grid tổng hợp để không phụ thuộc Internet; module fixture không được import bởi production.
- `scripts/seed-development-preview.py`: case API thật trên parcel snapshot 1937203; lưu job trước khi chờ hoàn thành. Dùng `--resume` khi chuẩn bị trước đó thất bại; không tự tạo lại job đang chạy/đã hoàn tất.
- Nếu kết nối khi chờ bị ngắt, dùng `--collect` để lấy lại job/kết quả đã có; không tạo run mới.
- `scripts/check-development-preview.cjs`: kiểm tra web thật, Before/After, traffic, nguồn, restore sau reload và viewport mobile.
- Bằng chứng máy chạy nằm trong `test-results/development-context*`; xem báo cáo kết quả đi kèm.

Nguồn API dự phòng: [OSM API và dữ liệu bbox](https://wiki.openstreetmap.org/wiki/API_0.6), [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API). Bản preview không tải toàn TP từ API công cộng cho mỗi lần chạy.
