"use strict";
const keys = ["baseline", "development"];
const labels = {baseline: "Hiện trạng", development: "Công trình dự định xây", mitigated: "Thiết kế cũ đã nhập", suggested: "Gợi ý đang so sánh"};
const surfaces = ["roof", "paved", "permeable", "green"];
const surfaceLabels = ["Mái công trình", "Sân cứng", "Sân thấm", "Đất xanh"];
const el = id => document.getElementById(id);
const number = id => Number(el(id).value);
const fmt = value => new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 2}).format(value);
let site = null, area = 0, map = null, draftLayer = null, drawing = null, points = [];
let layers = {}, footprints = {}, result = null, busy = false, revision = 0;

function status(message, failed = false) {
  el("status").textContent = message;
  el("status").className = failed ? "error" : "success";
}

function invalidate() {
  revision++;
  result = null;
  el("results").hidden = true;
  if (!busy) status("Đầu vào đã thay đổi. Hãy tính lại để có kết quả tương ứng.");
}

async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST",
    headers: {"Content-Type": "application/json"}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(x => `${x.loc.join(".")}: ${x.msg}`).join("\n") : data.detail;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return data;
}

function drawGeometry(key, geometry) {
  if (!map) return;
  if (layers[key]) map.removeLayer(layers[key]);
  layers[key] = L.geoJSON(geometry, {style: {color: key === "site" ? "#355e77" : key === "development" ? "#ce8635" : "#0b8b79", fillOpacity: 0.15}}).addTo(map);
  if (key === "site") map.fitBounds(layers[key].getBounds(), {padding: [25, 25]});
}

async function setSite(geometry) {
  const expectedRevision = revision;
  const measured = await api("/api/v1/scenarios/site-area", geometry);
  if (revision !== expectedRevision) throw new Error("Đầu vào đã thay đổi trong khi đo diện tích. Hãy áp dụng lại khu đất.");
  invalidate();
  site = geometry;
  area = measured.area_m2;
  footprints = {};
  for (const key of keys) if (layers[key]) {map.removeLayer(layers[key]); delete layers[key];}
  el("site-json").value = JSON.stringify(site);
  el("area").textContent = `Diện tích khu đất: ${fmt(area)} m² · đo trên ellipsoid WGS84. Footprint trước đó đã được xóa.`;
  drawGeometry("site", site);
}

function setValues(key, percentages, storage, floors, users) {
  surfaces.forEach((s, i) => {el(`${key}-${s}`).value = percentages[i];});
  el(`${key}-storage`).value = storage;
  el(`${key}-floors`).value = floors;
  el(`${key}-users`).value = users;
}

async function demo() {
  if (busy) return;
  invalidate();
  el("ack").checked = false;
  el("title").value = "Ví dụ giả định · xây trường học";
  el("building-use").value = "school";
  el("rain").value = 60;
  [0.9, 0.85, 0.35, 0.2].forEach((v, i) => {el(`coef-${surfaces[i]}`).value = v;});
  el("coefficient-basis").value = "Hệ số minh họa do người dùng giả định; không phải hệ số đã hiệu chỉnh cho Thủ Đức.";
  el("design-basis").value = "Khu đất và thiết kế giả định để thử phần mềm; chưa khảo sát hiện trạng, chưa xác nhận thửa đất.";
  setValues("baseline", [0, 10, 20, 70], 0, 1, 0);
  setValues("development", [30, 50, 10, 10], 0, 3, 600);
  el("target-runoff").value = 0;
  el("target-green").value = 30;
  el("target-impervious").value = 70;
  el("target-basis").value = "Mục tiêu giả định: không tăng nước còn lại, đất xanh ít nhất 30%, mái và sân cứng tối đa 70%.";
  el("minimum-paved").value = 10;
  el("maximum-green").value = 20;
  el("maximum-permeable").value = 30;
  el("maximum-storage").value = 100;
  el("budget").value = 1000000000;
  el("cost-green").value = 100000;
  el("cost-permeable").value = 150000;
  el("cost-storage").value = 2000000;
  el("cost-basis").value = "Giới hạn và chi phí giả định để thử phần mềm; chưa có khảo sát hoặc báo giá thực tế.";
  const demandDemo = {"trip-rate":.25,"vehicle-share":80,"vehicle-occupancy":1.5,"water-rate":80,"wastewater-fraction":80,"power-rate":.1,
    "vehicle-capacity":60,"water-capacity":30,"wastewater-capacity":25,"power-capacity":45,
    "minimum-vehicle-share":40,"maximum-water-saving":40,"maximum-power-saving":30,
    "cost-transport":2000000,"cost-water":1000000,"cost-power":1500000};
  Object.entries(demandDemo).forEach(([id,value])=>{el(id).value=value;});
  el("demand-basis").value = "Hệ số nhu cầu và công suất còn lại giả định để thử phần mềm; chưa đo lưu lượng hoặc đối chiếu nhà cung cấp hạ tầng.";
  el("transport-feasible").checked = true;
  await setSite({type: "Polygon", coordinates: [[[106.76,10.82],[106.761,10.82],[106.761,10.821],[106.76,10.821],[106.76,10.82]]]});
  status("Đã nạp ví dụ giả định. Kiểm tra hệ số, tỷ lệ bề mặt và xác nhận trước khi tính.");
}

