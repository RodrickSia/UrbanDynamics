# Hoàn thành các nhóm còn thiếu của simulation

Goal: hoàn thành toàn bộ các nhóm đã liệt kê, bao gồm counting trên server 152. Người dùng chọn UIT-ADrone hiện có; không coi video này là camera tại parcel Thủ Đức của snapshot. Triển khai và nghiệm thu trong demo kiểm thử; chưa push hoặc thay production.

## Yêu cầu và bằng chứng nghiệm thu

| Nhóm | Công việc cần hoàn thành | Bằng chứng cần có | Trạng thái |
|---|---|---|---|
| Chọn nhiều đất/kịch bản | Click bật/tắt tối đa 6 parcel; plan từng parcel; so vị trí cùng chương trình; xây đồng thời/từng giai đoạn; lưu/mở lại | Kiểm thử API và UI, native case nhiều parcel thật | Đang triển khai |
| Hiện trạng | Nối footprint/surface/dân số có nguồn; fallback hợp lý cho thiếu occupancy; khử trùng nền trước so sánh | Snapshot, phương pháp/hệ số, gate giả lập/quan trắc, sensitivity | Chưa hoàn thành |
| Quy hoạch | Tra mã đất/chức năng/chỉ tiêu; kiểm tra plan và ghi thiếu dữ liệu; demo có quy hoạch giả lập nếu thiếu | Nguồn, kiểm tra xung đột đất/chỉ tiêu, case pass/fail | Chưa hoàn thành |
| Giao thông | Import OSM vào mạng chung SUMO; route/access đa parcel; counting kiểm chứng, mapping cạnh/time/direction, demand/OD/đèn có nguồn hoặc giả định | Native network/routes, sai số counting, cùng seed/baseline, không áp counts sai địa điểm | Chưa hoàn thành |
| Thoát nước/ngập | Terrain/bề mặt/bối cảnh ngập; mạng/triều có nguồn hoặc giả lập; nối graph SWMM chung, đánh giá sensitivity | Native mass balance, scope, chứng minh không diễn giải tràn nút thành ngập 2D | Chưa hoàn thành |
| Điện/nước/nước thải | Nhu cầu theo hệ số + nền/công suất/vùng phục vụ có nguồn hoặc giả lập; headroom/cumulative | Phương pháp, profile tải, capacity checks và sensitivity | Chưa hoàn thành |
| Trường học | Vị trí/sức chứa/nhu cầu nền và đường đi; capacity allocation theo kịch bản | Không đếm trùng, nền bao phủ, inventory/fallback có nhãn | Chưa hoàn thành |
| Bóng đổ/nhiệt | Công trình/cây lân cận/chiều cao, bóng theo geometry; nhiệt screening được xác định rõ phương pháp/giới hạn | Nguồn/fallback, cùng receiver, không gán proxy bóng đổ thành nhiệt độ đo | Chưa hoàn thành |
| Giá đất/chi phí | Nối giá/phạm vi áp dụng; chi phí xây dựng/hạ tầng và sensitivity; không tự biến bảng giá thành giá thị trường | Nguồn/đơn vị/phạm vi, công thức, null khi không có phạm vi thích hợp | Chưa hoàn thành |
| Demo và bàn giao | Kết quả truy xuất được qua link; map layers/JSON/ZIP; nguồn, giả định, tốt/xấu theo tiêu chí đã khai báo | Regression, native/API/UI, báo cáo case và giới hạn toàn bộ nhóm | Chưa hoàn thành |

Mỗi nhóm cần cả đầu vào và đường tính/so sánh phù hợp. Chỉ lập danh sách thiếu dữ liệu hoặc để unknown không chứng minh hoàn thành nhóm. Dữ liệu giả lập được phép cho demo nhưng phải tách với dữ liệu có nguồn, có căn cứ/hệ số, chạy độ nhạy và không công bố như quan trắc. Việc tính được với giả định không chứng minh mô hình đã hiệu chỉnh hay công trình được phép xây.

## Thứ tự thực hiện

1. Luồng nhiều parcel và kịch bản; ổn định contract trước khi bổ sung nền.
2. Counting UIT-ADrone: xử lý lỗi đếm trùng, kiểm chứng trên mẫu, xuất contract counts/mapping và nối pipeline giao thông mà không chuyển vị trí nguồn.
3. Mạng OSM đa parcel và scenario SUMO; demand/OD có prior hợp lý, sensitivity và provenance.
4. Hiện trạng/quy hoạch, các nhóm hạ tầng/ngập/trường học/bóng-nhiệt/giá-chi phí theo từng hợp đồng dữ liệu.
5. Demo tổng hợp nhiều đất có nguồn, toàn bộ kiểm thử và audit từng requirement trước đánh dấu goal hoàn thành.

## Tiến độ ban đầu

