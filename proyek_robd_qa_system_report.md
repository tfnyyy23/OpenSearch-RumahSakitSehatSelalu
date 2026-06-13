# Laporan Tugas Proyek Rekayasa Basis Data (ROBD)
## QA System Analisis Biaya Operasional – Rumah Sakit Sehat Selalu

---

## 1. Konteks Proyek & Latar Belakang
Laporan ini disusun sebagai dokumentasi tugas mata kuliah **Rekayasa Basis Data (ROBD) Semester 6, Telkom University**. 

Proyek ini bertujuan membangun **Question Answering (QA) System** cerdas berbasis AI untuk menganalisis dan mengontrol **Biaya Operasional Rumah Sakit Sehat Selalu**. Sistem menggunakan **OpenSearch** sebagai database pencarian/agregasi berkinerja tinggi atas data tagihan terdenormalisasi, dan model **Gemini 1.5 Flash (atau Gemini 3.5 Flash)** sebagai intelligence layer untuk memproses maksud pertanyaan (intent parsing) serta merumuskan wawasan keuangan (insight generation) dalam Bahasa Indonesia.

---

## 2. Arsitektur Sistem

Sistem dideploy secara mandiri menggunakan teknologi containerization (Docker Compose) dengan alur data sebagai berikut:

```
                  [ User Browser (Frontend Chat UI) ]
                                  ↓
                        HTTP Port 3000 (Nginx)
                                  ↓
                       HTTP Port 8000 (FastAPI)
                       [ intelligence layer ]
                                  ↓
         ┌────────────────────────┴────────────────────────┐
         ↓                                                 ↓
  Gemini API (HTTPS)                               OpenSearch Node (Port 9200)
  - Intent Parsing                                 - Agregasi Finansial
  - Response Formatting                            - Query data tagihan_operasional
```

- **Frontend**: Halaman web statis murni (HTML5, CSS, dan Javascript murni) yang disajikan oleh Nginx di port `3000`.
- **Reverse Proxy**: Nginx mem-proxy request `/api/*` ke backend FastAPI untuk menghindari isu CORS di tingkat produksi.
- **Backend**: FastAPI (Python) yang berjalan di port `8000`, menyediakan antarmuka REST API `/api/health`, `/api/stats`, dan `/api/ask`.
- **Database**: OpenSearch Node v2.13.0 yang berjalan di port `9200` dengan security plugin dinonaktifkan untuk mempermudah koneksi sandbox lokal.

---

## 3. Hasil Audit Proyek (Daftar Masalah Awal)

Sebelum perbaikan dilakukan, ditemukan beberapa masalah kritis (logic error, dead code, dan integrasi yang rusak):

1. **Dockerfile Backend Salah Kamar (Outdated)**: 
   Dockerfile lama hanya menyalin file legacy `qa_system_api.py` dan menjalankannya. Ini menyebabkan container menjalankan API lama berbasis Claude AI (Anthropic) yang tidak mendukung Gemini, tidak modular, dan menggunakan index lama (`rumah_sakit`).
2. **Reverse Proxy Nginx Mismatch**:
   Konfigurasi `nginx.conf` memiliki trailing slash pada `proxy_pass http://qa-backend:8000/;` yang memotong prefix `/api/`. Akibatnya, request `/api/health` dipotong menjadi `/health` di backend, menyebabkan error `404 Not Found` karena backend modular mengonfigurasi rute dengan prefix `/api`.
3. **Ketidaksesuaian Struktur Index**:
   Backend baru mengasumsikan data diindeks ke dalam flat index bernama `tagihan_operasional` (1.500 data tagihan denormalisasi), namun loader database lama (`load_data_opensearch.py`) memasukkan data terpisah berdasarkan tipe dokumen (`dokter`, `pasien`, `registrasi`, `tagihan`) ke index `rumah_sakit`.
4. **Masalah Case-Sensitivity OpenSearch**:
   OpenSearch mencocokkan filter `term` secara case-sensitive pada field `keyword`. Karena Gemini mengekstrak nilai filter dengan casing bervariasi (misal: "rawat inap" lowercase), pencarian gagal karena di database bernilai "Rawat Inap".