function stopDrawing() {
  drawing = null; points = [];
  if (draftLayer && map) map.removeLayer(draftLayer);
  draftLayer = null;
  if (map) map.doubleClickZoom.enable();
}

async function finishDrawing() {
  if (busy) return;
  if (!drawing || points.length < 3) throw new Error("Cần chọn ít nhất ba điểm.");
  const target = drawing;
  const geometry = {type: "Polygon", coordinates: [[...points, points[0]]]};
  const expectedRevision = revision;
  if (target === "site") await setSite(geometry);
  else {
    const measured = await api("/api/v1/scenarios/site-area", geometry);
    if (revision !== expectedRevision) throw new Error("Đầu vào đã thay đổi. Hãy vẽ lại footprint.");
    const percent = measured.area_m2 / area * 100;
    const green = 100 - percent - number(`${target}-paved`) - number(`${target}-permeable`);
    if (green < 0) throw new Error("Footprint quá lớn so với phần sân đã nhập. Hãy điều chỉnh tỷ lệ sân trước.");
    // The backend additionally checks containment before accepting the run.
    invalidate();
    footprints[target] = geometry;
    el(`${target}-roof`).value = percent;
    el(`${target}-green`).value = green;
    drawGeometry(target, geometry);
  }
  stopDrawing();
  status("Đã nhận polygon. Với footprint, tỷ lệ mái và phần đất xanh còn lại đã được cập nhật; hãy kiểm tra trước khi tính.");
}

function makePayload() {
  if (!site || !area) throw new Error("Hãy chọn khu đất trước.");
  if (JSON.stringify(JSON.parse(el("site-json").value)) !== JSON.stringify(site)) throw new Error("GeoJSON đã thay đổi. Hãy bấm Áp dụng khu đất trước khi tính.");
  const body = {title: el("title").value, building_use: el("building-use").value, site,
    rainfall_mm: number("rain"), coefficients: {}, coefficient_basis: el("coefficient-basis").value,
    design_basis: el("design-basis").value};
  body.evaluation = {allowed_runoff_increase_pct: number("target-runoff"), minimum_green_pct: number("target-green"),
    maximum_impervious_pct: number("target-impervious"), basis: el("target-basis").value};
  body.demand = {
    peak_person_trips_per_user_hour: number("trip-rate"), private_vehicle_share: number("vehicle-share")/100,
    average_vehicle_occupancy: number("vehicle-occupancy"), water_liters_per_user_day: number("water-rate"),
    wastewater_fraction: number("wastewater-fraction")/100, peak_kw_per_user: number("power-rate"),
    remaining_vehicle_trips_per_hour: number("vehicle-capacity"), remaining_water_m3_per_day: number("water-capacity"),
    remaining_wastewater_m3_per_day: number("wastewater-capacity"), remaining_power_kw: number("power-capacity"), basis: el("demand-basis").value,
  };
  surfaces.forEach(s => {body.coefficients[s] = number(`coef-${s}`);});
  for (const key of keys) {
    const percentages = surfaces.map(s => number(`${key}-${s}`));
    if (Math.abs(percentages.reduce((a,b) => a+b, 0) - 100) > 1e-6) throw new Error(`${labels[key]}: tỷ lệ bề mặt phải cộng đúng 100%.`);
    const variant = {available_storage_m3: number(`${key}-storage`), floors: number(`${key}-floors`), users: number(`${key}-users`)};
    surfaces.forEach((s, i) => {variant[`${s}_m2`] = area * percentages[i] / 100;});
    if (footprints[key]) variant.footprint = footprints[key];
    body[key] = variant;
  }
  return body;
}

