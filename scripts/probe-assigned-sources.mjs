// Run with Node 20+ from the repository root: node scripts/probe-assigned-sources.mjs
// Read-only, small probes. No credentials, bulk scraping or database writes.

const thuDuc = { latitude: 10.82, longitude: 106.76 };
const probes = [
  {
    name: "Open-Meteo hourly rain forecast",
    url: `https://api.open-meteo.com/v1/forecast?latitude=${thuDuc.latitude}&longitude=${thuDuc.longitude}&hourly=precipitation&forecast_days=1&timezone=Asia%2FHo_Chi_Minh`,
    kind: "json",
    check: (data) => Array.isArray(data.hourly?.precipitation) && data.hourly.precipitation.length > 0,
  },
  {
    name: "Open-Meteo historical rain",
    url: `https://archive-api.open-meteo.com/v1/archive?latitude=${thuDuc.latitude}&longitude=${thuDuc.longitude}&start_date=2026-09-01&end_date=2026-09-07&daily=precipitation_sum&timezone=Asia%2FHo_Chi_Minh`,
    kind: "json",
    check: (data) => Array.isArray(data.daily?.precipitation_sum) && data.daily.precipitation_sum.length === 7,
  },
  {
    name: "HCMC historical flood TSV",
    url: "https://dataverse.ird.fr/api/access/datafile/50148?format=original",
    kind: "tsv",
    check: (data) => data.trimEnd().split(/\r?\n/).length > 2 && data.includes("\t"),
  },
  {
    name: "HCMC historical flood GeoPackage",
    url: "https://dataverse.ird.fr/api/access/datafile/50143?format=original",
    kind: "gpkg",
    check: (data) => data.startsWith("SQLite format 3"),
  },
  {
    name: "Copernicus GFM STAC collection",
    url: "https://stac.eodc.eu/api/v1/collections/GFM",
    kind: "json",
    check: (data) => data.id === "GFM",
  },
  {
    name: "Copernicus GFM item near Thu Duc",
    url: "https://stac.eodc.eu/api/v1/collections/GFM/items?bbox=106.68,10.76,106.90,10.93&limit=1",
    kind: "json",
    check: (data) => Array.isArray(data.features) && data.features.length > 0,
  },
  {
    name: "HCMC official 2026 land-price PDF",
    url: "https://congbao.hochiminhcity.gov.vn/cong-bao/van-ban/nghi-quyet/so/87-2025-nq-hdnd/ngay/26-12-2025/tai-ve/48983?cbid=48993",
    kind: "pdf",
    check: (data) => data.startsWith("%PDF-"),
  },
];

async function runProbe(probe) {
  try {
    let response;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        response = await fetch(probe.url, {
          signal: AbortSignal.timeout(20000),
          headers: { "User-Agent": "UrbanDynamics-source-probe/1.0" },
        });
        break;
      } catch (error) {
        if (attempt === 3) throw error;
        await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
      }
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const contentType = response.headers.get("content-type") ?? "unknown";
    let valid;
    let detail;
    if (probe.kind === "json") {
      const data = await response.json();
      valid = probe.check(data);
      detail = probe.name.includes("forecast")
        ? `hours=${data.hourly?.precipitation?.length ?? "unknown"}; first-rain-mm=${data.hourly?.precipitation?.[0] ?? "unknown"}`
        : probe.name.includes("historical")
          ? `days=${data.daily?.precipitation_sum?.length ?? "unknown"}; first-day-mm=${data.daily?.precipitation_sum?.[0] ?? "unknown"}`
          : probe.name.includes("item near")
            ? `items=${data.features?.length ?? "unknown"}; first-id=${data.features?.[0]?.id ?? "none"}`
            : `collection=${data.id ?? "unknown"}`;
    } else if (probe.kind === "pdf" || probe.kind === "gpkg") {
      const data = Buffer.from(await response.arrayBuffer());
      valid = probe.check(data.toString("ascii", 0, 16));
      detail = `bytes=${data.length}`;
    } else {
      const data = await response.text();
      valid = probe.check(data);
      const lines = data.trimEnd().split(/\r?\n/);
      const columns = lines[0].split("\t");
      const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      const thuDucRows = lines.slice(1).filter((line) => normalize(line).includes("thu duc"));
      const dateIndex = columns.indexOf("Date");
      const locationIndex = columns.indexOf("Location name");
      const first = thuDucRows[0]?.split("\t") ?? [];
      detail = `rows=${lines.length - 1}; thu-duc-text-matches=${thuDucRows.length}; first-match-date=${first[dateIndex] ?? "none"}; first-match-location=${first[locationIndex] ?? "none"}; columns=${columns.join(" | ")}`;
    }
    return { name: probe.name, status: valid ? "verified" : "unexpected response", http: response.status, contentType, detail, url: probe.url };
  } catch (error) {
    return { name: probe.name, status: "failed", error: String(error), url: probe.url };
  }
}

const results = await Promise.all(probes.map(runProbe));
console.log(JSON.stringify({ checkedAt: new Date().toISOString(), results }, null, 2));
if (results.some((result) => result.status !== "verified")) process.exitCode = 1;
