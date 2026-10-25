# Audit Sumber dan Keputusan Implementasi Lokal

## 1. Ruang lingkup dan asal sumber

- Snapshot lokal `mobile-source/` berasal dari branch publik `main`, diunduh pada **2026-10-25**. Commit ID tidak diketahui dan tidak diasumsikan. Folder referensi ini diabaikan Git; tidak tersedia dalam clone repository web dan tidak diperlukan untuk menjalankan aplikasi.
- Snapshot Flutter dipertahankan **tanpa perubahan**. Audit mencakup `lib/data/datasources/`, `lib/data/models/`, `lib/domain/entities/`, `lib/main.dart`, konfigurasi, serta logika backend yang berada langsung di halaman.
- Temuan berdasarkan pembacaan statis, bukan pengujian terhadap deployment Supabase. Kredensial dan schema backend terverifikasi tidak tersedia; DDL/migration, RLS, trigger, seed, serta storage policy tidak ditemukan dalam sumber yang diaudit.
- Direktori `mobile-source/web/` adalah scaffold target web Flutter. Routing aplikasi sudah ada di `lib/main.dart`; ini **bukan aplikasi backend terpisah**. Komentar `GET /menu` dan sejenisnya pada datasource juga bukan implementasi server HTTP tersendiri.
- Dokumen membedakan **perilaku sumber** dari **implementasi lokal**. Kontrol lokal di bawah telah diimplementasikan; cakupan pengujian dan batas klaimnya ada di [VERIFICATION.md](VERIFICATION.md). Audit sumber sendiri tetap merupakan pemeriksaan statis.

## 2. Keputusan arsitektur proyek induk

Implementasi lokal ditetapkan menggunakan:

| Komponen | Keputusan |
|---|---|
| Frontend | React + TypeScript + Vite, sebagai implementasi terpisah dari snapshot Flutter. |
| API | Python standard library; frontend mengakses API, bukan database secara langsung. |
| Database | SQLite lokal dengan schema migration berversi. |
| Aset | Menggunakan kembali aset asli dari `mobile-source/assets/`; tidak mengubah snapshot. |
| Katalog demo | Data lokal untuk demonstrasi. **Harga demo dibuat untuk kebutuhan demo, bukan harga asli kedai atau hasil pembacaan Supabase.** |

Alasan: aplikasi perlu dapat dijalankan lokal tanpa bergantung pada kredensial, schema, maupun layanan Supabase yang belum dapat diverifikasi. Ini merupakan penggantian backend untuk demo lokal, bukan replika deployment produksi.

**Tidak ada konektivitas maupun sinkronisasi Supabase produksi.** Akun, katalog, favorit, keranjang, dan pesanan lokal berdiri sendiri. Tidak ada impor otomatis pengguna/password, penyalinan transaksi produksi, atau sinkronisasi dua arah. Penggunaan aset asli tidak berarti data katalog atau harga demo berasal dari produksi.

## 3. Kontrak backend yang terlihat pada Flutter

Akses data menggunakan Supabase Auth, PostgREST, dan Storage secara langsung. Sebagian query berada di halaman, bukan seluruhnya melalui datasource.

Tipe berikut adalah ekspektasi klien, bukan hasil pemeriksaan DDL. ID pengguna berupa UUID string dari Auth; ID objek bisnis umumnya diperlakukan sebagai Dart `int`.

