# Kedai Don.Nih! — versi web full-stack

Adaptasi web dari [raffidevaa/don.nih](https://github.com/raffidevaa/don.nih). Identitas cokelat/krem, aset menu asli, pilihan ukuran/suhu, dan alur pelanggan/admin dipertahankan serta disesuaikan untuk web responsif. Snapshot Flutter `mobile-source/` hanya referensi lokal opsional, diabaikan Git, dan **tidak diperlukan** untuk install, build, atau menjalankan aplikasi setelah clone.

**Ini aplikasi lokal yang berfungsi, bukan koneksi ke data kedai produksi.** Katalog seed menggunakan nama/aset sumber, tetapi harga, deskripsi, dan extra topping adalah **contoh rekaan**. Tidak ada akun bawaan, transaksi uang, sinkronisasi Supabase, atau pembayaran Midtrans. Database dan akun yang Anda buat benar-benar disimpan di SQLite lokal.

## Fitur

- Jelajah katalog tanpa login; pencarian serta lima kategori.
- Daftar, masuk/keluar, sesi cookie HttpOnly; akses pelanggan/admin di server.
- Detail menu: Regular/Large, Cold/Hot, extra topping dengan kalkulasi harga.
- Favorit; keranjang dengan kuantitas persisten; checkout atomik dan aman terhadap retry identik.
- Riwayat/detail pesanan, snapshot item/harga/topping, dan timeline waktu sebenarnya.
- Status `WAITING → CONFIRMED → PROCESSED → COMPLETED`; polling setiap lima detik.
- Profil: nama, nomor telepon, unggah avatar PNG/JPEG/WebP.
- Admin: tambah/edit/arsipkan/aktifkan menu dan extra topping, gambar menu, harga ukuran/suhu, filter serta pembaruan pesanan.
- Navigasi desktop/mobile, dialog keyboard, fokus, loading, error, empty state, serta pemberitahuan sukses.

## Prasyarat

- Node.js **22+**, npm, Python **3.11+** (termasuk SQLite dan dukungan `hashlib.scrypt`).
- Backend menggunakan standard library Python; tidak perlu `pip install`, Docker, Flutter SDK, atau akun cloud.
- Internet hanya diperlukan untuk instalasi npm dan browser pengujian pertama kali. Aset/font aplikasi tidak bergantung CDN.

Semua perintah berikut dijalankan dari root proyek. Di Windows, gunakan `python`; di Linux/macOS biasanya `python3`.

## Jalankan lokal — satu server

1. Salin `.env.example` ke `.env` (opsional; nilai default sudah dapat digunakan):

   ```powershell
   Copy-Item .env.example .env
   ```

   Pada Linux/macOS gunakan `cp .env.example .env`.

2. Install, bangun frontend, dan siapkan database beserta katalog **demo**:

   ```sh
   npm --prefix frontend ci
   npm --prefix frontend run build
   python -m backend.cli init --demo
   ```

   Untuk katalog kosong, gunakan `python -m backend.cli init` tanpa `--demo`.
   Seed hanya dijalankan secara eksplisit, idempoten, dan menolak katalog nonkosong yang belum pernah di-seed. Server tidak mengisi katalog otomatis.

3. Jalankan:

   ```sh
   python -m backend.server
   ```

4. Buka **http://127.0.0.1:8000**. Daftar akun lewat web, pilih menu, lalu checkout. Hentikan server dengan Ctrl+C. Data tetap ada setelah restart.

Database default: `data/donnih.sqlite3`. Migrasi otomatis diterapkan saat startup. Gambar upload juga disimpan di database; tidak ada direktori upload tersembunyi atau cloud storage.

### Menyiapkan admin

Setelah mendaftarkan akun milik Anda lewat web, jalankan di terminal lain:

```sh
python -m backend.cli promote-admin --email email-anda@example.com
```

Ganti alamat contoh dengan email akun yang Anda daftarkan, lalu masuk ulang agar UI mengenali role admin. Alternatif membuat akun admin baru (password diminta tersembunyi, tidak melalui argumen CLI):

```sh
python -m backend.cli create-admin --email email-anda@example.com --username adminanda --name "Admin Kedai"
```

Tidak tersedia endpoint publik untuk menaikkan role. CLI memerlukan akses filesystem database. Jangan memberikan akses database/CLI kepada pengguna yang tidak dipercaya.

### Mode pengembangan dengan HMR

Terminal 1, dari root:

```sh
python -m backend.server
```

Terminal 2, dari root:

```sh
npm --prefix frontend run dev
```

Buka **http://127.0.0.1:5173**. Vite meneruskan `/api` dan `/uploads` ke `127.0.0.1:8000`; gambar asli dilayani dari `frontend/public/images`. Jika mengubah port backend, sesuaikan `frontend/vite.config.ts` dan `WEB_ORIGINS`. Jangan gunakan `vite preview` sebagai backend aplikasi; jalankan build lewat server Python di atas.

## Konfigurasi

| Variabel | Default | Kegunaan |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind lokal; jangan ubah ke publik tanpa hardening |
| `PORT` | `8000` | Port API dan built frontend |
| `DATABASE_PATH` | `data/donnih.sqlite3` | Path relatif terhadap direktori kerja, atau path absolut |
| `SESSION_HOURS` | `168` | Masa sesi 1–720 jam |
| `COOKIE_SECURE` | `false` | Gunakan `true` untuk HTTPS |
| `WEB_ORIGINS` | localhost/127.0.0.1 port 5173 dan 8000 | Origin browser yang boleh mengirim mutasi |

`.env` tidak masuk Git. Tidak ada service-role key, password produksi, secret frontend, atau kredensial Supabase yang perlu diisi untuk mode lokal. Menambahkan Supabase key saja **tidak** menghubungkan database ini ke Supabase.

## Arsitektur dan data

```text
frontend/src/       React + TypeScript, CSS responsif, routing hash
frontend/public/    Aset asli yang disalin dari sumber
backend/server.py  HTTP, cookie, proteksi request, static files
backend/app.py     API, validasi/otorisasi, harga, checkout, status
backend/db.py      Koneksi SQLite, migrasi, scrypt, seed eksplisit
backend/cli.py     Setup database dan provisioning admin
backend/migrations/001_initial.sql
                    Skema berversi; bukan migrasi Supabase produksi
tests/test_api.py   Tes HTTP/SQLite terisolasi
frontend/e2e/      Playwright dengan backend nyata + DB sementara
docs/              Audit sumber, kontrak API, hasil verifikasi
mobile-source/     Referensi lokal opsional (tidak masuk repository Git)
```

Frontend mengirim JSON ke API same-origin. Server menentukan pemilik data dari sesi, bukan `user_id` klien. Harga berupa integer Rupiah dan dihitung ulang dari katalog aktif saat keranjang dimuat/checkout. Tidak ada pajak, ongkir, diskon, atau stok karena tidak ditemukan aturannya dalam sumber.

Checkout menghitung harga, membuat order/detail/timeline, dan mengosongkan keranjang dalam satu transaksi SQLite. Kunci idempotensi unik per pengguna mengembalikan order yang sama pada retry. Nama, harga, gambar, dan topping disnapshot agar riwayat tidak berubah ketika katalog diedit. Item katalog diarsipkan alih-alih dihapus fisik.

**Pembayaran:** tunai di kasir adalah adaptasi label `Cash` di sumber. `payment_status` tetap `PENDING`, termasuk setelah pesanan `COMPLETED`; penyelesaian produksi bukan bukti uang diterima. Tidak ada tombol pelunasan, webhook, atau pembayaran online palsu.

Kontrak lengkap: [docs/API.md](docs/API.md). Pemetaan layar, temuan sumber, dan alasan perbedaan: [docs/SOURCE_AUDIT.md](docs/SOURCE_AUDIT.md).

## Pengujian

```sh
python -m unittest discover -s tests -v
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run test:e2e:install
npm --prefix frontend run test:e2e
```

Tes API menggunakan database sementara. E2E membangun frontend, menjalankan server nyata pada port sementara, membuat akun acak, menjalankan desktop/mobile Chromium, lalu membersihkan server/database. Tidak membuka database pribadi di `data/`. Unduhan browser hanya diperlukan sekali. Detail browser override dan laporan: [frontend/e2e/README.md](frontend/e2e/README.md).

Hasil terakhir dan cakupan/batas verifikasi: [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Repository GitHub

Panduan push pertama, pemeriksaan staging, dan daftar file yang harus disertakan ada di [docs/GITHUB.md](docs/GITHUB.md). **Tidak ada konfigurasi CI/CD**; pemeriksaan dijalankan manual dengan perintah di atas. Mempublikasikan source code tidak otomatis menjalankan backend atau database di GitHub Pages.

`package.json` root menyediakan pintasan `npm run setup:frontend`, `npm run dev`, `npm run build`, `npm run typecheck`, dan `npm run test:e2e`. Paket aplikasi dan lockfile utama tetap berada di `frontend/`; `npm install` di root saja tidak menginstal aplikasi frontend. Kedua lockfile disertakan untuk mereproduksi dependensinya masing-masing.

Database, sesi, upload, `.env`, `node_modules`, hasil build, laporan browser, dan snapshot Flutter lokal diabaikan Git. `.env.example` adalah pengecualian yang harus berisi konfigurasi contoh aman saja. Untuk atribusi dan batas lisensi kode/aset sumber, lihat [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Backup, deployment, dan batas integrasi

- Untuk backup lokal sederhana, hentikan server terlebih dahulu, kemudian salin database beserta file `-wal`/`-shm` jika masih ada. Untuk backup saat aplikasi aktif gunakan SQLite backup API; jangan menyalin file utama saja ketika WAL aktif.
- Build dapat dilayani server Python dengan satu origin, tetapi **`http.server` standard library ini ditujukan untuk lokal, bukan server publik production-ready**. Sebelum deployment publik: gunakan server produksi/reverse proxy HTTPS, cookie Secure, origin eksplisit, pembatasan koneksi/request, observabilitas, backup/restore, dan audit keamanan. Jangan mengekspos Vite dev server.
- Rate limit auth lokal: maksimal 20 percobaan daftar/login per IP per 10 menit. Di belakang proxy, kode belum membaca forwarded IP; diperlukan konfigurasi proxy tepercaya sebelum produksi.
- Upload dibatasi 2 MB per gambar dan 200 MB per akun; MIME dan signature diperiksa. Tidak ada re-encoding, pemindaian malware, atau validasi dimensi gambar. Gambar bersifat publik melalui URL acak, seperti asumsi bucket publik pada sumber; jangan unggah dokumen sensitif. Avatar lama dibersihkan, gambar menu dipertahankan demi riwayat.
- Belum ada email confirmation/reset password, pembatalan/refund, stok, verifikasi pembayaran, atau Supabase Realtime. Pembaruan status menggunakan polling, bukan WebSocket.
- Repository sumber tidak menyertakan schema/RLS/trigger/storage policy Supabase. Migrasi ke Supabase memerlukan verifikasi skema, Auth, ownership/RLS, storage policy, dan operasi checkout atomik server-side; data/akun lokal tidak otomatis bermigrasi. Midtrans memerlukan credential server dan webhook terverifikasi jika kelak ditambahkan.
- Belum ada persyaratan deployment atau lisensi eksplisit yang ditemukan dalam snapshot sumber. Pastikan izin penggunaan kode/aset asli sebelum distribusi komersial.
