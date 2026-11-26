# Kedai Don.Nih! — versi web full-stack

Adaptasi web dari [raffidevaa/don.nih](https://github.com/raffidevaa/don.nih). Identitas cokelat/krem, aset menu asli, pilihan ukuran/suhu, dan alur pelanggan/admin dipertahankan serta disesuaikan untuk web responsif. Snapshot Flutter `mobile-source/` hanya referensi lokal opsional, diabaikan Git, dan **tidak diperlukan** untuk install, build, atau menjalankan aplikasi setelah clone.

**Ini aplikasi lokal yang berfungsi, bukan koneksi ke data kedai produksi.** Katalog seed menggunakan nama/aset sumber, tetapi harga, deskripsi, dan extra topping adalah **contoh rekaan**. Tidak ada akun bawaan, transaksi uang, sinkronisasi Supabase, atau pembayaran Midtrans. Database menggunakan MongoDB yang ditentukan melalui `MONGODB_URI`.

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

- Node.js **22+**, npm, Python **3.11+**, dan MongoDB (lokal, Atlas, atau compatible service).
- Pasang backend dependency dengan `python -m pip install -r requirements.txt`.
- Internet hanya diperlukan untuk instalasi npm dan browser pengujian pertama kali. Aset/font aplikasi tidak bergantung CDN.

Semua perintah berikut dijalankan dari root proyek. Di Windows, gunakan `python`; di Linux/macOS biasanya `python3`.

## Jalankan lokal — satu server

1. Salin `.env.example` ke `.env` (opsional; nilai default sudah dapat digunakan):

   ```powershell
   Copy-Item .env.example .env
   ```

   Pada Linux/macOS gunakan `cp .env.example .env`.

2. Install dependency, bangun frontend, dan siapkan MongoDB beserta katalog **demo**:

   ```sh
   python -m pip install -r requirements.txt
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

Database name default: `PSOFP-db123`. Index dibuat saat startup. Gambar upload disimpan di MongoDB.

### Menyiapkan admin

Setelah mendaftarkan akun milik Anda lewat web, jalankan di terminal lain:

```sh
python -m backend.cli promote-admin --email email-anda@example.com
```

Ganti alamat contoh dengan email akun yang Anda daftarkan, lalu masuk ulang agar UI mengenali role admin. Alternatif membuat akun admin baru (password diminta tersembunyi, tidak melalui argumen CLI):

```sh
python -m backend.cli create-admin --email email-anda@example.com --username adminanda --name "Admin Kedai"
```

Tidak tersedia endpoint publik untuk menaikkan role. CLI memerlukan akses ke MongoDB. Jangan memberikan akses database/CLI kepada pengguna yang tidak dipercaya.

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
| `MONGODB_URI` | `mongodb://localhost:27017` | URI koneksi MongoDB; simpan kredensial hanya di backend |
| `MONGODB_DB_NAME` | `PSOFP-db123` | Nama database |
| `SESSION_HOURS` | `168` | Masa sesi 1–720 jam |
| `COOKIE_SECURE` | `false` | Gunakan `true` untuk HTTPS |
| `WEB_ORIGINS` | localhost/127.0.0.1 port 5173 dan 8000 | Origin browser yang boleh mengirim mutasi |

`.env` tidak masuk Git. Jangan masukkan URI MongoDB ke environment frontend. Untuk deploy, simpan URI pada konfigurasi environment AWS dan izinkan koneksi dari environment aplikasi.

## Arsitektur dan data

```text
frontend/src/       React + TypeScript, CSS responsif, routing hash
frontend/public/    Aset asli yang disalin dari sumber
backend/server.py  Flask app, cookie, proteksi request, static files
backend/app.py     API, validasi/otorisasi, harga, checkout, status
backend/db.py      MongoDB client, index, password hashing, seed eksplisit
backend/cli.py     Setup database dan provisioning admin
tests/test_api.py   Tes API (fixture SQLite lama perlu diselaraskan dengan MongoDB)
frontend/e2e/      Playwright dengan backend nyata + DB sementara
docs/              Audit sumber, kontrak API, hasil verifikasi
mobile-source/     Referensi lokal opsional (tidak masuk repository Git)
```

Frontend mengirim JSON ke API same-origin. Server menentukan pemilik data dari sesi, bukan `user_id` klien. Harga berupa integer Rupiah dan dihitung ulang dari katalog aktif saat keranjang dimuat/checkout. Tidak ada pajak, ongkir, diskon, atau stok karena tidak ditemukan aturannya dalam sumber.

Checkout menghitung harga, membuat order/detail/timeline, dan mengosongkan keranjang menggunakan operasi MongoDB. Kunci idempotensi unik per pengguna mengembalikan order yang sama pada retry. Nama, harga, gambar, dan topping disnapshot agar riwayat tidak berubah ketika katalog diedit. Item katalog diarsipkan alih-alih dihapus fisik.

**Pembayaran:** tunai di kasir adalah adaptasi label `Cash` di sumber. `payment_status` tetap `PENDING`, termasuk setelah pesanan `COMPLETED`; penyelesaian produksi bukan bukti uang diterima. Tidak ada tombol pelunasan, webhook, atau pembayaran online palsu.

Kontrak lengkap: [docs/API.md](docs/API.md). Pemetaan layar, temuan sumber, dan alasan perbedaan: [docs/SOURCE_AUDIT.md](docs/SOURCE_AUDIT.md).

## Pengujian

```sh
python -m compileall -q backend
npm --prefix frontend run typecheck
npm --prefix frontend run test:e2e:typecheck
npm --prefix frontend run build
```

API dan browser test fixtures saat ini masih membuat database SQLite, sehingga belum kompatibel dengan backend MongoDB. Workflow CI menjalankan syntax check Python, typechecks frontend, smoke test API terhadap MongoDB sementara, dan production build. Runtime API/E2E suites perlu dipindahkan ke MongoDB sebelum dapat dijalankan. Detail cakupan lama: [frontend/e2e/README.md](frontend/e2e/README.md).

Laporan [docs/VERIFICATION.md](docs/VERIFICATION.md) mencatat verifikasi versi SQLite sebelumnya dan bukan hasil verifikasi backend MongoDB saat ini.

## Repository GitHub

Panduan push pertama, pemeriksaan staging, dan daftar file yang harus disertakan ada di [docs/GITHUB.md](docs/GITHUB.md). Workflow `.github/workflows/cd.yaml` mendeploy ke EC2 melalui AWS Systems Manager (SSM) setelah workflow CI berhasil pada `main`; Anda juga dapat menjalankannya manual dari `main`. Siapkan GitHub secrets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, dan `AWS_INSTANCE_ID`, serta repository variables `AWS_REGION`, `EC2_APP_DIR`, dan `EC2_SERVICE_NAME`. Instance Ubuntu harus terdaftar di SSM, memiliki akses Git ke repository, Node.js, Python, dan service systemd Gunicorn yang sudah dikonfigurasi dengan environment MongoDB (`MONGODB_URI`, `MONGODB_DB_NAME`, `COOKIE_SECURE=true`, dan `WEB_ORIGINS`). Workflow memperbarui checkout di `EC2_APP_DIR` ke commit yang diuji CI, membangun frontend, lalu me-restart service.

`package.json` root menyediakan pintasan `npm run setup:frontend`, `npm run dev`, `npm run build`, `npm run typecheck`, dan `npm run test:e2e`. Paket aplikasi dan lockfile utama tetap berada di `frontend/`; `npm install` di root saja tidak menginstal aplikasi frontend. Kedua lockfile disertakan untuk mereproduksi dependensinya masing-masing.

Database, sesi, upload, `.env`, `node_modules`, hasil build, laporan browser, dan snapshot Flutter lokal diabaikan Git. `.env.example` adalah pengecualian yang harus berisi konfigurasi contoh aman saja. Untuk atribusi dan batas lisensi kode/aset sumber, lihat [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Backup, deployment, dan batas integrasi

- Gunakan backup MongoDB yang dikelola penyedia database dan uji pemulihannya secara berkala.
- Backend berjalan dengan Flask. `python -m backend.server` untuk lokal; deployment WSGI menggunakan Gunicorn (`backend.server:app`). Deployment EC2 menjalankan service systemd. Atur `MONGODB_URI`, `MONGODB_DB_NAME`, `COOKIE_SECURE=true`, dan `WEB_ORIGINS` di environment service, dan batasi allowlist MongoDB ke jaringan aplikasi.
- Rate limit auth lokal: maksimal 20 percobaan daftar/login per IP per 10 menit. Di belakang proxy, kode belum membaca forwarded IP; diperlukan konfigurasi proxy tepercaya sebelum produksi.
- Upload dibatasi 2 MB per gambar dan 200 MB per akun; MIME dan signature diperiksa. Tidak ada re-encoding, pemindaian malware, atau validasi dimensi gambar. Gambar bersifat publik melalui URL acak, seperti asumsi bucket publik pada sumber; jangan unggah dokumen sensitif. Avatar lama dibersihkan, gambar menu dipertahankan demi riwayat.
- Belum ada email confirmation/reset password, pembatalan/refund, stok, verifikasi pembayaran, atau Supabase Realtime. Pembaruan status menggunakan polling, bukan WebSocket.
- Backend menggunakan koneksi MongoDB langsung; aplikasi mengelola autentikasi dan sesi sendiri. Midtrans memerlukan credential server dan webhook terverifikasi jika kelak ditambahkan.
- Belum ada persyaratan deployment atau lisensi eksplisit yang ditemukan dalam snapshot sumber. Pastikan izin penggunaan kode/aset asli sebelum distribusi komersial.
