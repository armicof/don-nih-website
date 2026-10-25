# Verifikasi versi web lokal

Tanggal: 25 Oktober 2026. Lingkungan yang dijalankan: Windows, Python 3.11.9, Node.js 22.20.0, npm 11.19.0. Browser E2E: Chromium melalui Playwright 1.56.1. Tidak memakai data atau layanan produksi.

## Hasil terakhir

| Pemeriksaan | Hasil |
|---|---|
| `python3 -m unittest discover -s tests -v` | **37 passed**, 10,125 detik, termasuk regresi batas ID numerik URL |
| `npm --prefix frontend run typecheck` | Lulus pada implementasi frontend; dijalankan ulang juga oleh build (`tsc --noEmit`) |
| `npm --prefix frontend run build` | Lulus; Vite 6.4.1 + TypeScript, dijalankan kembali dalam E2E |
| `npm --prefix frontend run test:e2e:typecheck` | Lulus; dijalankan dalam E2E |
| `npm --prefix frontend run test:e2e` | **4 passed**, 53,0 detik, satu worker tanpa retry |

Build terakhir menghasilkan JS sekitar 252,41 kB (gzip 76,91 kB) dan CSS 39,33 kB (gzip 9,25 kB), di luar aset gambar asli. Angka ini hasil build saat verifikasi, bukan batas performa atau pengukuran Lighthouse.

## Tes HTTP/database (37)

Lihat `tests/test_api.py`. Server HTTP dan SQLite baru dibuat setiap tes, lalu ditutup/dihapus. Cakupan meliputi:

- Pendaftaran, login gagal/berhasil, hash password/salt, role signup, cookie HttpOnly/SameSite/Secure, kedaluwarsa sesi, logout, rate limit.
- Penolakan endpoint admin untuk user biasa; kepemilikan favorit/keranjang/order; upaya memalsukan `user_id`, role, dan harga.
- Body JSON invalid/null/non-object, content type, header keamanan dan origin, request terlalu besar.
- Pencarian, kategori, topping wajib, ID tidak valid/duplikat, batas quantity, persistensi saat aplikasi dimuat ulang.
- Harga/total dihitung di server; checkout kosong/unavailable ditolak; rollback kegagalan database yang disimulasikan di tengah transaksi.
- Retry checkout idempoten, termasuk permintaan bersamaan yang menghasilkan tepat satu order.
- CRUD/arsip/restore menu dan topping; size/temperature tetap; snapshot order bertahan setelah perubahan katalog.
- State machine pesanan, penolakan expected status stale, timeline waktu riil, status pembayaran tetap PENDING.
- Profil dan upload avatar/menu, batas ukuran, MIME/signature, larangan upload menu untuk pelanggan.
- Migrasi idempoten; seed demo eksplisit/idempoten; katalog non-demo tidak ditimpa seed.

Tes menemukan penerimaan JSON `null` sebagai `{}`. Root cause diperbaiki dengan sentinel default body agar `null` ditolak. Kesalahan indentasi pada perubahan validasi ID sempat menggagalkan startup saat rerun; sudah diperbaiki sebelum seluruh tes di atas lulus. Tidak ada kegagalan tes yang sengaja diabaikan.

## Browser end-to-end (4)

`frontend/e2e/storefront.spec.ts` menjalankan dua skenario luas pada setiap viewport:

- Desktop: **1440 × 900**.
- Mobile/touch: **360 × 800**.

Runner membangun frontend, membuat database demo sementara, menjalankan backend nyata pada port acak, membuat admin dengan akun/password acak dan CLI, lalu menggunakan browser tanpa mock API. Built app dilayani Python, sehingga CSP, cookie, static asset, dan upload juga diuji.

Skenario guest memeriksa pencarian/kategori/empty state, original image, login gate, dialog Escape/focus return, overflow, dan batas input. Skenario pelanggan/admin memeriksa pendaftaran, favorit, pilihan ukuran/suhu/topping, kuantitas/hapus/reload cart, checkout, detail/history setelah reload, CRUD menu/topping, upload, polling transisi status dengan dua context pengguna, snapshot harga, profil/avatar, serta login ulang. Error runtime/CSP dan respons API tidak terduga menggagalkan tes.

Runner mengonfirmasi server/database/upload sementara dibersihkan setelah sukses. Kegagalan startup pada run sebelumnya juga menjalankan cleanup. Laporan HTML berada di `frontend/e2e/report/index.html` setelah tes (diabaikan Git). Panduan: `frontend/e2e/README.md`.



## Diagnostik editor yang masih tersisa

Zed masih melaporkan `Cannot find module '@vitejs/plugin-react'` pada `frontend/vite.config.ts`, sementara paket terpasang, typecheck aplikasi/config Node (`tsconfig.node.json`), dan build Vite semuanya lulus. Konfigurasi resolusi Bundler sudah eksplisit; tidak ditambahkan suppression atau workaround dependensi. Restart TypeScript language server merupakan langkah diagnosis editor berikutnya. Belum diklaim bahwa diagnostik editor tersebut hilang.

## Belum diverifikasi / bukan klaim hasil

- Tidak menjalankan Flutter analyzer/build atau mengubah sumber Flutter. Target verifikasi adalah aplikasi web baru.
- Tidak mengakses Supabase, Midtrans, email provider, atau data akun produksi. Tidak ada klaim interoperabilitas schema/RLS maupun sinkronisasi akun/data.
- Belum diuji pada browser Safari/Firefox, perangkat fisik, pembaca layar, atau audit aksesibilitas WCAG lengkap.
- Tidak ada benchmark beban, pentest, audit dependensi menyeluruh, Lighthouse, atau pengujian deployment publik/reverse proxy.
- Tidak menguji pembayaran uang nyata, refund, stok, ataupun email confirmation/reset; fitur tersebut memang tidak diimplementasikan.
- Snapshot sumber tidak menyertakan screenshot referensi resmi atau database asli; fidelitas visual dinilai dari kode/aset yang tersedia, bukan perbandingan pixel-perfect terhadap build mobile produksi.