5. **Ketiadaan AI Guardrail**:
   Sistem akan mengalami error atau memaksakan pencarian database yang salah jika pengguna mengajukan pertanyaan di luar lingkup keuangan rumah sakit (misal: nasihat medis atau sapaan kasual).

---

## 4. Perbaikan & Penambahan Fitur Baru

### A. Konfigurasi Docker & Infrastruktur
- **Upgrade OpenSearch**: Meningkatkan image OpenSearch dan Dashboards ke versi **`2.13.0`** di `docker-compose.yml`.
- **Konfigurasi Gemini**: Mengganti variabel env `ANTHROPIC_API_KEY` menjadi `GEMINI_API_KEY`.
- **Reverse Proxy Fix**: Memperbaiki `nginx.conf` dengan menghapus trailing slash: `proxy_pass http://qa-backend:8000;`.
- **Dockerfile Fix**: Mengubah salinan file menjadi `. /app/backend/` dan mematangkan entry point perintah startup ke `backend.main:app`.

### B. Penyempurnaan Backend (FastAPI)
- **Implementasi AI Guardrail (Scope Enforcement)**:
  Memperbarui intent parser Gemini (`gemini_client.py`) untuk mendeteksi pertanyaan di luar konteks analitik biaya rumah sakit dan mengklasifikasikannya sebagai tipe `"out_of_scope"`. Backend mendeteksi tipe ini, **melewati query OpenSearch**, dan langsung menyajikan penolakan sopan serta saran 3 contoh pertanyaan finansial yang valid.
- **Normalisasi Nilai Filter (Case Normalization)**:
  Menambahkan utilitas di `opensearch_client.py` untuk menyelaraskan casing kata kunci filter secara dinamis (misal: memaksa `BPJS` menjadi kapital penuh, `THT` menjadi kapital penuh, `status_kunjungan` menjadi lowercase, dan poli/spesialisasi menjadi Title Case).
- **Endpoint Stats Dinamis (`GET /api/stats`)**:
  Menyajikan endpoint untuk menghitung data aktual database secara realtime melalui query *cardinality aggregation* (menghitung jumlah dokter unik, pasien unik, registrasi unik, dan total tagihan) dari index `tagihan_operasional`.

### C. Overhaul Chat UI & Fitur Premium
- **Palet Warna Teal & Navy**: Mengubah tampilan antarmuka web menjadi sangat elegan dan profesional bertema medis hospital, dilengkapi dengan drop shadow modern dan transisi mikro-interaktif.
- **KPI Summary Cards**: Jika query bertipe ringkasan umum (`summary`), bubble chat bot akan merender 3 kartu KPI utama (Total Pengeluaran, Rata-rata Biaya, dan Jumlah Tagihan) secara visual di atas jawaban teks.
- **Grafik Interaktif Tanpa Framework (SVG/CSS)**:
  - **Bar Chart Vertikal**: Digunakan untuk menampilkan tren pengeluaran bulanan (`per_bulan`) lengkap dengan label nominal rupiah dinamis.
  - **Progress Bar Horizontal**: Digunakan untuk menampilkan perbandingan pengeluaran antar-komponen biaya (`total_per_komponen`), poli termahal (`per_poli`), metode pembayaran terfavorit (`metode_bayar`), dan spesialisasi dokter (`per_spesialisasi`).
- **Ekspor CSV Instan**:
  Menyediakan tombol **📥 Unduh CSV** di dalam accordion data analitik JSON. Tombol ini mengonversi seluruh data agregasi (datar maupun bersarang) menjadi file spreadsheet `.csv` dan men-download-nya secara instan dari sisi klien.

---

## 5. Panduan Menjalankan & Menguji Proyek (Step-by-Step)

### Prasyarat
- Docker Desktop terinstal di komputer.
- Python 3.10+ (untuk seeding awal).
- Virtual environment (`venv`) terbuat dan diaktifkan.

### Langkah 1: Kloning & Pull Branch
Pastikan Anda berada di branch `develop` atau `main` yang telah diperbarui:
```bash
git checkout develop
git pull origin develop
```

