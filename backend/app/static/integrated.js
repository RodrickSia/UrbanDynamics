"use strict";
const $ = (id) => document.getElementById(id);
const esc = (x) =>
  String(x).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmt = (x) =>
  Number(x).toLocaleString("vi-VN", { maximumFractionDigits: 2 });
const labels = {
  building_density_percent: "Mật độ xây dựng",
  far: "FAR",
  green_percent: "Đất xanh",
  canopy_m2: "Tán cây (union)",
  impervious_percent: "Bề mặt không thấm",
  unretained_runoff_m3: "Runoff screening chưa giữ",
  node_flooding_m3: "Nước tràn nút SWMM",
  traffic_delay_seconds: "Chậm trễ SUMO",
  traffic_queue_m: "Hàng chờ SUMO",
  traffic_unfinished_vehicles: "Xe chưa hoàn thành",
  traffic_undeparted_vehicles: "Xe chưa xuất phát",
  freshwater_m3_day: "Nước cấp",
  wastewater_m3_day: "Nước thải",
  energy_kwh_day: "Điện năng",
  power_peak_kw: "Cao điểm điện",
  residents: "Cư dân thường trú",
  housing_units: "Căn hộ",
  service_capacity: "Công suất phục vụ",
  service_unserved_people: "Nhu cầu dịch vụ chưa đáp ứng",
  mean_outdoor_shaded_percent: "Bóng mát trong khu đất",
  neighbour_shadow_m2: "Bóng đổ ngoài khu đất",
  road_length_m: "Đường kịch bản",
};
const verdicts = {
  better: "Cải thiện",
  worse: "Tăng sức ép",
  benefit: "Lợi ích phục vụ",
  increased_demand: "Tăng nhu cầu",
  reduced_demand: "Giảm nhu cầu",
  unchanged: "Không đổi",
  context_change: "Thay đổi bối cảnh",
};
const blockFields = [
  "floors",
  "height_m",
  "units",
  "residents",
  "staff",
  "daily_visitors",
  "daily_users",
  "service_capacity",
];
const designFields = [
  "green_m2",
  "permeable_m2",
  "paved_m2",
  "storage_m3",
  "parking_spaces",
  "ev_chargers",
  "gate_lanes",
  "gate_service_seconds",
];
let plan,
  presets,
  result = null,
  revision = 0,
  busy = false,
  jsonDirty = false,
  drawMode = null,
  vertices = [],
  mapBounds;
