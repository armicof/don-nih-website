# ☕ Kedai Don.Nih!

Kedai Don.Nih! adalah aplikasi point of sale berbasis web untuk kedai kopi. Pelanggan dapat menjelajahi menu, menyesuaikan pesanan, lalu melakukan checkout. Admin mengelola katalog dan memperbarui status pesanan melalui dashboard.

## 📌 Fitur

- Registrasi, login, logout, dan profil pengguna.
- Katalog menu dengan pencarian dan kategori.
- Detail menu dengan pilihan ukuran, suhu, dan topping.
- Favorit dan keranjang yang tersimpan.
- Checkout dengan harga yang dihitung di server dan perlindungan retry menggunakan idempotency key.
- Riwayat dan detail pesanan beserta statusnya.
- Upload foto profil dan gambar menu.
- Dashboard admin untuk mengelola menu, topping, dan status pesanan.

> Pembayaran online belum tersedia. Pelanggan membayar di kasir.

## 🧰 Teknologi

| Bagian | Teknologi |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend dan API | Python, Flask |
| Database | MongoDB |
| Pengujian browser | Playwright |

## 🚀 Menjalankan secara lokal

### Prasyarat

- Python 3.11 atau lebih baru.
- Node.js 22 atau lebih baru dan npm.
- MongoDB lokal atau MongoDB Atlas yang dapat diakses.

### 1. Clone dan siapkan konfigurasi

```sh
git clone https://github.com/armicof/don-nih-website.git
cd don-nih-website
```

Salin `.env.example` menjadi `.env`:

```sh
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Lalu isi alamat MongoDB. Contoh konfigurasi untuk MongoDB lokal:

```dotenv
HOST=127.0.0.1
PORT=8000
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DB_NAME=donnih_local
SESSION_HOURS=168
COOKIE_SECURE=false
WEB_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000
```

Jangan commit `.env` atau kredensial database. Untuk MongoDB Atlas, gunakan connection string dari project Anda dan simpan dengan aman.

### 2. Instal dependensi backend

Buat dan aktifkan virtual environment, lalu instal paket Python:

```sh
python -m venv .venv
```

Aktifkan environment:

```sh
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Kemudian jalankan:

```sh
python -m pip install -r requirements.txt
```

### 3. Inisialisasi database

Perintah ini membuat collection dan index yang diperlukan serta mengisi katalog contoh:

```sh
python -m backend.cli init --demo
```

Data demo hanya untuk pengembangan. Untuk menyiapkan database tanpa katalog contoh, jalankan `python -m backend.cli init`.

### 4. Buat akun admin

```sh
python -m backend.cli create-admin --email admin@example.com --username admin --name "Admin Kedai"
```

Masukkan password saat diminta. Password tidak ditampilkan di terminal.

### 5. Instal dependensi frontend

Dari direktori root repository:

```sh
npm --prefix frontend ci
```

### 6. Jalankan aplikasi

Jalankan backend dan frontend pada dua terminal terpisah. Aktifkan virtual environment di terminal backend.

Terminal pertama:

```sh
python -m backend.server
```

Terminal kedua:

```sh
npm run dev
```

Buka alamat yang ditampilkan Vite, biasanya [http://localhost:5173](http://localhost:5173). Vite meneruskan permintaan API dan gambar upload ke backend lokal pada port 8000.

Untuk membangun frontend produksi dan menyajikannya melalui backend, jalankan:

```sh
npm run build
python -m backend.server
```

Lalu buka [http://localhost:8000](http://localhost:8000).

## 🧪 Pemeriksaan

Tes integrasi backend memerlukan MongoDB yang dapat diakses melalui `MONGODB_URI`:

```sh
python -m unittest discover -s tests -p "test_*.py" -v
```

Pemeriksaan frontend dan browser tersedia melalui `npm run typecheck`, `npm run build`, dan `npm run test:e2e`. Untuk pertama kali menjalankan tes browser, instal Chromium dengan `npm run test:e2e:install`.

## 📁 Struktur proyek

```text
.
├── backend/
│   ├── app.py              # Endpoint API, autentikasi, checkout, dan aturan bisnis
│   ├── cli.py              # Inisialisasi database dan pengelolaan akun admin
│   ├── db.py               # Koneksi MongoDB, index, dan data demo
│   └── server.py           # Server Flask dan penyajian frontend hasil build
├── frontend/
│   ├── e2e/                # Skenario end-to-end Playwright
│   ├── public/             # Aset statis
│   └── src/                # Kode React dan TypeScript
├── tests/                  # Tes integrasi API
├── docs/                   # Dokumentasi API, verifikasi, dan deployment
├── .env.example            # Template konfigurasi lokal
└── README.md
```

## 📚 Dokumentasi

- [Kontrak API](docs/API.md)
- [Verifikasi dan pemeriksaan](docs/VERIFICATION.md)
- [Panduan GitHub dan deployment](docs/GITHUB.md)
- [Pemberitahuan lisensi pihak ketiga](THIRD_PARTY_NOTICES.md)

## ℹ️ Catatan

- Akun yang dibuat melalui registrasi memiliki peran pelanggan. Buat akun admin menggunakan CLI di atas, atau promosikan akun yang sudah ada dengan `python -m backend.cli promote-admin --email alamat@email.com`.
- Pada deployment HTTPS, atur `COOKIE_SECURE=true` dan gunakan nilai `WEB_ORIGINS` yang sesuai dengan domain aplikasi.
- Jangan gunakan katalog demo sebagai daftar harga produksi.