### Langkah 2: Konfigurasi API Key
Isi variabel `GEMINI_API_KEY` pada file `.env` di root folder proyek:
```env
GEMINI_API_KEY=isi_dengan_api_key_gemini_anda
```

### Langkah 3: Jalankan Container Docker
Nyalakan container database, backend, dan frontend secara bersih:
```bash
docker compose down -v
docker compose up -d --build
```
*Tunggu sekitar 15 detik agar OpenSearch Node melakukan booting up sepenuhnya.*

### Langkah 4: Seeding Database Agregasi
Jalankan script python dari terminal lokal untuk melakukan denormalisasi data dan memasukkannya ke index `tagihan_operasional` di OpenSearch:
```bash
# Aktifkan venv Anda (Windows)
.\venv\Scripts\activate

# Install dependensi lokal jika belum ada
pip install opensearch-py

# Jalankan seeding
python scripts/index_to_opensearch.py
```
*Pastikan terminal menampilkan output "Success: 1500 documents indexed".*

### Langkah 5: Akses Aplikasi
- Buka browser dan arahkan ke: **`http://localhost:3000`** (Frontend Nginx).
- Indikator di pojok kanan atas akan menyala hijau dan menampilkan status: **`Online · OpenSearch 2.13.0`**.
- Kotak statistik di sebelah kanan akan menampilkan data dokter, pasien, registrasi, dan tagihan secara akurat.

---

## 6. Hasil Pengujian & Verifikasi

### A. Pengujian Endpoint API (Swagger)
Mengakses `http://localhost:8000/docs` membuktikan rute FastAPI bekerja:
- `GET /api/health` -> mengembalikan status `ok` dan versi OpenSearch `2.13.0`.
- `GET /api/stats` -> mengembalikan jumlah unik entitas database secara instan.
- `POST /api/ask` -> mengembalikan jawaban teks analitis, data agregasi mentah, serta tipe query.

### B. Pengujian Kasus Pertanyaan
1. **Pertanyaan Umum/Summary (KPI Cards)**:
   - *Pertanyaan*: "Berapa total biaya operasional rumah sakit?"
   - *Hasil*: Merender KPI Cards berisi total tagihan (~Rp 11 Miliar), rata-rata tagihan (~Rp 7.4 Juta), dan jumlah tagihan (1.500 kasus).
2. **Pertanyaan Tren Bulanan (Bar Chart Vertikal)**:
   - *Pertanyaan*: "Bagaimana tren biaya per bulan?"
   - *Hasil*: Bot merender grafik batang vertikal berwarna teal-biru yang dinamis, memetakan fluktuasi biaya dari bulan ke bulan.
3. **Pertanyaan Perbandingan (Progress Bar Horizontal)**:
   - *Pertanyaan*: "Poli mana yang paling banyak menghabiskan biaya?"
   - *Hasil*: Bot merender 5 progress bar horizontal teratas yang memetakan pengeluaran poli (misal: Gigi, Anak, Kandungan) secara proporsional.
4. **Pengujian Guardrail (Out of Scope)**:
   - *Pertanyaan*: "Apa obat untuk penyakit asma?"
   - *Hasil*: Sistem melewati query OpenSearch dan langsung merender teks penolakan sopan: *"Maaf, pertanyaan Anda berada di luar lingkup analisis biaya... Saya hanya dapat membantu Anda menganalisis data keuangan rumah sakit..."*
5. **Pengujian Ekspor CSV**:
   - Mengeklik tombol *"Lihat Data Analitik"* dan menekan tombol *"Unduh CSV"* langsung mengunduh file spreadsheet `.csv` berisi data tabel agregasi biaya yang valid ke folder Download PC.

---

## 7. Kesimpulan
Seluruh logic error, dead code, dan ketidakcocokan reverse proxy Nginx pada proyek ini telah diperbaiki secara tuntas. Pembuatan antarmuka grafik interaktif murni tanpa framework, kartu KPI eksekutif, filter otomatis case-normalization, serta guardrail scope pertanyaan out-of-scope membuat proyek QA System Rumah Sakit Sehat Selalu ini memiliki estetika yang **premium, tangguh, dan siap digunakan** untuk kepentingan manajemen eksekutif rumah sakit.