| Tabel | Kolom yang digunakan | Catatan |
|---|---|---|
| `users` | `id`, `email`, `username`, `fullname`, `phone_number`, `password`, `role`, `avatar_url` | Profil dikaitkan ke ID Auth; signup mengirim password mentah ke tabel ini. |
| `menus` | `id`, `name`, `price`, `topping`, `img`; `size` pada satu metode | `img` adalah path storage pada alur tambah menu. Model tidak membawa `img`; metode pencarian `size` tidak ditemukan dipanggil. |
| `toppings` | `id`, `name`, `price` | Mencakup tambahan, ukuran, dan suhu; model harga mengharuskan integer. |
| `menu_toppings` | `id`, `menu_id`, `toppings` | `toppings` disimpan sebagai string CSV ID, bukan relasi per topping. |
| `carts` | `id`, `user_id`, `menu_topping_id`, `total`, `is_purchased` | Alur keranjang utama; quantity tidak dipersistenkan. |
| `orders` | `id`, `user_id`, `order_status`, `payment_status`, `midtrans_order_id`, `net_income`, `payment_link`, `created_at`, `updated_at` | Total dan timestamp ditulis klien. |
| `order_details` | `id`, `order_id`, `menu_topping_id`, `quantity`, `price` | Harga satuan termasuk topping; detail dibuat satu per satu. |
| `favorites` | `id`, `user_id`, `menu_id` | ID dibuat dari milliseconds perangkat. |
| `cart` | `id`, `user_id`, `menu_id`, `quantity` | Alur tambah dari favorit memakai tabel singular ini, berbeda dari `carts`. |

Nested select mengasumsikan relasi `favorites → menus` dan `order_details → menu_toppings → menus`. Relasi pengguna serta constraint kepemilikan/keunikan tidak dapat dipastikan tanpa schema server. ID favorit berbasis milliseconds membutuhkan kapasitas lebih dari integer SQL 32-bit.

### Auth dan konfigurasi

- `main.dart` memuat `.env`, lalu `SUPABASE_URL` dan `SUPABASE_ANON_KEY`; tidak ada validasi konfigurasi yang memadai sebelum penggunaan nilai wajib.
- `.env` didaftarkan sebagai asset Flutter. Asset klien bukan tempat menyimpan rahasia: anon/publishable key boleh digunakan klien, **service-role key tidak boleh**.
- Login memakai `signInWithPassword()`, signup memakai `auth.signUp()` lalu insert profil, dan logout memakai `auth.signOut()`.
- Role `admin` dibaca dari `users.role` untuk menentukan navigasi. Navigasi bukan otorisasi server.
- Tidak ditemukan alur eksplisit konfirmasi email, pemulihan password, atau MFA. Jika konfirmasi email aktif di Supabase, signup dapat mengembalikan user tanpa session sehingga insert profil berpotensi ditolak RLS.
- `pubspec.yaml` memakai Dart `^3.9.2`; lockfile mengunci `supabase_flutter` pada `2.10.3`.

### Storage dan RPC

- Bucket `menu`: gambar menu memakai `menu/{id}_menu.{ext}`; helper juga mendukung `{folder}/{id}_{folder}.{ext}`.
- Bucket `avatars`: `{userId}/{milliseconds}.{ext}`; public URL disimpan ke `users.avatar_url`.
- `getPublicUrl()` menunjukkan harapan akses baca publik, bukan bukti bahwa bucket sudah dikonfigurasi publik.
- Sejumlah pembaca memaksa ekstensi `.png`, sedangkan upload mempertahankan ekstensi asli. Avatar selalu dikirim dengan MIME `image/jpeg`; avatar lama tidak dibersihkan oleh alur yang terlihat.
- **Tidak ditemukan pemanggilan RPC, Edge Functions, atau subscription Supabase Realtime.** Pembacaan order menggunakan query dan refresh, meskipun README menyebut realtime.

## 4. Aturan harga, checkout, dan status sumber

### Harga dan topping

```text
Harga satuan = harga menu + harga ukuran + harga suhu + total topping tambahan
Subtotal item = harga satuan × quantity
orders.net_income = jumlah subtotal item
```

Pemetaan ID topping di-hardcode: `Regular=11`, `Large=9`, `Cold=10`, `Hot=12`; default `Regular` dan `Cold`. Nominal surcharge dibaca dari database. Seed yang berbeda dapat mengubah makna ID tersebut.

- `CartDatasource` membaca harga, menghitungnya di klien, lalu menyimpan harga satuan di `carts.total`.
- Quantity hanya berada di memori dan kembali menjadi `1` ketika keranjang dimuat.
- Checkout memakai harga keranjang yang tersimpan, bukan menghitung ulang dari katalog saat checkout.
- Tidak terlihat aturan pajak, diskon, ongkir, service charge, stok, atau batas quantity maksimum.
- `net_income` secara implementasi adalah total order, bukan laba bersih atau penerimaan pembayaran terverifikasi.
- CSV topping tidak menjamin foreign key per topping. Parser gagal pada CSV kosong/malformed; datasource tidak menegakkan tepat satu ukuran/suhu atau kecocokan topping dengan menu.

