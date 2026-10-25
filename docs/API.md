# Kontrak API lokal Don.Nih!

Base path `/api`, JSON UTF-8. Endpoint ini adalah implementasi lokal baru, **bukan endpoint Supabase produksi**. Respons sukses berupa objek/array langsung; kegagalan `{ "error": "pesan untuk pengguna" }`.

## Transport dan keamanan

- Cookie sesi `donnih_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`; TTL default 168 jam. Hanya hash token disimpan di database. Logout mencabut sesi aktif. `COOKIE_SECURE=true` wajib untuk deployment HTTPS.
- Semua mutasi (`POST`, `PUT`, `PATCH`, `DELETE`) memerlukan `Content-Type: application/json` dan `X-Requested-With: donnih-web`.
- Gunakan `{}` untuk mutasi tanpa payload; root JSON `null`, array, string/angka ditolak. Maksimal body 2.900.000 byte.
- Tidak ada CORS yang membuka akses lintas origin. Jika header `Origin` ada, nilainya harus cocok dengan `WEB_ORIGINS`; `Sec-Fetch-Site: cross-site` ditolak.
- Pengguna ditentukan dari sesi. `user_id`, role, harga, dan total yang dikirim klien tidak menjadi sumber otoritas. Role signup selalu `user`; pemberian role admin melalui CLI.
- Read publik: health, katalog, topping, pemeriksaan sesi. Semua endpoint lain memerlukan login; `/admin/*` memerlukan role admin di server.
- Status error utama: `400` validasi, `401` belum login, `403` izin/origin, `404` data tidak ada/tidak dimiliki, `409` konflik/checkout item tidak tersedia, `413` ukuran upload, `415` content type, `429` rate limit, `503` database sibuk.
- Semua harga integer Rupiah, tanpa pecahan. Timestamp UTC ISO 8601; frontend menampilkan zona browser.

## Auth dan profil

| Metode/path | Payload | Respons |
|---|---|---|
| `GET /health` | — | `{ok,storage:"sqlite",demo_data,online_payment:false}` |
| `GET /auth/me` | — | `{user: User|null}` |
| `POST /auth/register` | `{email,password,fullname,username,phone_number?}` | `201 {user}` + cookie |
| `POST /auth/login` | `{email,password}` | `{user}` + cookie baru |
| `POST /auth/logout` | `{}` | `{ok:true}` + cookie kedaluwarsa |
| `PATCH /profile` | `{fullname?,phone_number?}` | `{user}` |
| `POST /uploads` | `{kind:"avatar"|"menu",data_url}` | `201 {url}` |

`User`: `{id,email,username,fullname,phone_number,avatar_url,role}`. UUID untuk ID pengguna. Password tidak pernah dikembalikan; disimpan memakai scrypt dengan salt acak. Email dan username unik case-insensitive. Username 3–30 karakter `[A-Za-z0-9_.-]`; nama lengkap 2–100; password signup 8–128; email maksimum 254; telepon opsional maksimum 25 dan harus menyerupai nomor telepon jika terisi. Tidak ada konfirmasi email atau reset password lokal.

Unggahan menerima data URL base64 PNG/JPEG/WebP, memeriksa MIME dan signature file; maksimum 2 MB, kuota 200 MB/akun. `kind=menu` hanya admin. Avatar langsung memperbarui profil; gambar menu mengembalikan URL untuk dipakai saat menyimpan katalog. URL acak `/uploads/<uuid>.<ext>` dapat dibaca publik. Isi gambar disimpan sebagai BLOB SQLite. Validasi ini bukan pemindaian malware atau decoding penuh.

## Katalog dan favorit

| Metode/path | Payload/query | Respons |
|---|---|---|
| `GET /menus` | `?search=...&category=...` | `Menu[]`, aktif saja |
| `GET /toppings` | — | `Topping[]`, aktif saja |
| `GET /favorites` | — | `number[]` ID menu aktif milik pengguna |
| `PUT /favorites/:menuId` | `{}` | `{ok:true}`, idempoten |
| `DELETE /favorites/:menuId` | `{}` | `{ok:true}`, idempoten |

`Menu`: `{id,name,description,category,price,img,active}`. Kategori: `COFFEE`, `NON-COFFEE`, `DESSERT`, `BREAKFAST`, `MEAL`. Pencarian substring nama/deskripsi, bukan regex. Kategori disimpan eksplisit, berbeda dari inferensi nama pada Flutter.

`Topping`: `{id,name,price,kind,active}`. Kind: `extra`, `size`, `temperature`. ID bawaan mengikuti sumber:

| ID | Pilihan | Kind |
|---|---|---|
| 9 | Large | size |
| 11 | Regular | size |
| 10 | Cold | temperature |
| 12 | Hot | temperature |

Detail menu dibentuk dari objek katalog dan daftar topping; tidak perlu endpoint detail menu terpisah. Seperti layar sumber, setiap menu memiliki tepat satu ukuran dan suhu, termasuk makanan. Extra topping bersifat global karena tidak ada pemetaan ketersediaan per menu yang lengkap pada sumber.

## Keranjang dan checkout

| Metode/path | Payload | Respons |
|---|---|---|
| `GET /cart` | — | `Cart` |
| `POST /cart` | `{menu_id,topping_ids:[...],quantity?:1}` | `201 Cart` |
| `PATCH /cart/:id` | `{quantity}` | `Cart` |
| `DELETE /cart/:id` | `{}` | `Cart` |
| `POST /orders` | `{idempotency_key}` | `201 Order`, atau `200 Order` untuk retry |