function textCell(row, value, header = false) {
  const cell = document.createElement(header ? "th" : "td");
  cell.textContent = value;
  row.appendChild(cell);
}

function render(data, selectedIndex = 0) {
  result = data;
  el("results").hidden = false;
  el("result-title").textContent = `${data.inputs.title} · ${fmt(data.site_area_m2)} m² · mưa ${fmt(data.inputs.rainfall_mm)} mm`;
  const table = el("metrics"); table.replaceChildren();
  const displayVariants = {...data.variants};
  const selected = data.recommendations?.[selectedIndex];
  if (selected) displayVariants.suggested = selected.predicted;
  const displayKeys = Object.keys(displayVariants);
  const header = document.createElement("tr");
  textCell(header, "Chỉ số", true); displayKeys.forEach(k => textCell(header, k === "suggested" ? selected.label : labels[k], true)); table.appendChild(header);
  const metrics = [["gross_runoff_m3", "Nước chảy tràn trước giữ nước (m³)"], ["retained_m3", "Nước giữ lại giả định (m³)"],
    ["unretained_runoff_m3", "Nước còn lại sau giữ nước (m³)"], ["impervious_area_m2", "Mái + sân cứng (m²)"],
    ["green_area_m2", "Đất xanh (m²)"], ["gross_floor_area_estimate_m2", "Diện tích sàn ước tính (m²)"], ["users", "Người sử dụng được nhập"]];
  if (data.inputs.demand) metrics.push(["peak_vehicle_trips_per_hour","Chuyến xe giờ cao điểm (chuyến/giờ)"],
    ["water_demand_m3_per_day","Nhu cầu nước (m³/ngày)"],["wastewater_m3_per_day","Nước thải (m³/ngày)"],["peak_power_kw","Điện giờ cao điểm (kW)"]);
  for (const [key, label] of metrics) {
    const row = document.createElement("tr"); textCell(row, label);
    displayKeys.forEach(k => textCell(row, fmt(displayVariants[k][key]))); table.appendChild(row);
  }
  el("bars").replaceChildren();
  const maximum = Math.max(...displayKeys.map(k => displayVariants[k].unretained_runoff_m3), 1);
  for (const key of displayKeys) {
    const row = document.createElement("div"); row.className = "bar";
    const label = document.createElement("span"); label.textContent = key === "suggested" ? selected.label : labels[key];
    const bar = document.createElement("i"); bar.style.width = `${displayVariants[key].unretained_runoff_m3 / maximum * 55}%`;
    const value = document.createElement("b"); value.textContent = `${fmt(displayVariants[key].unretained_runoff_m3)} m³`;
    row.append(label, bar, value); el("bars").appendChild(row);
  }
  el("deltas").replaceChildren();
  for (const comparison of data.comparisons) {
    const item = document.createElement("li");
    const delta = comparison.delta.unretained_runoff_m3;
    item.textContent = `${labels[comparison.from]} → ${labels[comparison.to]}: nước còn lại ${delta >= 0 ? "tăng" : "giảm"} ${fmt(Math.abs(delta))} m³; đất xanh thay đổi ${fmt(comparison.delta.green_area_m2)} m².`;
    el("deltas").appendChild(item);
  }
  el("basis").textContent = `${data.method.runoff}. ${data.method.storage}. Hệ số: ${data.method.coefficient_basis} Hiện trạng và thiết kế: ${data.method.design_basis}`;
  if (data.method.demand) el("basis").textContent += ` Nguồn hệ số nhu cầu và công suất còn lại: ${data.method.demand.basis}`;
  el("limitations").replaceChildren();
  for (const text of data.limitations) {const item = document.createElement("li"); item.textContent = text; el("limitations").appendChild(item);}
  el("saved").replaceChildren();
  const link = document.createElement("a"); link.textContent = "Mở lại bài đánh giá này"; link.href = `/simulation?run=${encodeURIComponent(data.id)}`;
  el("saved").append(`Đã lưu lúc ${new Date(data.created_at).toLocaleString("vi-VN")} · `, link);
  renderAssessment(data);
  renderSuggestions(data, selectedIndex);
}

