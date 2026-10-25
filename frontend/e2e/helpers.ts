import { expect, type Page } from '@playwright/test';

export async function go(page: Page, path: string) {
  await page.goto(`/#${path}`);
}

export async function readApi<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(`/api${path}`);
  expect(response.ok(), `${path}: ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json() as Promise<T>;
}

// Observe real network responses; no routes, interception, or API fixtures.
export async function mutation<T>(page: Page, path: string, method: string, action: () => Promise<unknown>, status = 200): Promise<T> {
  const [response] = await Promise.all([
    page.waitForResponse(response => new URL(response.url()).pathname === `/api${path}` && response.request().method() === method),
    action(),
  ]);
  expect(response.status(), `${method} ${path}: ${await response.text()}`).toBe(status);
  const headers = response.request().headers();
  expect(headers['x-requested-with']).toBe('donnih-web');
  expect(headers['content-type']).toContain('application/json');
  expect(headers.authorization).toBeUndefined();
  return response.json() as Promise<T>;
}

export async function login(page: Page, email: string, password: string, admin = false) {
  await go(page, '/login');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await mutation(page, '/auth/login', 'POST', () => page.getByRole('button', { name: 'Masuk', exact: true }).click());
  await expect(page).toHaveURL(admin ? /#\/admin\/orders$/ : /#\/menu$/);
}

export async function logout(page: Page) {
  await go(page, '/profile');
  await page.getByRole('button', { name: 'Keluar', exact: true }).click();
  await mutation(page, '/auth/logout', 'POST', () => page.getByRole('dialog').getByRole('button', { name: 'Keluar', exact: true }).click());
  await expect(page).toHaveURL(/#\/menu$/);
}

export async function noOverflow(page: Page) {
  await expect(page.locator('.loading, .skeleton')).toHaveCount(0);
  const dimensions = await page.evaluate(() => ({
    viewport: innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(dimensions.document, `Document overflow: ${JSON.stringify(dimensions)}`).toBeLessThanOrEqual(dimensions.viewport);
  expect(dimensions.body, `Body overflow: ${JSON.stringify(dimensions)}`).toBeLessThanOrEqual(dimensions.viewport);
  for (const dialog of await page.locator('dialog[open]').all()) {
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth + 1), 'Dialog horizontal overflow').toBeTruthy();
  }
}

export async function loadedImage(page: Page, alt: string) {
  const image = page.getByRole('img', { name: alt, exact: true });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
}

export function observeBrowser(page: Page, failures: string[]) {
  page.on('pageerror', error => failures.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error' && /Content Security Policy|Refused to|pattern attribute value/i.test(message.text())) failures.push(message.text());
  });
  page.on('response', response => {
    if (new URL(response.url()).pathname.startsWith('/api/') && response.status() >= 400) {
      failures.push(`${response.request().method()} ${response.url()} returned ${response.status()}`);
    }
  });
}