### Checkout

Urutan sumber: insert order → insert setiap detail → update total → baca order → tandai cart purchased. Langkah-langkah merupakan request terpisah, tanpa transaksi atomik atau idempotency yang terlihat.

Order dimulai dengan `WAITING`, pembayaran `PENDING`, dan nilai string literal `'NULL'` untuk `midtrans_order_id` serta `payment_link`—bukan SQL `NULL`. `is_purchased=true` berarti order sudah dibuat, **bukan pembayaran lunas**.

### Status

Alur pemanggil admin: `WAITING → CONFIRMED → PROCESSED → COMPLETED`. Datasource menerima string status bebas, tanpa validasi transisi/status sebelumnya atau prasyarat pembayaran. `CANCELLED` dikenali daftar admin, tetapi alur pembatalan lengkap tidak tersedia; detail admin memetakan status tidak dikenal ke level awal.

Tidak ada audit trail transisi. Timeline admin membuat waktu sintetis dari `created_at + 1/3/38 menit`; waktu ini bukan kejadian backend yang tercatat. Timestamp order/update berasal dari perangkat.

**Midtrans belum terintegrasi:** tidak ditemukan pembuatan transaksi, payment link aktual, webhook, verifikasi signature, settlement, refund, atau rekonsiliasi. Label `Cash` pada detail bersifat statis, bukan field metode pembayaran persisten.

## 5. Pemetaan layar ke fungsi lokal

Pemetaan ini adalah cakupan fungsional, bukan janji menyalin widget Flutter atau mempertahankan URL secara identik. Path sumber di bawah relatif terhadap `mobile-source/lib/presentation/pages/`.

| Sumber / route Flutter | Fungsi yang dipertahankan pada implementasi lokal | Perubahan kontrak |
|---|---|---|
| `loadingscreen.dart`, `/`; bootstrap `main.dart` | Bootstrap dan pemeriksaan session | Tidak menginisialisasi Supabase; menggunakan session API lokal. |
| `login_page.dart`, `/login`; `sign_up_page.dart`, `/signup` | Login, registrasi, logout | Auth lokal; tidak memakai akun Supabase atau mengklaim email terverifikasi. |
| `homepage.dart`, `/home` | Katalog dan akses favorit | Katalog demo lokal; harga ditandai sebagai data demo. |
| `menu_detail.dart`, `/menu-detail` | Detail menu, ukuran, suhu, topping, tambah keranjang | Pilihan terstruktur dan validasi server; tidak bergantung pada ID seed Supabase. |
| `favourites_page.dart`, `/favourites` | Favorit milik pengguna | Tambah ke keranjang menggunakan kontrak keranjang tunggal, bukan `cart` terpisah. |
| `cart_page.dart`, `/cart` | Quantity, hapus item, checkout | Quantity persisten; harga otoritatif server; checkout atomik dan idempotent. |
| `order_status.dart`, `/order`, `/order-status`; `order_detail.dart`, `/order-detail` | Riwayat dan detail pesanan pengguna | Snapshot item dan event status persisten; akses dibatasi pemilik. |
| `profile_page.dart`, `/profile` | Profil pengguna dan logout | Profil dan upload avatar lokal dipersistenkan di SQLite; tidak menyinkronkan ke Supabase Storage. |
| `admin_homepage.dart`, `/admin/home`; `admin_add_menu_page.dart`; `admin_menu_detail_page.dart` | Pengelolaan katalog dan topping | Hak admin diperiksa API; perubahan harus benar-benar dipersistenkan. Save ukuran/suhu pada sumber masih lokal/TODO. |
| `admin_order_status.dart`, `/admin/orders`; `admin_order_detail.dart`, `/admin/order-detail` | Daftar dan perubahan status order | Validasi transisi oleh server dan pencatatan event aktual; tanpa timeline buatan. |

## 6. Deviasi keamanan dan integritas