function renderAssessment(data) {
  const assessment = data.impact_assessment;
  el("assessment").replaceChildren();
  el("recommend-form").hidden = !assessment;
  if (!assessment) {el("assessment").textContent = "Đây là kết quả luồng so sánh cũ. Có thể nhập mục tiêu và chạy lại luồng dự tính tác động."; return;}
  const verdicts = {better:"Tốt hơn", worse:"Xấu hơn", mixed:"Có đánh đổi giữa các tiêu chí", unchanged:"Không thay đổi"};
  const heading = document.createElement("strong"); heading.textContent = `${verdicts[assessment.verdict]} so với hiện trạng — xét áp lực môi trường/hạ tầng theo giả định.`;
  const list = document.createElement("ul");
  const directions = {better:"tốt hơn", worse:"xấu hơn", unchanged:"không đổi"};
  for (const change of assessment.changes) {
    const item = document.createElement("li");
    item.textContent = `${change.label}: ${fmt(change.baseline)} → ${fmt(change.predicted)} ${change.units} (${directions[change.direction]}).`;
    list.appendChild(item);
  }
  for (const target of assessment.targets) {
    const item = document.createElement("li");
    const change = assessment.changes.find(x => x.metric === target.metric);
    item.textContent = `${target.met ? "Đạt" : "Chưa đạt"} mục tiêu ${change.label}: ${target.operator} ${fmt(target.target)} ${change.units}.`;
    list.appendChild(item);
  }
  const basis = document.createElement("p"); basis.className = "hint";
  basis.textContent = `${assessment.target_basis} ${assessment.interpretation}`;
  el("assessment").append(heading,list,basis);
}

function renderSuggestions(data, selectedIndex) {
  const root = el("suggestions"); root.replaceChildren();
  if (!data.recommendations?.length) {
    if (data.recommendation_status === "no_feasible_improvement") root.textContent = "Không tìm được cải thiện trong ngân sách và giới hạn đã nhập. Cần xem lại ràng buộc hoặc thiết kế công trình.";
    return;
  }
  const heading = document.createElement("h3"); heading.textContent = "Gợi ý do hệ thống tạo và tính lại"; root.appendChild(heading);
  if (data.recommendation_status === "partial_improvement") {
    const note = document.createElement("p"); note.textContent = "Có cải thiện nhưng chưa đạt đủ mục tiêu trong các phương án đã tìm. Hãy xem các mục tiêu còn thiếu."; root.appendChild(note);
  }
  data.recommendations.forEach((candidate,index) => {
    const card = document.createElement("div"); card.className = "suggestion";
    const title = document.createElement("strong"); title.textContent = `${candidate.label} · ${candidate.assessment.targets_met ? "Đạt mục tiêu đã chọn" : "Chưa đạt đủ mục tiêu"}`;
    const actions = document.createElement("p");
    actions.textContent = `Đổi ${fmt(candidate.changes.paved_to_green_m2)} m² sân cứng sang đất xanh; ${fmt(candidate.changes.paved_to_permeable_m2)} m² sang sân thấm; thêm ${fmt(candidate.changes.additional_storage_m3)} m³ giữ nước.`;
    const outcome = document.createElement("p"); outcome.textContent = `Nước còn lại: ${fmt(candidate.predicted.unretained_runoff_m3)} m³; đất xanh: ${fmt(candidate.predicted.green_area_m2)} m²; chi phí giả định: ${fmt(candidate.estimated_cost_vnd)} VND. Giữ nguyên công trình và số người.`;
    if (data.inputs.demand) {
      actions.textContent += ` Chỉ tiêu vận hành cần kiểm chứng: xe cá nhân ${fmt(candidate.operations.private_vehicle_share*100)}%; tiết kiệm nước ${fmt(candidate.operations.water_saving_fraction*100)}%; giảm điện cao điểm ${fmt(candidate.operations.power_saving_fraction*100)}%.`;
      outcome.textContent += ` Dự tính: ${fmt(candidate.predicted.peak_vehicle_trips_per_hour)} chuyến xe/giờ; ${fmt(candidate.predicted.water_demand_m3_per_day)} m³ nước/ngày; ${fmt(candidate.predicted.wastewater_m3_per_day)} m³ thải/ngày; ${fmt(candidate.predicted.peak_power_kw)} kW.`;
    }
    const missing = document.createElement("p"); missing.className = "hint";
    missing.textContent = candidate.assessment.targets.filter(x=>!x.met).map(x=>{
      const metric = candidate.assessment.changes.find(c=>c.metric===x.metric);
      return `Chưa đạt ${metric.label}: ${fmt(x.actual)} ${metric.units}, mục tiêu ${x.operator} ${fmt(x.target)}.`;
    }).join(" ");
    const button = document.createElement("button"); button.type = "button"; button.className = "secondary";
    button.textContent = index === selectedIndex ? "Đang so sánh trong bảng" : "Xem trong bảng so sánh";
    button.addEventListener("click",()=>render(data,index));
    card.append(title,actions,outcome,missing,button); root.appendChild(card);
  });
  const method = document.createElement("p"); method.className = "hint";
  method.textContent = `${data.recommendation_method.ranking} ${data.recommendation_method.limitations} Chi phí: ${data.recommendation_method.cost_basis}`;
  root.appendChild(method);
}

