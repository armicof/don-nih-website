import { randomBytes, randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';
import type { Cart, Menu, Order, Topping, User } from '../src/types';
import { go, loadedImage, login, logout, mutation, noOverflow, observeBrowser, readApi } from './helpers';

const imageFile = fileURLToPath(new URL('../public/images/LogoDonnih.png', import.meta.url));
const paymentText = 'Pembayaran belum diverifikasi; bayar di kasir';

test('guest browsing, accessible dialogs, and backend-aligned input limits', async ({ page }, testInfo) => {
  const failures: string[] = [];
  observeBrowser(page, failures);
  const health = await readApi<{ demo_data: boolean; storage: string; online_payment: boolean }>(page, '/health');
  expect(health).toMatchObject({ demo_data: true, storage: 'sqlite', online_payment: false });
  await go(page, '/menu');
  await expect(page.getByRole('heading', { name: 'Menu pilihan', exact: true })).toBeVisible();
  await loadedImage(page, 'Caffè Latte');
  await noOverflow(page);
  await expect(page.locator(testInfo.project.name === 'mobile' ? '.bottom-nav' : '.sidebar')).toBeVisible();
  await page.getByRole('button', { name: 'Non-coffee', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Pilih Apple Tea', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pilih Caffè Latte', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Semua menu', exact: true }).click();
  const search = page.getByRole('textbox', { name: 'Cari menu', exact: true });
  await expect(search).toHaveAttribute('maxlength', '100');
  await search.fill('no-matching-menu-e2e');
  await expect(page.getByRole('heading', { name: 'Menu tidak ditemukan', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Hapus pencarian', exact: true }).click();
  const openDetail = page.getByRole('button', { name: 'Pilih Caffè Latte', exact: true });
  await openDetail.click();
  await expect(page.getByRole('radio', { name: /^Regular/ })).toBeChecked();
  await expect(page.getByRole('radio', { name: /^Cold/ })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Masuk untuk memesan', exact: true })).toBeEnabled();
  await noOverflow(page);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(openDetail).toBeFocused();
  await go(page, '/cart');
  await expect(page.getByRole('heading', { name: 'Satu langkah menuju favoritmu', exact: true })).toBeVisible();
  await noOverflow(page);
  await go(page, '/register');
  const username = page.getByLabel('Username', { exact: true });
  await expect(username).toHaveAttribute('minlength', '3');
  await expect(username).toHaveAttribute('maxlength', '30');
  await username.fill('nama.uji-pelanggan_1');
  expect(await username.evaluate((input: HTMLInputElement) => input.validity.patternMismatch)).toBe(false);
  await username.fill('nama tidak valid');
  expect(await username.evaluate((input: HTMLInputElement) => input.validity.patternMismatch)).toBe(true);
  await expect(page.getByLabel('Nama lengkap', { exact: true })).toHaveAttribute('minlength', '2');
  await expect(page.getByLabel('Nama lengkap', { exact: true })).toHaveAttribute('maxlength', '100');
  await expect(page.getByLabel('Nomor telepon', { exact: true })).toHaveAttribute('maxlength', '25');
  await expect(page.getByLabel('Nomor telepon', { exact: true })).not.toHaveAttribute('required');
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('minlength', '8');
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('maxlength', '128');
  await noOverflow(page);
  await go(page, '/login');
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('minlength', '8');
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('maxlength', '128');
  await noOverflow(page);
  expect(failures).toEqual([]);
});

test('real customer purchase, admin management, polling, and persisted profile', async ({ page, browser }, testInfo) => {
  const tag = randomUUID().replaceAll('-', '').slice(0, 12);
  const customer = {
    email: `customer-${tag}@example.test`,
    password: randomBytes(64).toString('hex'),
    fullname: `Pelanggan ${tag}`,
    username: `uji.${tag}-pelanggan`.padEnd(30, 'x'),
    phone_number: `+${'1'.repeat(24)}`,
  };
  const failures: string[] = [];
  observeBrowser(page, failures);
  const adminContext = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL,
    viewport: page.viewportSize(),
    isMobile: testInfo.project.name === 'mobile',
    hasTouch: testInfo.project.name === 'mobile',
    locale: 'id-ID', timezoneId: 'Asia/Jakarta',
  });
  const admin = await adminContext.newPage();
  observeBrowser(admin, failures);
  let order!: Order;
  let originalToppings!: Topping[];
  let unitPrice = 0;
  let latte!: Menu;
  try {
    await test.step('sign up through the browser, then logout and login with a real cookie', async () => {
      await go(page, '/register');
      await page.getByLabel('Nama lengkap', { exact: true }).fill(customer.fullname);
      await page.getByLabel('Username', { exact: true }).fill(customer.username);
      await page.getByLabel('Nomor telepon', { exact: true }).fill(customer.phone_number);
      await page.getByLabel('Email', { exact: true }).fill(customer.email);
      await page.getByLabel('Password', { exact: true }).fill(customer.password);
      const result = await mutation<{ user: User }>(page, '/auth/register', 'POST', () => page.getByRole('button', { name: 'Buat akun', exact: true }).click(), 201);
      expect(result.user).toMatchObject({ username: customer.username, role: 'user', phone_number: customer.phone_number });
      await expect(page).toHaveURL(/#\/menu$/);
      const cookie = (await page.context().cookies()).find(cookie => cookie.name === 'donnih_session');
      expect(cookie?.httpOnly).toBe(true);
      await logout(page);
      await login(page, customer.email, customer.password);
      await expect(page.getByRole('heading', { name: 'Welcome, Pelanggan!', exact: true })).toBeVisible();
    });

    await test.step('favorite persists, customizations reach the server, and cart quantity survives reload', async () => {
      latte = (await readApi<Menu[]>(page, '/menus')).find(menu => menu.name === 'Caffè Latte')!;
      expect(latte).toBeTruthy();
      await mutation(page, `/favorites/${latte.id}`, 'PUT', () => page.getByRole('button', { name: 'Simpan Caffè Latte ke favorit', exact: true }).click());
      await page.reload();
      await go(page, '/favorites');
      await expect(page.getByRole('button', { name: 'Hapus Caffè Latte dari favorit', exact: true })).toBeVisible();
      await mutation(page, `/favorites/${latte.id}`, 'DELETE', () => page.getByRole('button', { name: 'Hapus Caffè Latte dari favorit', exact: true }).click());
      await expect(page.getByRole('heading', { name: 'Belum ada menu favorit', exact: true })).toBeVisible();
      await go(page, '/menu');
      await mutation(page, `/favorites/${latte.id}`, 'PUT', () => page.getByRole('button', { name: 'Simpan Caffè Latte ke favorit', exact: true }).click());
      originalToppings = await readApi<Topping[]>(page, '/toppings');
      const extra = originalToppings.find(topping => topping.name === 'Extra Espresso')!;
      unitPrice = latte.price + originalToppings.filter(topping => [9, 12, extra.id].includes(topping.id)).reduce((sum, topping) => sum + topping.price, 0);
      await page.getByRole('button', { name: 'Pilih Caffè Latte', exact: true }).click();
      await page.getByRole('radio', { name: /^Large/ }).check();
      await page.getByRole('radio', { name: /^Hot/ }).check();
      await page.getByRole('checkbox', { name: /^Extra Espresso/ }).check();
      await noOverflow(page);
      const cart = await mutation<Cart>(page, '/cart', 'POST', () => page.getByRole('button', { name: 'Tambah ke keranjang', exact: true }).click(), 201);
      expect(cart.items[0].unit_price).toBe(unitPrice);
      expect(cart.items[0].toppings.map(topping => topping.id).sort((a, b) => a - b)).toEqual([9, 12, extra.id].sort((a, b) => a - b));
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.getByRole('button', { name: 'Pilih Pancake', exact: true }).click();
      await expect(page.getByRole('radio', { name: /^Regular/ })).toBeChecked();
      await expect(page.getByRole('radio', { name: /^Cold/ })).toBeChecked();
      const twoItems = await mutation<Cart>(page, '/cart', 'POST', () => page.getByRole('button', { name: 'Tambah ke keranjang', exact: true }).click(), 201);
      expect(twoItems.items).toHaveLength(2);
      await go(page, '/cart');
      const pancake = twoItems.items.find(item => item.name === 'Pancake')!;
      await mutation(page, `/cart/${pancake.id}`, 'DELETE', () => page.getByRole('button', { name: 'Hapus Pancake', exact: true }).click());
      await expect(page.getByRole('heading', { name: 'Pancake', exact: true })).toHaveCount(0);
      const changed = await mutation<Cart>(page, `/cart/${cart.items[0].id}`, 'PATCH', () => page.getByRole('button', { name: 'Tambah jumlah Caffè Latte', exact: true }).click());
      expect(changed.total).toBe(unitPrice * 2);
      await page.reload();
      await expect(page.getByLabel('Jumlah Caffè Latte', { exact: true })).toHaveText('2');
      await expect(page.locator('.cart-item-content')).toContainText('Large');
      await expect(page.locator('.cart-item-content')).toContainText('Hot');
      await noOverflow(page);
    });

    await test.step('checkout persists a real order and server timestamps across reload', async () => {
      await expect(page.getByText(paymentText, { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Lanjut checkout', exact: false }).click();
      await noOverflow(page);
      order = await mutation<Order>(page, '/orders', 'POST', () => page.getByRole('button', { name: 'Buat pesanan', exact: true }).click(), 201);
      expect(order).toMatchObject({ order_status: 'WAITING', payment_status: 'PENDING', payment_method: 'CASH', net_income: unitPrice * 2 });
      expect(order.items).toHaveLength(1);
      expect(order.items[0]).toMatchObject({ name: 'Caffè Latte', quantity: 2, price: unitPrice });
      expect(order.events.map(event => event.status)).toEqual(['WAITING']);
      await expect(page).toHaveURL(new RegExp(`#/orders/${order.id}$`));
      await expect(page.locator('.timeline li.reached')).toHaveCount(1);
      const timestamp = await page.locator('.timeline li.reached p').innerText();
      await page.reload();
      await expect(page.locator('.timeline li.reached p')).toHaveText(timestamp);
      expect((await readApi<Order>(page, `/orders/${order.id}`)).events).toEqual(order.events);
      expect((await readApi<Cart>(page, '/cart')).items).toHaveLength(0);
      await noOverflow(page);
      await login(admin, process.env.E2E_ADMIN_EMAIL!, process.env.E2E_ADMIN_PASSWORD!, true);
    });

    await test.step('admin creates, uploads, edits, archives, and restores a menu', async () => {
      const maxName = `Menu E2E ${tag} `.padEnd(100, 'm');
      const editedName = `Menu edit ${tag}`;
      await go(admin, '/admin/menus');
      await admin.getByRole('button', { name: 'Tambah menu', exact: true }).click();
      await expect(admin.getByLabel('Nama menu', { exact: true })).toHaveAttribute('maxlength', '100');
      const price = admin.getByLabel('Harga dasar (Rp)', { exact: true });
      await expect(price).toHaveAttribute('max', '100000000');
      await price.fill('100000001');
      expect(await price.evaluate((input: HTMLInputElement) => input.validity.rangeOverflow)).toBe(true);
      await price.fill('100000000');
      await admin.getByLabel('Nama menu', { exact: true }).fill(maxName);
      await expect(admin.getByLabel('Deskripsi', { exact: true })).not.toHaveAttribute('required');
      const upload = await mutation<{ url: string }>(admin, '/uploads', 'POST', () => admin.getByLabel('Unggah gambar menu', { exact: true }).setInputFiles(imageFile), 201);
      expect(upload.url).toMatch(/^\/uploads\//);
      await loadedImage(admin, 'Pratinjau gambar menu');
      await noOverflow(admin);
      const created = await mutation<Menu>(admin, '/admin/menus', 'POST', () => admin.getByRole('button', { name: 'Simpan menu', exact: true }).click(), 201);
      expect(created).toMatchObject({ name: maxName, price: 100000000, description: '', img: upload.url });
      await expect(admin.getByRole('heading', { name: maxName, exact: true })).toBeVisible();
      await noOverflow(admin);
      await admin.locator('.admin-menu-card').filter({ has: admin.getByRole('heading', { name: maxName, exact: true }) }).getByRole('button', { name: 'Edit', exact: true }).click();
      await admin.getByLabel('Nama menu', { exact: true }).fill(editedName);
      await admin.getByLabel('Harga dasar (Rp)', { exact: true }).fill('31000');
      await admin.getByLabel('Deskripsi', { exact: true }).fill('Menu E2E yang disimpan oleh server nyata.');
      await admin.getByRole('dialog').getByLabel('Kategori').selectOption('BREAKFAST');
      await mutation(admin, `/admin/menus/${created.id}`, 'PATCH', () => admin.getByRole('button', { name: 'Simpan menu', exact: true }).click());
      await admin.reload();
      await expect(admin.getByRole('heading', { name: editedName, exact: true })).toBeVisible();
      await admin.getByRole('button', { name: `Arsipkan ${editedName}`, exact: true }).click();
      await mutation(admin, `/admin/menus/${created.id}`, 'DELETE', () => admin.getByRole('dialog').getByRole('button', { name: 'Arsipkan', exact: true }).click());
      const archived = admin.locator('.admin-menu-card').filter({ has: admin.getByRole('heading', { name: editedName, exact: true }) });
      await expect(archived.getByText('Diarsipkan', { exact: true })).toBeVisible();
      expect((await readApi<Menu[]>(page, '/menus')).some(menu => menu.id === created.id)).toBe(false);
      await mutation(admin, `/admin/menus/${created.id}`, 'PATCH', () => archived.getByRole('button', { name: 'Aktifkan', exact: true }).click());
      expect((await readApi<Menu[]>(page, '/menus')).find(menu => menu.id === created.id)).toMatchObject({ active: true, name: editedName, category: 'BREAKFAST', price: 31000 });
      await noOverflow(admin);
    });

    await test.step('admin extra topping CRUD and size/temperature prices do not rewrite old orders', async () => {
      await go(admin, '/admin/toppings');
      await admin.getByRole('button', { name: 'Tambah topping', exact: true }).click();
      const maxName = `Topping E2E ${tag} `.padEnd(100, 't');
      const editedName = `Caramel E2E ${tag}`;
      await expect(admin.getByLabel('Nama pilihan', { exact: true })).toHaveAttribute('maxlength', '100');
      await expect(admin.getByLabel('Harga tambahan (Rp)', { exact: true })).toHaveAttribute('max', '100000000');
      await admin.getByLabel('Nama pilihan', { exact: true }).fill(maxName);
      await admin.getByLabel('Harga tambahan (Rp)', { exact: true }).fill('100000000');
      const topping = await mutation<Topping>(admin, '/admin/toppings', 'POST', () => admin.getByRole('button', { name: 'Simpan pilihan', exact: true }).click(), 201);
      expect(topping).toMatchObject({ name: maxName, price: 100000000, kind: 'extra' });
      await expect(admin.getByRole('heading', { name: maxName, exact: true })).toBeVisible();
      await noOverflow(admin);
      await admin.getByRole('button', { name: `Edit ${maxName}`, exact: true }).click();
      await admin.getByLabel('Nama pilihan', { exact: true }).fill(editedName);
      await admin.getByLabel('Harga tambahan (Rp)', { exact: true }).fill('4500');
      await mutation(admin, `/admin/toppings/${topping.id}`, 'PATCH', () => admin.getByRole('button', { name: 'Simpan pilihan', exact: true }).click());
      await admin.getByRole('button', { name: `Arsipkan topping ${editedName}`, exact: true }).click();
      await mutation(admin, `/admin/toppings/${topping.id}`, 'DELETE', () => admin.getByRole('dialog').getByRole('button', { name: 'Arsipkan', exact: true }).click());
      expect((await readApi<Topping[]>(page, '/toppings')).some(value => value.id === topping.id)).toBe(false);
      await mutation(admin, `/admin/toppings/${topping.id}`, 'PATCH', () => admin.getByRole('button', { name: `Aktifkan topping ${editedName}`, exact: true }).click());
      expect((await readApi<Topping[]>(page, '/toppings')).find(value => value.id === topping.id)).toMatchObject({ name: editedName, price: 4500, active: true });
      for (const id of [9, 12]) {
        const original = originalToppings.find(topping => topping.id === id)!;
        await admin.getByRole('button', { name: `Edit ${original.name}`, exact: true }).click();
        await expect(admin.getByLabel('Nama pilihan', { exact: true })).toHaveAttribute('readonly');
        await admin.getByLabel('Harga tambahan (Rp)', { exact: true }).fill(String(original.price + 1500));
        await mutation(admin, `/admin/toppings/${id}`, 'PATCH', () => admin.getByRole('button', { name: 'Simpan pilihan', exact: true }).click());
        const fixed = admin.locator('.admin-topping-row').filter({ has: admin.getByRole('heading', { name: original.name, exact: true }) });
        await expect(fixed.getByRole('button', { name: /Arsipkan/ })).toHaveCount(0);
        expect((await readApi<Topping[]>(page, '/toppings')).find(value => value.id === id)?.price).toBe(original.price + 1500);
        await admin.getByRole('button', { name: `Edit ${original.name}`, exact: true }).click();
        await admin.getByLabel('Harga tambahan (Rp)', { exact: true }).fill(String(original.price));
        await mutation(admin, `/admin/toppings/${id}`, 'PATCH', () => admin.getByRole('button', { name: 'Simpan pilihan', exact: true }).click());
      }
      expect((await readApi<Order>(page, `/orders/${order.id}`)).items).toEqual(order.items);
      await admin.reload();
      await expect(admin.getByRole('heading', { name: editedName, exact: true })).toBeVisible();
      await noOverflow(admin);
    });

    await test.step('sequential admin transitions reach customer detail/history through real five-second polling', async () => {
      await go(admin, '/admin/orders');
      await admin.getByLabel('Cari nomor pesanan atau pelanggan', { exact: true }).fill(String(order.id));
      await admin.locator('.order-toolbar').getByRole('button', { name: 'Menunggu konfirmasi', exact: true }).click();
      const adminCard = admin.locator('.order-card').filter({ has: admin.getByRole('heading', { name: `Pesanan #${order.id}`, exact: true }) });
      await expect(adminCard).toBeVisible();
      await noOverflow(admin);
      await adminCard.click();
      const transitions = [
        { action: 'Konfirmasi pesanan', status: 'CONFIRMED', label: 'Dikonfirmasi' },
        { action: 'Mulai siapkan pesanan', status: 'PROCESSED', label: 'Sedang disiapkan' },
        { action: 'Tandai pesanan selesai', status: 'COMPLETED', label: 'Selesai' },
      ];
      for (const [index, transition] of transitions.entries()) {
        if (index === 1) {
          await go(page, '/orders');
          await expect(page.getByRole('heading', { name: `Pesanan #${order.id}`, exact: true })).toBeVisible();
        }
        if (index === 2) {
          await page.locator('.order-card').filter({ has: page.getByRole('heading', { name: `Pesanan #${order.id}`, exact: true }) }).click();
          await expect(page.locator('.timeline li.current')).toContainText('Sedang disiapkan');
        }
        await admin.getByRole('button', { name: transition.action, exact: true }).click();
        const changed = await mutation<Order>(admin, `/admin/orders/${order.id}/status`, 'PATCH', () => admin.getByRole('button', { name: 'Ya, lanjutkan status', exact: true }).click());
        expect(changed.order_status).toBe(transition.status);
        expect(changed.events).toHaveLength(index + 2);
        // Do not navigate or reload the customer page after the mutation.
        // The frontend's own five-second poll must discover the server event.
        if (index === 1) {
          await expect(page.locator('.order-card .status')).toHaveText(transition.label, { timeout: 12000 });
        } else {
          await expect(page.locator('.timeline li.current strong')).toHaveText(transition.label, { timeout: 12000 });
        }
      }
      await expect(admin.getByText('Pesanan selesai — tidak ada aksi berikutnya.', { exact: true })).toBeVisible();
      await expect(page.locator('.timeline li.reached')).toHaveCount(4);
      await expect(page.getByText(paymentText, { exact: true })).toBeVisible();
      const completed = await readApi<Order>(page, `/orders/${order.id}`);
      expect(completed.events.map(event => event.status)).toEqual(['WAITING', 'CONFIRMED', 'PROCESSED', 'COMPLETED']);
      expect(completed.payment_status).toBe('PENDING');
      expect(completed.items).toEqual(order.items);
      expect(completed.events.every(event => !Number.isNaN(Date.parse(event.created_at)))).toBe(true);
      const times = await page.locator('.timeline li.reached p').allTextContents();
      await page.reload();
      await expect(page.locator('.timeline li.reached p')).toHaveText(times);
      expect((await readApi<Order>(page, `/orders/${order.id}`)).events).toEqual(completed.events);
      await noOverflow(page);
      await noOverflow(admin);
    });

    await test.step('profile name, phone, uploaded avatar, history, and favorites survive a new login', async () => {
      await go(page, '/profile');
      const fullname = `Nama baru ${tag}`;
      await page.getByLabel('Nama lengkap', { exact: true }).fill(fullname);
      await page.getByLabel('Nomor telepon', { exact: true }).fill('081234567890');
      await mutation(page, '/profile', 'PATCH', () => page.getByRole('button', { name: 'Simpan perubahan', exact: true }).click());
      const uploaded = await mutation<{ url: string }>(page, '/uploads', 'POST', () => page.getByLabel('Unggah foto profil', { exact: true }).setInputFiles(imageFile), 201);
      await loadedImage(page, `Foto profil ${fullname}`);
      expect(uploaded.url).toMatch(/^\/uploads\//);
      await page.reload();
      await expect(page.getByLabel('Nama lengkap', { exact: true })).toHaveValue(fullname);
      await expect(page.getByLabel('Nomor telepon', { exact: true })).toHaveValue('081234567890');
      await loadedImage(page, `Foto profil ${fullname}`);
      expect((await readApi<{ user: User }>(page, '/auth/me')).user.avatar_url).toBe(uploaded.url);
      await noOverflow(page);
      await logout(page);
      await login(page, customer.email, customer.password);
      await go(page, '/orders');
      await page.getByRole('button', { name: 'Selesai', exact: true }).click();
      await expect(page.getByRole('heading', { name: `Pesanan #${order.id}`, exact: true })).toBeVisible();
      await expect(page.locator('.order-card .status')).toHaveText('Selesai');
      await noOverflow(page);
      await go(page, '/favorites');
      await expect(page.getByRole('button', { name: 'Pilih Caffè Latte', exact: true })).toBeVisible();
      await go(page, '/cart');
      await expect(page.getByRole('heading', { name: 'Keranjang masih kosong', exact: true })).toBeVisible();
      await noOverflow(page);
      expect(failures).toEqual([]);
    });
  } finally {
    if (testInfo.status !== testInfo.expectedStatus) {
      await testInfo.attach('admin-screen', { body: await admin.screenshot({ fullPage: true }), contentType: 'image/png' }).catch(() => {});
    }
    await adminContext.close();
  }
});
