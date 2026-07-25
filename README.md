# folder-size-monitor

Monitor pertumbuhan kapasitas folder tertentu di banyak server Debian, lalu kirim snapshot ke InfluxDB 3 Core.

## Gambaran singkat

Proyek ini terdiri dari:
- script Python kecil yang menjalankan `du` hanya untuk folder target
- file config per server untuk mendefinisikan folder apa saja yang dipantau
- file env untuk menyimpan endpoint dan token InfluxDB
- 1 baris `cron` untuk menjalankan monitor tiap 3 jam

Tujuannya adalah menyimpan snapshot ukuran folder secara berkala supaya nanti bisa dianalisis growth-nya di InfluxDB.

## Alur kerja

1. Clone repo ke server Debian yang ingin dimonitor.
2. Copy dan sesuaikan file config dan env.
3. Install script ke lokasi yang mudah dipanggil, misalnya `/usr/local/bin/folder-size-monitor`.
4. Tambahkan cron job via `crontab -e`.
5. Setiap 3 jam, script membaca daftar folder target, menjalankan `du` untuk masing-masing folder, lalu menulis hasil ke InfluxDB.

## Struktur file

- `folder_size_monitor.py`
  - script utama
  - membaca config
  - menjalankan `du`
  - mengirim data ke InfluxDB dalam line protocol

- `config.example.json`
  - contoh konfigurasi folder target per server
  - file ini disalin menjadi config aktif di server

- `.env.example`
  - contoh variabel environment yang diperlukan script
  - file ini disalin menjadi `.env` aktif di server

- `.gitignore`
  - mencegah file rahasia dan artefak ikut ter-commit

## Instalasi

### 1) Clone repo

```bash
git clone <URL-REPO> folder-size-monitor
cd folder-size-monitor
```

### 2) Siapkan file environment

Salin file contoh menjadi file aktif:

```bash
cp .env.example /etc/folder-size-monitor.env
chmod 600 /etc/folder-size-monitor.env
```

Lalu edit file tersebut:

```bash
nano /etc/folder-size-monitor.env
```

### Penjelasan `.env`

Isi yang disarankan:

```bash
INFLUX_URL=http://docker2-pdn1:8181
INFLUX_DB=infrastruktur
INFLUX_TOKEN=replace-me
SITE=pdns1
FOLDER_MONITOR_CONFIG=/etc/folder-size-monitor.json
DU_TIMEOUT_SEC=120
```

Arti tiap variabel:

- `INFLUX_URL`
  - alamat InfluxDB 3 Core
  - contoh saat ini: `http://docker2-pdn1:8181`

- `INFLUX_DB`
  - nama database tujuan untuk menyimpan snapshot
  - contoh saat ini: `infrastruktur`

- `INFLUX_TOKEN`
  - token auth untuk menulis data ke InfluxDB
  - simpan hanya di file `.env`, jangan di chat atau repo

- `SITE`
  - penanda lokasi atau site server
  - dipakai sebagai tag data

- `FOLDER_MONITOR_CONFIG`
  - path file config JSON yang berisi daftar folder target
  - default yang disarankan: `/etc/folder-size-monitor.json`

- `DU_TIMEOUT_SEC`
  - batas waktu maksimal `du` untuk satu folder
  - jika folder sangat besar, `du` bisa lambat; timeout mencegah job menggantung terlalu lama

### 3) Siapkan config folder

Salin contoh config menjadi file aktif:

```bash
cp config.example.json /etc/folder-size-monitor.json
```

Lalu edit sesuai folder yang ingin dipantau pada server itu:

```bash
nano /etc/folder-size-monitor.json
```

### Penjelasan `config.json`

Contoh:

```json
{
  "database": "infrastruktur",
  "site": "pdns1",
  "measurement": "ukuran_folder",
  "paths": [
    {"path": "/mnt/docker/volumes/api_app"},
    {"path": "/mnt/docker/volumes/api_db"},
    {"path": "/srv/data/uploads", "label": "uploads"}
  ]
}
```

Arti tiap field:

- `database`
  - database InfluxDB tujuan
  - jika tidak diisi, script pakai nilai dari `INFLUX_DB`

- `site`
  - nilai tag site untuk server ini
  - jika tidak diisi, script pakai nilai dari `SITE`

- `measurement`
  - nama measurement di InfluxDB
  - default: `ukuran_folder`

- `paths`
  - daftar folder yang akan diukur
  - bisa berisi string sederhana atau object

Bentuk yang didukung untuk `paths`:

```json
"/srv/data/uploads"
```

atau:

```json
{"path": "/srv/data/uploads", "label": "uploads"}
```

`label` bersifat opsional dan dipakai sebagai tag tambahan kalau ingin memberi nama yang lebih mudah dibaca daripada path panjang.

### 4) Install script ke PATH

```bash
install -m 0755 folder_size_monitor.py /usr/local/bin/folder-size-monitor
```

### 5) Tambahkan cron job

Buka crontab:

```bash
crontab -e
```

Tambahkan baris ini:

```cron
0 */3 * * * . /etc/folder-size-monitor.env; /usr/local/bin/folder-size-monitor >> /var/log/folder-size-monitor.log 2>&1
```

Maknanya:
- jalan setiap 3 jam
- load variabel dari `/etc/folder-size-monitor.env`
- jalankan script monitor
- simpan log ke `/var/log/folder-size-monitor.log`

## Penjelasan output data

Script mengirim data ke InfluxDB dengan bentuk snapshot seperti:

- measurement: `ukuran_folder`
- tags:
  - `path`
  - `server`
  - `site`
  - `label` jika ada
- field:
  - `size`
- timestamp:
  - waktu eksekusi saat snapshot diambil

Contoh line protocol:

```text
ukuran_folder,path=/mnt/docker/volumes/api_db,server=docker2,site=pdns1 size=175419778i 1753416151000000000
```

## Catatan performa

Script sudah dibuat supaya lebih ringan dengan:
- `nice -n 19`
- `ionice -c3`
- timeout per folder

Tetap disarankan:
- hanya memantau folder yang memang penting
- jangan masukkan seluruh filesystem tanpa alasan kuat
- atur folder per server sesuai kebutuhan masing-masing host

## Verifikasi manual

Setelah setup, coba jalankan manual:

```bash
. /etc/folder-size-monitor.env
/usr/local/bin/folder-size-monitor
```

Lalu cek:
- apakah ada error di terminal
- apakah log menulis ringkasan sukses/gagal
- apakah data masuk ke InfluxDB

## Rekomendasi operasional

Untuk tiap server:
- buat satu config yang hanya berisi folder-folder milik server itu
- simpan env lokal di server tersebut
- gunakan `crontab -e` supaya jadwal mudah dilihat dan dikelola
- dokumentasikan folder mana saja yang dipantau agar mudah audit di kemudian hari