function restoreInputs(data) {
  const inputs = data.inputs;
  site = inputs.site;
  area = data.site_area_m2;
  footprints = {};
  el("site-json").value = JSON.stringify(site);
  el("area").textContent = `Diện tích khu đất đã lưu: ${fmt(area)} m².`;
  el("title").value = inputs.title;
  el("building-use").value = inputs.building_use;
  el("rain").value = inputs.rainfall_mm;
  el("coefficient-basis").value = inputs.coefficient_basis;
  el("design-basis").value = inputs.design_basis;
  if (inputs.demand) {
    const demand = inputs.demand;
    const values = {"trip-rate":demand.peak_person_trips_per_user_hour,"vehicle-share":demand.private_vehicle_share*100,
      "vehicle-occupancy":demand.average_vehicle_occupancy,"water-rate":demand.water_liters_per_user_day,
      "wastewater-fraction":demand.wastewater_fraction*100,"power-rate":demand.peak_kw_per_user,
      "vehicle-capacity":demand.remaining_vehicle_trips_per_hour,"water-capacity":demand.remaining_water_m3_per_day,
      "wastewater-capacity":demand.remaining_wastewater_m3_per_day,"power-capacity":demand.remaining_power_kw};
    Object.entries(values).forEach(([id,value])=>{el(id).value=value;});
    el("demand-basis").value = demand.basis;
  }
  if (inputs.evaluation) {
    el("target-runoff").value = inputs.evaluation.allowed_runoff_increase_pct;
    el("target-green").value = inputs.evaluation.minimum_green_pct;
    el("target-impervious").value = inputs.evaluation.maximum_impervious_pct;
    el("target-basis").value = inputs.evaluation.basis;
  }
  surfaces.forEach(s => {el(`coef-${s}`).value = inputs.coefficients[s];});
  for (const key of keys) {
    const variant = inputs[key];
    setValues(key, surfaces.map(s => variant[`${s}_m2`] / area * 100),
      variant.available_storage_m3, variant.floors, variant.users);
    if (variant.footprint) footprints[key] = variant.footprint;
  }
  el("ack").checked = false;
  if (data.recommendation_constraints) {
    const constraints = data.recommendation_constraints;
    el("minimum-paved").value = constraints.minimum_paved_m2 / area * 100;
    el("maximum-green").value = constraints.maximum_green_conversion_m2 / area * 100;
    el("maximum-permeable").value = constraints.maximum_permeable_conversion_m2 / area * 100;
    el("maximum-storage").value = constraints.maximum_additional_storage_m3;
    el("budget").value = constraints.budget_vnd;
    el("cost-green").value = constraints.green_cost_vnd_per_m2;
    el("cost-permeable").value = constraints.permeable_cost_vnd_per_m2;
    el("cost-storage").value = constraints.storage_cost_vnd_per_m3;
    el("cost-basis").value = constraints.cost_basis;
    el("minimum-vehicle-share").value = constraints.minimum_private_vehicle_share*100;
    el("transport-feasible").checked = constraints.transport_shift_feasible;
    el("maximum-water-saving").value = constraints.maximum_water_saving_fraction*100;
    el("maximum-power-saving").value = constraints.maximum_power_saving_fraction*100;
    el("cost-transport").value = constraints.transport_cost_vnd_per_share_point;
    el("cost-water").value = constraints.water_cost_vnd_per_saving_point;
    el("cost-power").value = constraints.power_cost_vnd_per_saving_point;
  }
}

