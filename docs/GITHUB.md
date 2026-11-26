# Persiapan push dan deployment ke GitHub

Workflow `.github/workflows/deploy.yml` menjalankan pemeriksaan frontend/Python dan mendeploy ke EC2 melalui AWS Systems Manager (SSM) pada push ke `main`. Siapkan GitHub secrets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, dan `AWS_INSTANCE_ID`, serta repository variables `AWS_REGION`, `EC2_APP_DIR`, dan `EC2_SERVICE_NAME`. Instance Ubuntu perlu terdaftar di SSM, memiliki akses Git ke repository, Node.js, Python, dan service systemd yang memakai konfigurasi MongoDB aplikasi. GitHub Pages tidak dapat menjalankan API Python aplikasi ini.

## 1. Apa yang masuk repository

Sertakan:

- `backend/`: kode server dan setup collection/index MongoDB.
- `frontend/src/`, `frontend/public/`, konfigurasi Vite/TypeScript/Playwright, `frontend/e2e/` (kode tes saja).
- `tests/`, `docs/`, `README.md`, `THIRD_PARTY_NOTICES.md`.
- `package.json` dan `package-lock.json` root serta frontend. Dependensi root yang sudah ada dipertahankan; aplikasi frontend dipasang terpisah.
- `.gitignore`, `.gitattributes`, `.editorconfig`, dan `.env.example` yang sudah ditinjau dan bebas rahasia.

Jangan sertakan:

- `.env` atau konfigurasi lingkungan berisi rahasia.
- file konfigurasi berisi URI/kredensial MongoDB, akun, sesi login, gambar upload pribadi, atau backup database.
- `node_modules/`, `frontend/dist/`, cache Python, log, dan laporan/trace/screenshot E2E.
- `mobile-source/`: snapshot sumber lokal opsional. Aset yang diperlukan sudah tersedia di `frontend/public/images/`.

`.gitignore` bukan pemindai rahasia dan tidak menghapus file yang telanjur di-track atau masuk history. **Periksa `.env.example` secara manual sebelum commit**; pengecualian untuk template hanya aman bila isinya benar-benar contoh. Jangan gunakan `git add -f` untuk memaksa file rahasia/database masuk.

## 2. Jalankan pemeriksaan lokal

Dari root, dengan Node 22+ dan Python 3.11+:

```sh
npm --prefix frontend ci
python -m pip install -r requirements.txt
python -m compileall -q backend
npm --prefix frontend run typecheck
npm --prefix frontend run test:e2e:typecheck
npm --prefix frontend run build
```

API and browser suites in `tests/` and `frontend/e2e/` still use SQLite fixtures and are not compatible with the MongoDB backend. The workflow runs an API smoke check using a temporary MongoDB service instead. Migrate those fixtures before relying on the older suite instructions in `frontend/e2e/README.md`.

Kode/aset upstream tetap memiliki hak masing-masing. Baca `THIRD_PARTY_NOTICES.md`; lisensi sumber belum terverifikasi. Jangan menetapkan lisensi atau mempublikasikan materi pihak ketiga tanpa hak yang diperlukan.

## 3. Inisialisasi dan periksa staging

Jika direktori belum memiliki repository Git, jalankan **sendiri**:

```sh
git init -b main
git add .
git --no-pager diff --cached --check
git --no-pager diff --cached --stat
git --no-pager diff --cached
git --no-pager --no-optional-locks status --short
```

Jika sudah memiliki repository/branch, jangan menjalankan ulang langkah inisialisasi atau mengganti branch yang sedang dipakai tanpa memeriksa history.

Periksa bahwa direktori privat/generatif benar-benar diabaikan:

```sh
git --no-pager check-ignore -v data/donnih.sqlite3 node_modules frontend/node_modules frontend/dist mobile-source .env
```

Periksa daftar file staged, bukan hanya file yang terlihat di editor:

```sh
git --no-pager diff --cached --name-only
```

Jika file pribadi terlanjur staged, gunakan `git rm --cached -- PATH` untuk satu file atau `git rm -r --cached -- DIREKTORI` untuk direktori setelah mengganti placeholder dengan path yang benar. `--cached` mempertahankan file lokal. Jangan jalankan penghapusan massal terhadap index tanpa meninjau isinya. Jika rahasia sudah pernah di-push, cabut/rotasi rahasia terlebih dahulu; menghapus file dari commit berikutnya saja tidak cukup.

## 4. Commit dan pasang remote milik Anda

Buat repository **kosong** di akun/organisasi GitHub yang benar, tanpa auto-generated README, `.gitignore`, atau lisensi agar tidak menimbulkan history berbeda. Tentukan visibilitas berdasarkan izin kode/aset. Repository sumber `raffidevaa/don.nih` adalah referensi, **bukan otomatis remote tujuan proyek ini**.

Setelah meninjau staging:

```sh
git commit -m "Prepare Donnih web application for GitHub"
```

Salin URL repository baru dari GitHub, lalu gunakan:

```text
git remote add origin URL_REPOSITORY_ANDA
git remote -v
git push -u origin main
```

`URL_REPOSITORY_ANDA` adalah placeholder dokumentasi: ganti dengan URL sebenarnya, jangan tempel literal tersebut. Jika `origin` sudah ada, periksa terlebih dahulu; jangan menimpanya otomatis. Jika branch Anda bukan `main`, sesuaikan nama branch pada perintah push. Jangan memakai force push sebagai solusi history yang berbeda.

Gunakan Git Credential Manager/GitHub CLI/SSH untuk autentikasi. Jangan menyisipkan personal access token ke URL remote, kode, `.env.example`, atau command yang akan tersimpan di history shell.

## 5. Verifikasi setelah push

- Tinjau file melalui GitHub: source, aset, migration, dua lockfile, dan dokumentasi tersedia; database/secrets/build tidak ada.
- Pastikan tab Actions menjalankan workflow CI dan deployment SSM setelah push ke `main`.
- Clone ke direktori baru untuk menguji instruksi README. Folder `mobile-source/`, root `node_modules/`, dan database pribadi tidak diperlukan oleh aplikasi.
- Jalankan setup lokal seperti README dan buat akun/admin sendiri; tidak ada akun demo dengan password yang dibagikan.

## Batas pemeriksaan otomatis

Pencarian pola kredensial pada source code hanya pemeriksaan awal, bukan audit keamanan menyeluruh. Konfigurasi private yang diblokir editor tidak dibaca dalam persiapan ini. Pemeriksaan isi `.env.example`, keputusan lisensi/izin publikasi, identitas Git, dan remote tujuan tetap harus ditinjau pemilik proyek sebelum commit/push.
