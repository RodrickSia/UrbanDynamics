// Browser regression against the real service; no mocking of solver responses.
const {
  chromium,
} = require("../.runtime/ui-check/node_modules/playwright-core");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
process.chdir(path.resolve(__dirname, ".."));
fs.mkdirSync("test-results", { recursive: true });
(async () => {
  const base = process.env.INTEGRATED_API_URL || "http://127.0.0.1:8001";
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const report = { base, checks: [] };
  try {
    const page = await browser.newPage({
      viewport: { width: 1360, height: 980 },
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(base + "/simulation/integrated");
    await page.waitForFunction(() =>
      document.querySelector("#status").textContent.includes("Sẵn sàng"),
    );
    assert.equal(await page.locator("#residents").inputValue(), "600");
    assert.equal(await page.locator("#floors").inputValue(), "12");
    report.checks.push(
      "Residential Thu Duc preset, no required technical coefficients",
    );
    await page.locator("#predict").click();
    await page.waitForFunction(
      () =>
        document
          .querySelector("#status")
          .textContent.includes("Đã tính và lưu"),
      {},
      { timeout: 180000 },
    );
    assert.equal(await page.locator("#impact tbody tr").count(), 22);
    assert.match(
      await page.locator("#engine-summary").textContent(),
      /SUMO 1.27.1/,
    );
    assert.match(await page.locator("#engine-summary").textContent(), /SWMM/);
    assert.match(await page.locator("#assessment").textContent(), /lợi ích/);
    report.checks.push(
      "Real prediction, 22 metric rows, benefit/pressure assessment and solver summaries",
    );
    const originalURL = page.url();
    await page.locator("#series").selectOption("water_m3");
    assert.equal(await page.locator("#chart polyline").count(), 3);
    await page.locator("#recommend").click();
    await page.waitForFunction(
      () =>
        document
          .querySelector("#status")
          .textContent.includes("Đã chạy lại và lưu"),
      {},
      { timeout: 240000 },
    );
    assert.equal(await page.locator(".suggestion").count(), 3);
    await page.locator(".suggestion button").first().click();
    assert.match(await page.locator("#state").inputValue(), /rec-/);
    assert.notEqual(page.url(), originalURL);
    report.checks.push(
      "Recommendations rerun, costs, Pareto and comparison state switch",
    );
    await page.screenshot({
      path: "test-results/integrated-desktop.png",
      fullPage: true,
    });
    await page.reload();
    await page.waitForFunction(() =>
      document.querySelector("#status").textContent.includes("Sẵn sàng"),
    );
    assert.equal(await page.locator(".suggestion").count(), 3);
    assert.equal(await page.locator("#residents").inputValue(), "600");
    const archive = await page.request.get(
      new URL(await page.locator("#artifacts").getAttribute("href"), base).href,
    );
    assert.equal(archive.status(), 200);
    report.checks.push("Saved run reopen and native engine ZIP download");
    await page.locator("#residents").fill("650");
    assert.equal(await page.locator("#results").isHidden(), true);
    assert.equal(new URL(page.url()).search, "");
    report.checks.push("Editing plan invalidates stale results and saved URL");
    await page.locator("summary").first().click();
    await page.locator("#plan-json").fill("{invalid");
    assert.equal(await page.locator("#predict").isDisabled(), true);
    await page.locator("#apply-json").click();
    assert.match(await page.locator("#status").getAttribute("class"), /error/);
    report.checks.push("Unapplied or invalid JSON cannot run");
    await page.locator("#preset").selectOption("residential");
    const beforeDraw = JSON.parse(
      await page.locator("#plan-json").inputValue(),
    );
    await page.locator("#draw-building").click();
    await page.locator("#map").scrollIntoViewIfNeeded();
    const box = await page.locator("#map").boundingBox();
    for (const [x, y] of [
      [270, 145],
      [330, 145],
      [330, 198],
      [270, 198],
    ]) {
      await page.mouse.click(
        box.x + (x / 600) * box.width,
        box.y + (y / 330) * box.height,
      );
    }
    await page.locator("#finish-draw").click();
    await page.waitForFunction(() =>
      document
        .querySelector("#status")
        .textContent.includes("Đã tính sân cứng"),
    );
    const afterDraw = JSON.parse(await page.locator("#plan-json").inputValue());
    assert.notDeepEqual(
      afterDraw.development.buildings[0].footprint,
      beforeDraw.development.buildings[0].footprint,
    );
    assert.notEqual(
      afterDraw.development.paved_m2,
      beforeDraw.development.paved_m2,
    );
    report.checks.push("Pointer-drawn footprint and API area rebalance");
    await page.locator("#preset").selectOption("office");
    assert.equal(await page.locator("#residents").inputValue(), "0");
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: "test-results/integrated-mobile.png",
      fullPage: true,
    });
    report.checks.push(
      "Nonresidential population separation and mobile no overflow",
    );
    assert.deepEqual(errors, []);
    report.checks.push("No JavaScript runtime errors");
    console.log(JSON.stringify(report, null, 2));
  } finally {
    fs.writeFileSync(
      "test-results/integrated-ui-report.json",
      JSON.stringify(report, null, 2),
    );
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