async function run(event) {
  event.preventDefault();
  if (busy) return;
  const body = makePayload();
  const expectedRevision = revision;
  busy = true; el("run").disabled = true; status("Đang tính và lưu bài đánh giá…");
  try {
    const data = await api("/api/v1/scenarios/building/predict", body);
    if (revision !== expectedRevision) {
      status(`Đã lưu lần chạy ${data.id}, nhưng đầu vào đã thay đổi. Hãy tính lại hoặc mở /simulation?run=${data.id}.`);
      return;
    }
    render(data);
    status("Đã dự tính và đánh giá công trình. Bạn có thể nhập giới hạn rồi yêu cầu hệ thống tìm gợi ý cải thiện.");
  } finally {busy = false; el("run").disabled = false;}
}

async function requestRecommendations(event) {
  event.preventDefault();
  if (busy || !result) return;
  const source = result;
  const measuredArea = source.site_area_m2;
  const body = {
    minimum_paved_m2: number("minimum-paved") / 100 * measuredArea,
    maximum_green_conversion_m2: number("maximum-green") / 100 * measuredArea,
    maximum_permeable_conversion_m2: number("maximum-permeable") / 100 * measuredArea,
    maximum_additional_storage_m3: number("maximum-storage"), budget_vnd: number("budget"),
    green_cost_vnd_per_m2: number("cost-green"), permeable_cost_vnd_per_m2: number("cost-permeable"),
    storage_cost_vnd_per_m3: number("cost-storage"), cost_basis: el("cost-basis").value,
    minimum_private_vehicle_share: number("minimum-vehicle-share")/100, transport_shift_feasible: el("transport-feasible").checked,
    maximum_water_saving_fraction: number("maximum-water-saving")/100, maximum_power_saving_fraction: number("maximum-power-saving")/100,
    transport_cost_vnd_per_share_point: number("cost-transport"), water_cost_vnd_per_saving_point: number("cost-water"),
    power_cost_vnd_per_saving_point: number("cost-power"),
  };
  const expectedRevision = revision;
  busy = true; el("recommend").disabled = true; status("Đang tạo phương án, tính lại tác động và kiểm tra mục tiêu/ngân sách…");
  try {
    const data = await api(`/api/v1/scenarios/building/${source.id}/recommendations`, body);
    if (revision !== expectedRevision) {status(`Đã lưu gợi ý tại /simulation?run=${data.id}; đầu vào đã thay đổi, hãy dự tính lại.`); return;}
    render(data);
    status(data.recommendations.length ? "Đã tạo gợi ý từ kết quả dự tính và ràng buộc đã nhập. Chưa xác nhận tính khả thi thi công." : "Không tìm được gợi ý cải thiện trong các giới hạn hiện tại.");
  } finally {busy = false; el("recommend").disabled = false;}
}

function bind(id, handler) {
  el(id).addEventListener("click", () => Promise.resolve().then(handler).catch(e => status(e.message, true)));
}