`Cart`: `{items:[{id,menu_id,name,img,quantity,unit_price,total,toppings:Topping[],available}],total}`.

- Kuantitas 1–99 per baris; maksimal 100 baris per pengguna.
- Maksimal 50 ID topping unik, seluruhnya harus ada/aktif; tepat satu `size` dan satu `temperature`.
- Item tidak digabung otomatis, sehingga konfigurasi berbeda tetap terpisah.
- Harga satuan = harga menu aktif terkini + jumlah harga topping; total baris = harga satuan × kuantitas.
- Setiap load/mutasi keranjang mengembalikan harga katalog terkini. Harga dihitung ulang saat checkout; klien tidak dapat menetapkan harga atau totalnya. Tidak ada pajak, biaya tambahan tersembunyi, diskon, atau stok.
- Menu/topping yang diarsipkan membuat item keranjang `available=false`; checkout ditolak sampai item dihapus. Nilai ini tidak mengubah snapshot order lama.
- Keranjang kosong ditolak. Order, detail, event pertama, serta pengosongan keranjang berada dalam satu transaksi `BEGIN IMMEDIATE`; kegagalan di tengah di-rollback.
- `idempotency_key`: 16–100 karakter `[A-Za-z0-9_-]`, frontend memakai UUID acak. Unik per pengguna dan disimpan bersama order. Retry key yang sama mengembalikan order lama, tidak memproses keranjang baru. Gunakan key baru untuk checkout baru; pertahankan key saat respons jaringan tidak pasti.

Contoh payload penambahan (ID menu diambil dari katalog; ID 11/10 bawaan):

```json
{"menu_id":1,"topping_ids":[11,10],"quantity":2}
```

Contoh checkout:

```json
{"idempotency_key":"d964e31d-69c9-4848-ad57-815c849fa901"}
```

## Pesanan

| Metode/path | Akses | Respons/payload |
|---|---|---|
| `GET /orders` | Pengguna | `Order[]` milik sendiri, terbaru dahulu |
| `GET /orders/:id` | Pemilik/admin | `Order` |
| `GET /admin/orders` | Admin | Semua `Order[]` |
| `PATCH /admin/orders/:id/status` | Admin | `{expected_status,order_status}` → `Order` |

`Order`:

```text
{
  id, user_id, customer_name,
  order_status, payment_status: "PENDING", payment_method: "CASH",
  net_income, created_at, updated_at,
  items: [{id,order_id,menu_id,name,img,quantity,price,toppings:[{id,name,price}],total}],
  events: [{status,created_at}]
}
```

`price` adalah harga satuan lengkap; `net_income` mengikuti nama kolom sumber tetapi berarti total order, bukan laba atau penerimaan uang. Item dan nama pelanggan disnapshot. Event memakai waktu server, bukan perkiraan tahapan.

Transisi hanya `WAITING → CONFIRMED → PROCESSED → COMPLETED`. `expected_status` harus sama dengan database untuk menolak tab/admin yang stale. Tidak ada lompat, mundur, atau mutasi setelah completed. Contoh:

```json
{"expected_status":"WAITING","order_status":"CONFIRMED"}
```

Status pembayaran tidak berubah menjadi paid hanya karena pesanan selesai. Tidak tersedia payment link, webhook, atau endpoint settlement. Frontend melakukan polling lima detik, bukan realtime subscription Supabase.

## CRUD admin

| Metode/path | Payload | Respons |
|---|---|---|
| `GET /admin/menus` | — | Semua menu, termasuk arsip |
| `POST /admin/menus` | `{name,description?,category,price,img?}` | `201 Menu` |
| `PATCH /admin/menus/:id` | Field menu yang diubah dan/atau `{active:boolean}` | `Menu` |
| `DELETE /admin/menus/:id` | `{}` | `{ok:true}`, soft archive |
| `GET /admin/toppings` | — | Semua topping, termasuk arsip |
| `POST /admin/toppings` | `{name,price}` | `201 Topping`, kind extra |
| `PATCH /admin/toppings/:id` | `{name?,price?,active?}` | `Topping` |
| `DELETE /admin/toppings/:id` | `{}` | `{ok:true}`, archive extra |

Nama 2–100, deskripsi 0–1000, harga 0–100.000.000 Rupiah. Gambar menu harus aset lokal bawaan atau URL upload menu yang ada; URL eksternal tidak diterima. Pilihan size/temperature bawaan tidak dapat dihapus, dinonaktifkan, atau diganti namanya; harga dapat diperbarui. `active:true` memulihkan menu/extra topping arsip.

## Skema dan migrasi

`backend/migrations/001_initial.sql` mencakup `users`, `sessions`, `auth_attempts`, `menus`, `toppings`, `favorites`, `carts`, `cart_toppings`, `orders`, `order_details`, `order_events`, `uploads`, `metadata`. `schema_migrations` mencatat file migrasi yang sudah diterapkan. Foreign keys aktif, WAL aktif, busy timeout 15 detik.

Perbedaan dari sumber: tidak ada password plaintext; relasi topping keranjang dinormalisasi (bukan CSV), quantity disimpan, snapshot order dan event dibuat, katalog soft archive, timestamp dari server, tidak ada placeholder string `"NULL"` untuk payment link. Skema ini tidak boleh diterapkan langsung ke Supabase/PostgreSQL; lihat audit migrasi.