Ketiadaan kebijakan server di repository **tidak membuktikan** deployment Supabase terbuka. Namun, keamanan sumber tidak dapat disimpulkan dari filter query atau tombol admin saja.

| Prioritas / temuan sumber | Dampak | Kontrak perbaikan implementasi lokal |
|---|---|---|
| **Kritis:** signup mengirim password mentah ke `users.password` | Jika diterima backend, password tersimpan di tabel aplikasi; pembacaan profil memakai `select()` tanpa pembatasan kolom. | Hash password dengan `scrypt` dan salt acak per pengguna; tidak menyimpan/mengembalikan password mentah. |
| **Tinggi:** harga, quantity, user ID, dan total dipercaya dari klien | Manipulasi harga/kepemilikan jika server tidak menegakkan aturan. | Identitas berasal dari session; server memvalidasi item/opsi/quantity dan menghitung harga dari katalog. Nilai uang memakai satuan rupiah integer. |
| **Tinggi:** checkout multi-request tanpa transaksi/idempotency | Order parsial, total salah, cart belum tertutup, atau order ganda saat retry. | Satu transaksi SQLite untuk validasi, harga, order/detail, event awal, dan perubahan cart; idempotency key terikat pengguna; retry key yang sama mengembalikan order terdahulu, bukan checkout baru. |
| **Tinggi:** admin hanya dibedakan pada navigasi; beberapa mutasi berdasarkan ID saja | Potensi akses lintas pengguna atau eskalasi hak jika policy tidak memadai. | Pemeriksaan ownership pada setiap akses objek dan role admin pada setiap operasi administratif; klien tidak boleh memilih/mengubah role sendiri. |
| **Tinggi:** hasil `users.insert()` tanpa `.select()` dibaca sebagai `inserted.id` dan properti objek | Signup dapat gagal setelah akun/profil telanjur dibuat. | Registrasi lokal konsisten dalam transaksi database; tidak meniru provisioning Auth/profil dua layanan. |
| **Tinggi:** favorit menulis `cart`, checkout membaca `carts` | Penambahan item tidak masuk alur checkout yang sama tanpa bridge backend. | Satu model keranjang untuk seluruh titik masuk. |
| **Sedang:** quantity sementara, nama item dibaca dari katalog terkini | Keranjang berubah setelah reload; riwayat berubah saat katalog diedit. | Quantity persisten dan snapshot nama, opsi, harga satuan, serta quantity pada detail order. |
| **Sedang:** status bebas dan timestamp sintetis/perangkat | Transisi tidak valid, konflik admin, dan riwayat tidak dapat diaudit. | State machine server; event berisi status, waktu server, dan pelaku, disimpan bersama perubahan status. |
| **Sedang:** tipe dan nullability model tidak konsisten | Runtime error, khususnya harga `double` yang di-cast ke `int` dan nilai order nullable. | Schema/API terdefinisi, validasi input, constraint dan migration SQLite; respons tidak memuat placeholder `'NULL'`. |
| **Sedang:** path/MIME storage tidak konsisten; write database/upload terpisah | Gambar hilang atau objek yatim. | Aset asli digunakan lokal; upload PNG/JPEG/WebP dibatasi, disimpan sebagai BLOB, dan profil diubah atomik. Tidak ada klaim kompatibilitas bucket produksi. |

Session API lokal menggunakan token acak opaque dengan cookie **HttpOnly**, expiry dan invalidasi logout; bukan token di `localStorage`. Gunakan `SameSite`, validasi origin/mitigasi CSRF untuk mutasi, dan `Secure` pada deployment HTTPS. Cookie `Secure` tidak diasumsikan bekerja untuk demo HTTP localhost. HttpOnly saja tidak menggantikan otorisasi atau perlindungan CSRF.

## 7. Batas implementasi lokal dan migrasi lanjutan

### Yang tidak tersedia

- Tidak ada pembayaran online, verifikasi pembayaran, webhook Midtrans, atau klaim bahwa order selesai berarti lunas.
- Tidak ada verifikasi email, konfirmasi email, maupun pemulihan akun/password melalui email.
- Tidak ada sinkronisasi produksi, Supabase Realtime, storage bucket produksi, atau migrasi otomatis identitas Auth.
- Tidak ada klaim production-ready hanya karena aplikasi dapat dijalankan lokal. Deployment publik tetap memerlukan TLS, pengelolaan rahasia, pembatasan percobaan login, backup, observabilitas, dan pengujian keamanan.

