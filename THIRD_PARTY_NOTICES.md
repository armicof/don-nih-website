# Atribusi kode dan aset pihak ketiga

## Sumber aplikasi

Versi web ini diadaptasi dari aplikasi Flutter **Kedai Don.Nih!**:

- Repository: https://github.com/raffidevaa/don.nih
- Pemilik repository sumber: `raffidevaa`.
- Referensi audit: branch `main`, diunduh 25 Oktober 2026; commit snapshot tidak dicatat.
- Alur, model bisnis, warna, dan aset aplikasi sumber menjadi acuan. Audit serta perbedaan implementasi tersedia di [docs/SOURCE_AUDIT.md](docs/SOURCE_AUDIT.md).

Snapshot `mobile-source/` hanya salinan referensi lokal dan tidak disertakan dalam Git. Gambar berikut disalin dari `assets/images/` sumber ke `frontend/public/images/` agar aplikasi web dapat dijalankan tanpa snapshot tersebut:

- `LogoDonnih.png`
- `americano.png`
- `appletea.png`
- `caffelatte.png`
- `curry.png`
- `espresso.png`
- `menu_cappucino.png`
- `orderhistory.png`
- `pancake.png`
- `peachtea.png`

Tidak ditemukan berkas lisensi eksplisit pada snapshot yang diperiksa. Repository publik **tidak otomatis memberikan izin untuk redistribusi atau penggunaan komersial**. Dokumen atribusi ini bukan pemberian lisensi, dan tidak menggantikan izin pemegang hak. Tidak ditambahkan lisensi MIT atau lisensi lainnya atas nama pemilik sumber.

Sebelum mempublikasikan repository/aset secara terbuka, pastikan Anda memiliki izin yang diperlukan, atau ganti materi yang tidak memiliki izin redistribusi. Jika hak penggunaan belum jelas, jangan menganggap proyek ini sudah mendapat izin publikasi hanya karena lolos build dan tes.

## Dependensi perangkat lunak

Dependensi npm dicatat dalam `package.json`/`package-lock.json` root dan `frontend/package.json`/`frontend/package-lock.json`. Ketentuan lisensi masing-masing paket tetap berlaku. `node_modules/` tidak disertakan; pemasangan menggunakan lockfile. Tidak ada perubahan lisensi paket pihak ketiga melalui proyek ini.