12/10/2026: đã kiểm tra code hiện hành và server 152. API prepare hỗ trợ 6 parcel nhưng click polygon thay lựa chọn; chỉ tạo options riêng từng parcel, chưa có builder cumulative; floor area thay đổi theo footprint. Counting có kết quả pretrained và một lỗi ID trùng đã biết; chưa có counting ground truth đầy đủ, chưa đủ điều kiện calibration. Mạng OSM hiện chưa được dùng trong planning native. Không có quá trình mới nào được khởi chạy trong các turn bị ngắt trước đó theo lịch sử tool; cần kiểm tra trạng thái server trước mỗi lần chạy mới.

## Tiến độ sau triển khai đợt đầu — model 0.16

- **Luồng nhiều parcel:** click bật/tắt giữ các lựa chọn; plan riêng từng parcel; cùng tổng sàn/căn/cư dân khi so vị trí; cumulative và nhóm tùy chọn, tối đa 12 options, tối đa 4 phases. Case 3 parcel có 5 options/3 phases chạy native và mở lại thành công. 5 nhóm UI đạt, bao gồm tùy chọn counting, nhóm tùy chọn và mobile (`test-results/planning-system-osm-counting/ui-report.json`). Chưa phải triển khai frontend chính của nhóm.
- **Giao thông:** native đã nhập mạng OSM chung (805 cạnh công cộng, 6 cạnh private), private access theo junction gần nhất là giả định, phases/OD vẫn chưa quan trắc. Không tự fallback về corridor khi OSM không routable. Case native có counting reference thành công, cân bằng SUMO/SWMM và geometry nguồn được giữ. Job `2e8bf14a-cc47-4011-a0a5-9996d40e1495`, run `20944c97-2edf-4b29-ac02-a52d49e907d5`. [Mở kết quả](http://127.0.0.1:8007/simulation/planning?job=2e8bf14a-cc47-4011-a0a5-9996d40e1495&option=together_3).
- **Counting 152:** thêm script offline ở `scripts/identity-repair-20261012/`, outputs riêng `outputs/identity-repair-20261012/` dưới thư mục thử nghiệm. Windows/Linux 6/6 logic test đạt. Tổng clip 16 sửa từ 18→17 (lỗi ô tô ID8/11); clip22 giữ15, clip31 giữ9. Giữ bản gốc và overlays cũ. Chưa có nhãn crossing độc lập đầy đủ hoặc camera/edge/time mapping; `simulation_ready=false`.
- **Nối counting:** catalog tham chiếu bất biến và kiểm tra SHA; UIT-ADrone dùng làm prior tỷ lệ ô tô/xe máy. Case chọn clip22 có 1 ô tô/13 xe máy, loại bus khỏi prior hai lớp, đỉnh OD **giả định** 800 xe/h cho ra 57 ô tô +743 xe máy tại giờ18. Không chuyển số đếm qua vạch thành quan trắc OD vùng/đường khác. Cần sensitivity và bước xác minh counting tiếp theo để hoàn thành nhóm giao thông.
- **Quy hoạch:** đã freeze thuộc tính parcel/đồ án/quyết định và cảnh báo công năng có khả năng xung đột. Ba parcel case này có nhãn xanh/CTCC/giao thông nên đều cảnh báo, không phát hành compliance pass. Chưa có sub-area polygons/chỉ tiêu mật độ/FAR/tầng cao/khoảng lùi được xác minh.
- **Hiện trạng:** đã fetch thêm 375 polygon ESA WorldCover 2021 10m vào snapshot dẫn xuất `0e62caa68cf5d4a1c9941cd82d59b8d4a09a453170dd09726c322d252bea2fda`. Nguồn/classification lịch sử, không phải survey hiện tại; chưa hoàn thành occupancy và khử trùng dân số.
- **Nguồn server156:** catalog mới xác nhận parcel có `loai_dat_qh`, `do_an`, `quyet_dinh`; rain/flood/land-price có catalog, nhưng không có utility capacity hoặc school enrollment trong catalog này. Báo cáo `test-results/planning-system-osm-counting/server-layer-catalog.json`.
- **Kiểm thử hợp đồng/native:** 21/21 tập tập trung đạt (`test-results/planning-osm-counting-contract.xml`); toàn bộ regression sau thay đổi 0.16 chưa chạy. Báo cáo 114/114 là lịch sử 0.15, không coi là chứng minh hoàn tất 0.16.

Đang phục vụ bằng cập nhật mã vào container demo local, giữ volume. Image `planning-demo-backend:local` cũ chưa rebuild để chứa toàn bộ thay đổi mới; cần build/reproduce cuối cùng trước nghiệm thu. Chưa commit/push/deploy production.

Các nhóm thoát nước/hạ tầng/trường học/bóng-nhiệt/giá-chi phí vẫn chưa hoàn thành. Goal giữ nguyên toàn bộ phạm vi và chưa đạt; không coi các cảnh báo `unknown` hoặc prior transfer này là hoàn thành thiếu dữ liệu.

## Cập nhật model 0.17–0.18

- **WorldCover đã vào phép tính:** snapshot `0e62caa68cf5d4a1c9941cd82d59b8d4a09a453170dd09726c322d252bea2fda` có 375 polygon. Context giữ metadata, pixel SHA và bản tái dựng baseline có SHA/cờ khớp. Case P1 có 1.513,5 m² xanh; P2/P3 có proxy built-up ngoài mái 1.117,5/1.548,5 m². Classification năm 2021 không xác minh độ thấm hoặc vacancy năm 2026. Tiến trình fetch treo sau khi xuất file đã dừng; hash và việc tiêu thụ dữ liệu được xác minh, không fetch lại.
- **Trường học:** graph foot OSM, kiểm tra foot/access/oneway:foot; đường một chiều xe không tự áp cho đi bộ. Tuyến có đoạn nối thẳng ước tính từ tâm parcel/điểm trường đến node, tối đa 300 m mỗi đầu. Đường không kết nối báo unroutable, không fallback spine. Case có 15 tuyến tới 5 điểm trường; khoảng cách gần nhất P1/P2/P3: 1.405,1 /114,6 /652,6 m. Tuyến chưa phân bổ ghi `access_only_not_enrollment`. Capacity/enrollment/nền học sinh/occupancy thiếu nên unserved vẫn null.
- **Sensitivity giao thông:** sửa prior bỏ qua tham số thay đổi lưu lượng. Profile hiệu lực được scale về đỉnh giả định của case, giữ dạng ngày/tỷ lệ lớp và bảo toàn tổng khi làm tròn. Đã kiểm tra 400/800/1.200 xe/h. Đây là OD giả định, chưa hiệu chỉnh từ video.
- **Bóng đổ:** freeze footprint/cây OSM bên ngoài union mọi parcel trong 300 m, dùng chung giữa options/phases. Receiver chung loại cả mái hàng xóm. Case thực có **23 footprint, 0 cây được map; cả 23 thiếu chiều cao** nên dùng default có nhãn. Test riêng kiểm tra cây và chiều cao có tag. Inventory chưa đầy đủ; chưa có mô hình nhiệt độ/UTCI.
- **Docker:** build lại từ mã nguồn; thay đúng API/worker khi không có job queued/running; giữ volume SQLite và readonly snapshot. Chưa commit/push/deploy production.

### Case local mới nhất

[Mở kết quả 3 parcel](http://127.0.0.1:8007/simulation/planning?job=246bfe99-59a4-472f-82b8-e5f4e07885af&option=together_3).

Job `246bfe99-59a4-472f-82b8-e5f4e07885af`, run `f3baac15-5938-47bd-b1cc-8d7eeb356bb5`: 3 parcel, 5 options, 3 phases; OSM + prior clip22; SUMO count balance và SWMM balance đạt. Cả 3 parcel vẫn có cảnh báo công năng quy hoạch; đây là what-if, không chứng minh được phép xây chung cư.

`test-results/planning-fixed-context/` chứa native-result.json, context-handoff-report.json, school-map.json, shadow-map.json, artifacts.zip (160 members, không hỏng), báo cáo API/UI. Options dùng cùng 23 đối tượng hàng xóm và cùng receiver; map APIs trả mixed_demo và manifest nguồn.

### Kiểm thử và phần còn lại

- Model 0.17: **245 passed, 4 skipped**, 269,53 s (`test-results/planning-backend-regression-017.xml`). Bốn skips cần PostGIS; hai bộ test giá đất độc lập của task khác không nằm trong lần chạy này. Không tính skip là pass.
- Model 0.18: tập liên quan **32/32 passed**, 29,72 s (`test-results/planning-context-regression-018.xml`), native và ZIP thành công. Không coi 245 là toàn bộ regression 0.18.
- UI mới: **6 nhóm đạt** (`test-results/planning-fixed-context/ui-report.json`), gồm mở lại deep link, tuyến trường học OSM có nhãn chưa xác nhận chỗ học, chọn nhiều đất, cumulative, nhóm tùy chọn/counting và mobile. Image đang phục vụ đã rebuild cả caption UI; manifest `56c5fa2f96a47548cfa292c16762763052d13bb60373dbccec3ff2bcff36c737`.
- Counting: đã lấy ba filmstrip nguồn xuyên suốt cửa sổ về `.runtime/traffic-counting-review/manual-review/`. Filmstrip thưa chỉ hỗ trợ review; không tự tạo ground truth hoặc công bố precision/recall counting từ nó. Cần nhãn crossing độc lập và mapping camera/edge/time trước calibration.

**Chưa hoàn tất toàn bộ scope:** occupancy và khử trùng dân số; nền/công suất điện-nước-nước thải và sức chứa trường; terrain/cống/triều; chỉ tiêu quy hoạch; nhiệt screening; giá/chi phí; counting validation. Bước tiếp theo là gói nền giả định demo có nhãn và sensitivity cho trường thiếu nguồn, để backend chuẩn bị nền từ parcel khi người dùng nhập building plan. Giữ dữ liệu thật và giả định riêng trong contract/kết quả.