Schema SQLite dikelola melalui migration lokal berversi, dengan foreign key/constraint yang sesuai. Data demo dipisahkan dari migration schema; proses ini bukan migration untuk database Supabase produksi.

### Syarat migrasi ke Supabase

Migrasi bukan sekadar memasukkan URL dan key. Sebelum mengganti backend lokal diperlukan:

1. **Schema terverifikasi:** DDL, tipe uang/ID, nullability, foreign key, indeks, constraint, seed opsi, serta pemetaan data dan migration yang ditinjau.
2. **RLS dan hak kolom:** ownership seluruh tabel terkait; admin-only katalog/status; larangan perubahan role, total, dan status pembayaran oleh pengguna biasa. RLS baris saja tidak melindungi semua kolom sensitif.
3. **Supabase Auth:** strategi identitas, provisioning profil, session, redirect, kebijakan konfirmasi/recovery, dan migrasi akun yang aman. Hash lokal tidak diasumsikan kompatibel atau otomatis dapat diimpor.
4. **Storage:** bucket, public/private access, policy upload, validasi MIME/ukuran, path stabil, dan pembersihan objek.
5. **Checkout RPC transaksional:** identitas dari Auth, harga dihitung server, validasi opsi/quantity, idempotency, snapshot detail, penutupan cart, dan pencatatan event dalam transaksi. Keamanan fungsi/privilege harus ditinjau, bukan mempercayai payload klien.
6. **Pengujian integrasi:** akses lintas akun/admin, retry dan konkurensi checkout, transisi status, serta pemulihan kegagalan. Pembayaran merupakan integrasi terpisah bila kelak ditambahkan.

## 8. Referensi utama dan validasi audit

Tautan berikut mengarah ke branch `main` repository sumber dan dapat berubah setelah tanggal audit; bukan permalink commit snapshot.

- [Bootstrap Flutter](https://github.com/raffidevaa/don.nih/blob/main/lib/main.dart), [dependensi](https://github.com/raffidevaa/don.nih/blob/main/pubspec.yaml).
- [Auth](https://github.com/raffidevaa/don.nih/blob/main/lib/data/datasources/auth_datasource.dart), [keranjang](https://github.com/raffidevaa/don.nih/blob/main/lib/data/datasources/cart_datasource.dart), [order](https://github.com/raffidevaa/don.nih/blob/main/lib/data/datasources/order_datasource.dart), [admin order](https://github.com/raffidevaa/don.nih/blob/main/lib/data/datasources/admin_order_datasource.dart).
- [Detail order](https://github.com/raffidevaa/don.nih/blob/main/lib/data/datasources/order_detail_datasource.dart), [storage](https://github.com/raffidevaa/don.nih/blob/main/lib/data/datasources/storage_datasource.dart).
- [Aturan topping](https://github.com/raffidevaa/don.nih/blob/main/lib/presentation/pages/menu_detail.dart), [checkout](https://github.com/raffidevaa/don.nih/blob/main/lib/presentation/pages/cart_page.dart), [kontrak favorit](https://github.com/raffidevaa/don.nih/blob/main/lib/presentation/pages/favourites_page.dart).
- [Status admin](https://github.com/raffidevaa/don.nih/blob/main/lib/presentation/pages/admin_order_detail.dart), [profil/avatar](https://github.com/raffidevaa/don.nih/blob/main/lib/presentation/pages/profile_page.dart), [persistensi admin](https://github.com/raffidevaa/don.nih/blob/main/lib/presentation/pages/admin_menu_detail_page.dart).

Audit ini tidak menjalankan build/test Flutter, tidak memanggil layanan produksi, dan tidak memverifikasi schema atau policy deployment. Test otomatis untuk kontrak sumber tidak ditemukan. Snapshot tidak diubah. Implementasi backend lokal terpisah berada di `backend/`; hasil tesnya dicatat dalam [VERIFICATION.md](VERIFICATION.md).
