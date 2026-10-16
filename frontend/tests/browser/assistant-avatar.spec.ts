import { expect, test } from '@playwright/test';

test('pixel assistant replies, recovers from failure, and stays inside the map when dragged', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#d9e6e9' } }],
  } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  await page.route('**/api/v1/zoning/plans', route => route.fulfill({ json: { plans: [] } }));
  await page.route('**/api/v1/agent/config', route => route.fulfill({ json: { enabled: true, model_configured: true, requires_token: false } }));
  await page.route('**/api/v1/agent/sessions', route => route.fulfill({ json: { session_id: 'avatar-test', messages: [] } }));
  let release: () => void = () => {};
  let fail = false;
  await page.route('**/api/v1/agent/chat', async route => {
    if (fail) return route.fulfill({ status: 503, json: { detail: 'Temporarily unavailable' } });
    await new Promise<void>(resolve => { release = resolve; });
    await route.fulfill({ json: { session_id: 'avatar-test', messages: [
      { role: 'user', content: 'Analyze this area' },
      { role: 'assistant', content: 'I can help you explore this neighborhood. **Population, land use and access** provide a useful starting point. Select an area on the map to compare available data and examine its planning possibilities.' },
    ] } });
  });
  await page.goto('/');
  const launcher = page.getByRole('button', { name: 'Planning assistant', exact: true });
  await launcher.hover();
  await expect(launcher.locator('.pixel-robot')).toHaveAttribute('data-state', 'completed');
  await launcher.click();
  const panel = page.getByRole('complementary', { name: 'Planning assistant' });
  await page.getByLabel('Message to planning assistant').fill('Analyze this area');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(panel.locator('.assistant-thinking .pixel-robot')).toHaveAttribute('data-state', 'thinking');
  release();
  const robot = panel.locator('.assistant-reply .pixel-robot');
  await expect(robot).toHaveAttribute('data-state', 'speaking');
  await expect(robot).toHaveAttribute('data-state', 'completed');
  await expect(robot).toHaveAttribute('data-state', 'idle');
  await expect(panel.locator('.assistant-thinking')).toHaveCount(0);
  const handle = page.getByRole('button', { name: 'Move chat' });
  const original = (await panel.boundingBox())!;
  const grip = (await handle.boundingBox())!;
  await page.mouse.move(grip.x + 40, grip.y + 16);
  await page.mouse.down(); await page.mouse.move(grip.x + 240, grip.y - 100, { steps: 8 }); await page.mouse.up();
  const moved = (await panel.boundingBox())!;
  expect(moved.x).toBeGreaterThan(original.x + 100);
  expect(moved.y).toBeGreaterThanOrEqual(8);
  await handle.focus(); await page.keyboard.press('Home');
  expect((await panel.boundingBox())!.x).toBe(original.x);
  await page.screenshot({ path: 'test-results/assistant-pixel-desktop.png' });
  fail = true;
  await page.getByLabel('Message to planning assistant').fill('Try again');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('Temporarily unavailable');
  await expect(panel.locator('[data-state=thinking]')).toHaveCount(0);
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    await handle.focus(); await page.keyboard.press('ArrowRight');
    const box = (await panel.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    expect(box.y + box.height).toBeLessThanOrEqual(800);
  }
  await page.setViewportSize({ width: 320, height: 800 });
  await page.screenshot({ path: 'test-results/assistant-pixel-mobile.png' });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await panel.getByRole('button', { name: 'New chat' }).click();
  fail = false;
  await page.getByLabel('Message to planning assistant').fill('Analyze this area');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(panel.locator('.assistant-thinking')).toBeVisible();
  release();
  await expect(robot).toHaveAttribute('data-state', 'idle');
  await expect(panel.locator('.assistant-bubble p')).toContainText('planning possibilities.');
  expect(await robot.locator('.robot-body').evaluate(node => getComputedStyle(node).animationName)).toBe('none');
  expect(errors).toEqual([]);
});