function setup() {
  for (const key of keys) {
    const card = document.createElement("div"); card.className = "variant";
    const title = document.createElement("h3"); title.textContent = labels[key]; card.appendChild(title);
    for (const [index, surface] of surfaces.entries()) {
      const label = document.createElement("label"); label.textContent = `${surfaceLabels[index]} (%)`;
      const input = document.createElement("input"); input.id = `${key}-${surface}`; input.type = "number";
      input.min = 0; input.max = 100; input.step = "any"; input.required = true; input.value = surface === "green" ? 100 : 0;
      label.appendChild(input); card.appendChild(label);
    }
    for (const [suffix, labelText, max, step, value] of [["storage", "Dung tích trống giữ nước (m³)", 1000000, "any", 0], ["floors", "Số tầng", 100, "1", 1], ["users", "Người sử dụng", 100000, "1", 0]]) {
      const label = document.createElement("label"); label.textContent = labelText;
      const input = document.createElement("input"); input.id = `${key}-${suffix}`; input.type = "number";
      input.min = suffix === "floors" ? 1 : 0; input.max = max; input.step = step; input.required = true; input.value = value;
      label.appendChild(input); card.appendChild(label);
    }
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "secondary"; remove.textContent = "Xóa footprint";
    remove.addEventListener("click", () => {delete footprints[key]; if (layers[key]) {map.removeLayer(layers[key]); delete layers[key];} invalidate();});
    card.appendChild(remove); el("variant-inputs").appendChild(card);
  }
  if (typeof L !== "undefined") {
    map = L.map("map").setView([10.82,106.76], 16);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
    map.on("click", event => {
      if (!drawing || busy) return;
      points.push([event.latlng.lng, event.latlng.lat]);
      if (draftLayer) map.removeLayer(draftLayer);
      draftLayer = L.polyline(points.map(p => [p[1],p[0]]), {color:"#aa4d35"}).addTo(map);
    });
  } else el("map").textContent = "Bản đồ chưa tải. Bạn vẫn có thể nạp ví dụ hoặc nhập GeoJSON bên dưới.";
  bind("demo", demo);
  bind("apply-site", async () => {if (!busy) {await setSite(JSON.parse(el("site-json").value)); status("Đã nhận khu đất.");}});
  bind("draw", () => {
    if (busy) return;
    if (!map) throw new Error("Bản đồ chưa tải. Hãy dùng GeoJSON.");
    stopDrawing(); const target = el("draw-target").value;
    if (target !== "site" && !site) throw new Error("Hãy vẽ khu đất trước.");
    drawing = target; map.doubleClickZoom.disable();
    status("Bấm lần lượt các đỉnh rồi chọn Hoàn tất polygon.");
  });
  bind("finish", finishDrawing); bind("cancel", stopDrawing);
  bind("download", () => {
    if (!result) return;
    const link = document.createElement("a"); const url = URL.createObjectURL(new Blob([JSON.stringify(result,null,2)], {type:"application/json"}));
    link.href = url; link.download = `building-scenario-${result.id}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  bind("print", () => window.print());
  el("editor").addEventListener("submit", event => run(event).catch(error => status(error.message, true)));
  el("recommend-form").addEventListener("submit", event => requestRecommendations(event).catch(error => status(error.message,true)));
  el("recommend-form").addEventListener("input", () => {
    revision++;
    if (result) render(result, -1);
    el("suggestions").replaceChildren();
    if (!busy) status("Giới hạn hoặc chi phí đã thay đổi. Hãy tìm lại gợi ý để kiểm tra ràng buộc mới.");
  });
  el("editor").addEventListener("input", invalidate);
  el("site-json").addEventListener("input", invalidate);
  const id = new URLSearchParams(window.location.search).get("run");
  if (id) api(`/api/v1/scenarios/building/${encodeURIComponent(id)}`).then(data => {
    restoreInputs(data); render(data); drawGeometry("site", data.inputs.site);
    for (const key of keys) if (data.inputs[key].footprint) drawGeometry(key, data.inputs[key].footprint);
    status("Đang xem kết quả đã lưu. Bạn có thể sửa thiết kế, xác nhận và tính thành lần chạy mới.");
  }).catch(error => status(error.message, true));
}
setup();