function status(message, error = false) {
  $("status").textContent = message;
  $("status").className = error ? "error" : "";
}
async function api(url, body) {
  const response = await fetch(
    url,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : JSON.stringify(value.detail),
    );
  return value;
}
function invalidate() {
  revision++;
  result = null;
  $("results").hidden = true;
  history.replaceState(null, "", location.pathname);
}
function showPlan() {
  const b = plan.development.buildings[0];
  $("title").value = plan.title;
  for (const f of blockFields) $(f).value = b[f] ?? 0;
  for (const f of designFields)
    $(f).value = ["green_m2", "permeable_m2", "paved_m2"].includes(f)
      ? Number(plan.development[f] ?? 0).toFixed(2)
      : (plan.development[f] ??
        { gate_lanes: 1, gate_service_seconds: 8 }[f] ??
        0);
  $("level").value = plan.conditions?.level ?? "base";
  $("seed").value = plan.conditions?.seed ?? 2026;
  $("solar_date").value = plan.conditions?.solar_date ?? "2026-04-15";
  $("plan-json").value = JSON.stringify(plan, null, 2);
  renderMap();
}
function readPlan() {
  const b = plan.development.buildings[0];
  plan.title = $("title").value;
  for (const f of blockFields) b[f] = Number($(f).value);
  for (const f of designFields) plan.development[f] = Number($(f).value);
  plan.conditions = {
    ...(plan.conditions ?? {}),
    level: $("level").value,
    seed: Number($("seed").value),
    solar_date: $("solar_date").value,
  };
  $("plan-json").value = JSON.stringify(plan, null, 2);
  return structuredClone(plan);
}
function setBusy(value) {
  busy = value;
  $("predict").disabled = value || jsonDirty;
  $("recommend").disabled = value;
}
function state() {
  const key = $("state").value;
  if (key === "baseline") return result.variants.baseline;
  if (key.startsWith("rec-"))
    return result.recommendations[Number(key.slice(4))].predicted;
  return result.variants.development;
}
function geometries(geo) {
  if (!geo) return [];
  if (geo.type === "FeatureCollection")
    return geo.features.flatMap((f) => geometries(f.geometry));
  if (geo.type === "Feature") return geometries(geo.geometry);
  return [geo];
}
function allPoints(geo) {
  return geometries(geo)
    .flatMap(
      (g) =>
        g.coordinates?.flat(
          g.type === "Polygon" || g.type === "MultiLineString"
            ? 1
            : g.type === "MultiPolygon"
              ? 2
              : 0,
        ) ?? [],
    )
    .filter((p) => Array.isArray(p));
}
function renderMap() {
  if (!plan) return;
  const features = [];
  features.push([plan.site, "site"]);
  const s = result ? state() : null;
  const design = s
    ? $("state").value === "baseline"
      ? result.context.baseline
      : $("state").value.startsWith("rec-")
        ? result.recommendations[Number($("state").value.slice(4))].design
        : plan.development
    : plan.development;
  if (s) {
    features.push([s.traffic.network, "road"]);
    features.push([s.services.map, "service"]);
    if (s.drainage.map) features.push([s.drainage.map, "drain"]);
    for (const f of result.context.layers.flood_history.features ?? [])
      features.push([f, "flood"]);
    for (const f of s.shadow.map.features.filter(
      (f) => f.properties.hour_local === Number($("shadow-hour").value),
    ))
      features.push([f, "shadow"]);
  }
  for (const b of design.buildings) features.push([b.footprint, "building"]);
  const points = allPoints(plan.site);
  const xs = points.map((p) => p[0]),
    ys = points.map((p) => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2,
    cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const width = Math.max(0.0015, Math.max(...xs) - Math.min(...xs)) * 3.4,
    height = width / 1.9;
  mapBounds = { x: cx - width / 2, y: cy - height / 2, width, height };
  const xy = (p) => [
    ((p[0] - mapBounds.x) / width) * 600,
    330 - ((p[1] - mapBounds.y) / height) * 330,
  ];
  const colors = {
    site: "#287aa4",
    building: "#da8429",
    shadow: "#8964a8",
    road: "#858e95",
    service: "#16877b",
    flood: "#c53343",
    drain: "#534db1",
  };
  let markup =
    '<text x="10" y="20" fill="#516a70" font-size="12">Vector khu đất / WGS84 • ↑ Bắc</text>';
  for (const [geo, kind] of features)
    for (const g of geometries(geo)) {
      const c = colors[kind];
      if (g.type === "Point") {
        const [x, y] = xy(g.coordinates);
        markup += `<circle cx="${x}" cy="${y}" r="5" fill="${c}"/>`;
      } else {
        let paths =
          g.type === "Polygon"
            ? [g.coordinates]
            : g.type === "MultiPolygon"
              ? g.coordinates
              : g.type === "LineString"
                ? [[g.coordinates]]
                : g.type === "MultiLineString"
                  ? g.coordinates.map((line) => [line])
                  : [];
        for (const rings of paths) {
          const path = rings
            .map(
              (ring) =>
                ring
                  .map((p, i) => `${i ? "L" : "M"}${xy(p).join(" ")}`)
                  .join(" ") + (kind === "road" ? "" : "Z"),
            )
            .join(" ");
          markup += `<path d="${path}" fill="${kind === "road" ? "none" : c}" fill-opacity="${kind === "site" ? 0.08 : kind === "shadow" ? 0.25 : 0.65}" stroke="${c}" stroke-width="${kind === "road" ? 4 : 2}" fill-rule="evenodd"/>`;
        }
      }
    }
  if (vertices.length)
    markup += `<polyline points="${vertices.map((p) => xy(p).join(",")).join(" ")}" fill="none" stroke="#b62538" stroke-width="3"/>`;
  $("map").innerHTML = markup;
}
function chart() {
  const key = $("series").value;
  const datasets = [
      result.variants.baseline.demand.hourly[key],
      result.variants.development.demand.hourly[key],
      state().demand.hourly[key],
    ],
    max = Math.max(1, ...datasets.flat());
  let svg = '<path d="M35 10V145H710" fill="none" stroke="#a6b9b9"/>';
  const colors = ["#91999f", "#d68735", "#097e76"];
  datasets.forEach((values, i) => {
    svg += `<polyline points="${values.map((v, h) => `${35 + h * 28},${145 - (v / max) * 125}`).join(" ")}" fill="none" stroke="${colors[i]}" stroke-width="2.5"/>`;
  });
  for (const h of [0, 6, 12, 18, 23])
    svg += `<text x="${35 + h * 28}" y="164" font-size="11">${h}h</text>`;
  svg += `<text x="0" y="20" font-size="11">${fmt(max)}</text>`;
  $("chart").innerHTML = svg;
}
function render() {
  const selected = state();
  $("results").hidden = false;
  $("assessment").textContent =
    `Có ${result.assessment.benefits.length} lợi ích/cải thiện và ${result.assessment.pressures.length} nhóm tăng sức ép/nhu cầu. ${result.assessment.targets.filter((t) => t.met).length}/${result.assessment.targets.length} mục tiêu giả định đạt. Cần đọc từng tiêu chí và tính khả thi của phương án.`;
  $("cards").innerHTML = [
    ["housing_units", "Căn hộ"],
    ["residents", "Cư dân"],
    ["freshwater_m3_day", "Nước m³/ngày"],
    ["power_peak_kw", "Điện cao điểm kW"],
  ]
    .map(
      ([k, l]) =>
        `<div class="metric">${l}<strong>${fmt(selected.metrics[k])}</strong></div>`,
    )
    .join("");
  $("impact").querySelector("tbody").innerHTML = result.assessment.rows
    .map(
      (r) =>
        `<tr><td>${esc(labels[r.metric] ?? r.metric)} <small>(${esc(r.unit)})</small></td><td>${fmt(r.baseline)}</td><td>${fmt(r.development)}</td><td>${fmt(selected.metrics[r.metric])}</td><td class="${esc(r.verdict)}">${esc(verdicts[r.verdict])}</td></tr>`,
    )
    .join("");
  $("run-info").textContent =
    `Run ${result.id} · ${result.created_at} · Context ${result.context.sha256.slice(0, 12)} · ${result.model_version}`;
  $("artifacts").href = `/api/v1/scenarios/integrated/${result.id}/artifacts`;
  const t = selected.traffic,
    d = selected.drainage;
  const roads = selected.roads;
  $("spatial-summary").textContent =
    `Tổng diện tích sàn: ${fmt(selected.gis.floor_area_m2)} m²; phương pháp theo từng khối: ${selected.gis.floor_area_method.join(", ")}.\n` +
    `Dịch vụ tổng hợp: ${fmt(selected.services.demand_people)} người/ngày cần phục vụ, ${fmt(selected.services.capacity_people)} công suất, ${fmt(selected.services.unserved_people)} chưa đáp ứng. Đi bộ tới điểm gần nhất: ${fmt(selected.services.walk_minutes_to_nearest)} phút trên mạng tổng hợp, không phải khảo sát thực tế.\n` +
    (roads
      ? `Đường kịch bản: ${fmt(roads.length_m)} m; mật độ ${fmt(roads.density_km_per_km2)} km/km² trong buffer 1 km. Nền có ${roads.baseline_connected_components} thành phần kết nối. Thay đổi topology chưa được mô phỏng.\n`
      : "") +
    `Nút SWMM tổng hợp:\n` +
    d.nodes
      .map(
        (node) =>
          `${node.id}: độ sâu nút tối đa ${fmt(node.peak_depth_m)} m; tràn ≈ ${fmt(node.flooding_m3)} m³ trong ${fmt(node.flooding_duration_minutes)} phút mẫu. Đây là độ sâu trong nút cống/bể, không là độ sâu ngập bề mặt.`,
      )
      .join("\n");
  $("engine-summary").textContent =
    `SUMO ${t.version}: ${t.planned_vehicles} xe kế hoạch; ${t.completed_vehicles} hoàn thành; ${t.unfinished_vehicles} chưa hoàn thành; ${t.undeparted_vehicles} chưa xuất phát. Chậm trễ trung bình chuyến hoàn thành: ${fmt(t.mean_completed_delay_seconds)} s. Hàng chờ lớn nhất: ${fmt(t.max_queue_length_m)} m.\n${t.limitations}\n\nSWMM ${d.version}: tràn nút ≈ ${fmt(d.node_flooding_m3)} m³; peak runoff ${fmt(d.runoff_peak_m3_s)} m³/s. Sai số liên tục: ${d.continuity_errors_percent.map(fmt).join(", ")}%. Kiểm tra balance: ${d.balance_passed ? "đạt" : "KHÔNG ĐẠT — không dùng để xếp hạng đạt mục tiêu"}.\n${d.limitations}\n\n${selected.shadow.limitations}`;
  $("provenance").textContent = JSON.stringify(
    {
      baseline: result.context.baseline_provenance,
      library: result.context.library,
      context_layers: Object.fromEntries(
        Object.entries(result.context.layers).map(([k, v]) => [
          k,
          { ...v, features: undefined },
        ]),
      ),
      weather: result.context.weather_context,
      synthetic: result.context.synthetic_components,
      conditions: result.context.conditions,
      unavailable: result.unavailable_modules,
      warnings: result.warnings,
      targets: result.assessment.targets,
    },
    null,
    2,
  );
  renderMap();
  chart();
}
function renderSuggestions() {
  const container = $("suggestions");
  container.innerHTML = "";
  const p = document.createElement("p");
  p.textContent = `Kết quả: ${result.recommendation_status}. Chi phí tổng hợp; mục tiêu chưa đạt vẫn được hiển thị.`;
  container.append(p);
  for (const [i, r] of result.recommendations.entries()) {
    const div = document.createElement("div");
    div.className = "suggestion";
    div.innerHTML = `<h3>${esc(r.name)} ${r.pareto ? "· Pareto trong các ứng viên" : ""}</h3><p>${fmt(r.estimated_cost_vnd)} VND · ${r.budget_applied ? "Đã xét ngân sách" : "Chưa đặt ngân sách"} · Giữ quy mô: ${r.scale_preserved ? "có" : "không"}</p><p>${r.assessment.targets.filter((t) => t.met).length}/${r.assessment.targets.length} mục tiêu đạt; ${r.versus_proposal.pressures.length} tiêu chí tăng sức ép so với đề xuất.</p><pre>${esc(JSON.stringify(r.actions, null, 2))}</pre>`;
    const button = document.createElement("button");
    button.textContent = "Xem tác động đã tính lại";
    button.onclick = () => {
      $("state").value = `rec-${i}`;
      render();
    };
    div.append(button);
    container.append(div);
  }
}
function updateStateOptions() {
  const selected = $("state").value;
  $("state").innerHTML =
    '<option value="development">Thiết kế ban đầu</option><option value="baseline">Hiện trạng</option>';
  result.recommendations.forEach((r, i) => {
    const option = document.createElement("option");
    option.value = `rec-${i}`;
    option.textContent = r.name;
    $("state").append(option);
  });
  if ([...$("state").options].some((o) => o.value === selected))
    $("state").value = selected;
}
function download(value, name) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function balance() {
  const token = revision;
  const payload = readPlan();
  const area = (await api("/api/v1/scenarios/site-area", payload.site)).area_m2;
  let roof = 0;
  for (const b of payload.development.buildings)
    roof += (await api("/api/v1/scenarios/site-area", b.footprint)).area_m2;
  if (token !== revision) return;
  plan.development.paved_m2 =
    area - roof - plan.development.green_m2 - plan.development.permeable_m2;
  if (plan.development.paved_m2 < 0)
    throw new Error("Đất xanh + thấm + mái vượt diện tích khu đất");
  invalidate();
  showPlan();
  status(`Khu đất ${fmt(area)} m²; mái ${fmt(roof)} m². Đã tính sân cứng.`);
}
for (const id of [
  "title",
  ...blockFields,
  ...designFields,
  "level",
  "seed",
  "solar_date",
])
  $(id).addEventListener("input", () => {
    readPlan();
    invalidate();
    renderMap();
    status("Thiết kế đã đổi. Bấm Dự tính để tính lại.");
  });
$("plan-json").addEventListener("input", () => {
  jsonDirty = true;
  invalidate();
  status("JSON đang chỉnh: chọn Áp dụng JSON trước khi dự tính.");
  $("predict").disabled = true;
});
$("apply-json").onclick = () => {
  try {
    const parsed = JSON.parse($("plan-json").value);
    if (!parsed.site || !parsed.development?.buildings?.length)
      throw new Error("Cần site và ít nhất một building");
    plan = parsed;
    jsonDirty = false;
    invalidate();
    showPlan();
    $("predict").disabled = busy;
    status("Đã áp dụng building plan.");
  } catch (e) {
    status(e.message, true);
  }
};
$("import-plan").onchange = async (e) => {
  try {
    $("plan-json").value = await e.target.files[0].text();
    $("apply-json").click();
  } catch (err) {
    status(err.message, true);
  }
};
$("preset").onchange = () => {
  plan = structuredClone(presets.building_presets[$("preset").value]);
  jsonDirty = false;
  invalidate();
  showPlan();
  $("predict").disabled = busy;
  status("Đã nạp mẫu; số liệu thiết kế mẫu có thể chỉnh.");
};
$("balance").onclick = () => balance().catch((e) => status(e.message, true));
$("predict").onclick = async () => {
  if (drawMode) {
    status("Hoàn thành hoặc hủy polygon trước khi chạy.", true);
    return;
  }
  const token = revision;
  setBusy(true);
  status("Đang chạy GIS, lịch nhu cầu, bóng đổ, SUMO và SWMM…");
  try {
    const data = await api("/api/v1/scenarios/integrated/predict", readPlan());
    if (token !== revision) {
      status("Thiết kế đã thay đổi; kết quả cũ được lưu nhưng không hiển thị.");
      return;
    }
    result = data;
    updateStateOptions();
    render();
    $("suggestions").innerHTML = "";
    history.replaceState(null, "", `?run=${result.id}`);
    status("Đã tính và lưu snapshot trước/sau.");
  } catch (e) {
    status(e.message, true);
  } finally {
    setBusy(false);
  }
};
$("recommend").onclick = async () => {
  const source = result,
    token = revision;
  setBusy(true);
  status("Đang chạy lại các ứng viên trên cùng nền…");
  try {
    const data = await api(
      `/api/v1/scenarios/integrated/${source.id}/recommendations`,
      {
        budget_vnd: $("budget").value === "" ? null : Number($("budget").value),
        maximum_surface_conversion_m2: Number($("conversion").value),
        maximum_additional_storage_m3: Number($("extra-storage").value),
        minimum_paved_m2: Number($("min-paved").value),
        allow_surface_changes: $("allow-surfaces").checked,
        allow_storage: $("allow-storage").checked,
        allow_operations: $("allow-operations").checked,
      },
    );
    if (token !== revision || result !== source) return;
    result = data;
    updateStateOptions();
    render();
    renderSuggestions();
    history.replaceState(null, "", `?run=${result.id}`);
    status("Đã chạy lại và lưu so sánh gợi ý.");
  } catch (e) {
    status(e.message, true);
  } finally {
    setBusy(false);
  }
};
for (const id of ["state", "series", "shadow-hour"])
  $(id).onchange = () => render();
$("export-plan").onclick = () => download(readPlan(), "building-plan.json");
$("export-result").onclick = () =>
  download(result, `integrated-${result.id}.json`);
$("print").onclick = () => window.print();
for (const kind of ["site", "building"])
  $(`draw-${kind}`).onclick = () => {
    drawMode = kind;
    vertices = [];
    invalidate();
    $("finish-draw").disabled = false;
    $("cancel-draw").disabled = false;
    status("Nhấp các đỉnh trên bản đồ, chọn Xong polygon.");
    renderMap();
  };
$("map").addEventListener("pointerdown", (e) => {
  if (!drawMode) return;
  const rect = $("map").getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * 600,
    y = ((e.clientY - rect.top) / rect.height) * 330;
  vertices.push([
    mapBounds.x + (x / 600) * mapBounds.width,
    mapBounds.y + ((330 - y) / 330) * mapBounds.height,
  ]);
  renderMap();
});
function cancelDraw() {
  drawMode = null;
  vertices = [];
  $("finish-draw").disabled = true;
  $("cancel-draw").disabled = true;
  renderMap();
}
$("cancel-draw").onclick = () => {
  cancelDraw();
  status("Đã hủy polygon đang vẽ.");
};
$("finish-draw").onclick = async () => {
  if (vertices.length < 3) {
    status("Cần ít nhất 3 đỉnh.", true);
    return;
  }
  const polygon = {
    type: "Polygon",
    coordinates: [[...vertices, vertices[0]]],
  };
  const token = revision,
    mode = drawMode;
  try {
    await api("/api/v1/scenarios/site-area", polygon);
    if (token !== revision || mode !== drawMode) return;
    if (mode === "site") plan.site = polygon;
    else plan.development.buildings[0].footprint = polygon;
    cancelDraw();
    showPlan();
    await balance();
  } catch (e) {
    status(e.message, true);
  }
};
(async () => {
  try {
    presets = await api("/api/v1/scenarios/integrated/presets");
    plan = structuredClone(presets.default);
    const run = new URLSearchParams(location.search).get("run");
    if (run) {
      result = await api(
        `/api/v1/scenarios/integrated/${encodeURIComponent(run)}`,
      );
      plan = structuredClone(result.inputs);
    }
    showPlan();
    if (result) {
      updateStateOptions();
      render();
      renderSuggestions();
    }
    status("Sẵn sàng. Chỉnh building plan rồi chọn Dự tính.");
  } catch (e) {
    status(e.message, true);
    $("predict").disabled = true;
  }
})();
